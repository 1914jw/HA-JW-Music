"""Short-lived local copies of tracks, for players that need a file.

pyatv cannot reliably stream an http(s) URL: it reads the
stream through a fixed 64 KiB buffer and fails with "failed to init
decoder" / "timed out reading from stream". Playing a local file path
works, so for those players a track is downloaded once into the system
temp folder (never into the HA config folder, so it is not part of
backups) and handed over as ``PlayMedia.path``. Other players keep 
streaming directly from jw.org.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import aiohttp

from homeassistant.core import HomeAssistant

from .const import (
    CACHE_DIR_NAME,
    CACHE_DOWNLOAD_TIMEOUT,
    CACHE_MAX_BYTES,
    CACHE_MAX_FILES,
    LOGGER,
)

_SUFFIX_BY_MIME = {
    "audio/mpeg": ".mp3",
    "audio/flac": ".flac",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
}
_CHUNK_SIZE = 64 * 1024
_locks: dict[str, asyncio.Lock] = {}


def _cache_dir() -> Path:
    return Path(tempfile.gettempdir()) / CACHE_DIR_NAME


def _suffix(url: str, mime_type: str) -> str:
    return _SUFFIX_BY_MIME.get(mime_type) or Path(urlparse(url).path).suffix or ".mp3"


def _touch_if_valid(target: Path) -> bool:
    """Blocking: True if a usable cached copy exists (and mark it as fresh)."""
    try:
        if target.is_file() and target.stat().st_size > 0:
            os.utime(target)
            return True
    except OSError:
        pass
    return False


def _prune(directory: Path, keep: Path) -> None:
    """Blocking: keep only the newest CACHE_MAX_FILES files."""
    files = sorted(
        (f for f in directory.iterdir() if f.is_file()),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    for old in files[CACHE_MAX_FILES:]:
        if old != keep:
            old.unlink(missing_ok=True)


def _store(target: Path, data: bytes) -> None:
    """Blocking: write atomically, then prune old copies."""
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    partial.write_bytes(data)
    os.replace(partial, target)
    _prune(target.parent, keep=target)


async def _download(session: aiohttp.ClientSession, url: str) -> bytes:
    timeout = aiohttp.ClientTimeout(total=CACHE_DOWNLOAD_TIMEOUT)
    async with session.get(url, timeout=timeout) as resp:
        resp.raise_for_status()
        if (resp.content_length or 0) > CACHE_MAX_BYTES:
            raise ValueError("file is too large")
        data = bytearray()
        async for chunk in resp.content.iter_chunked(_CHUNK_SIZE):
            data.extend(chunk)
            if len(data) > CACHE_MAX_BYTES:
                raise ValueError("file is too large")
    if not data:
        raise ValueError("empty response")
    return bytes(data)


async def async_get_track_file(
    hass: HomeAssistant, session: aiohttp.ClientSession, url: str, mime_type: str
) -> Path | None:
    """Return a local copy of the track at ``url``, or None on failure.

    Callers fall back to the plain URL when this returns None.
    """
    key = hashlib.sha256(url.encode()).hexdigest()[:24]
    target = _cache_dir() / f"{key}{_suffix(url, mime_type)}"

    async with _locks.setdefault(key, asyncio.Lock()):
        if await hass.async_add_executor_job(_touch_if_valid, target):
            return target
        try:
            data = await _download(session, url)
            await hass.async_add_executor_job(_store, target, data)
        except (aiohttp.ClientError, TimeoutError, ValueError, OSError) as err:
            LOGGER.warning("Could not cache %s for local playback: %s", url, err)
            return None
    return target


async def async_clear_cache(hass: HomeAssistant) -> None:
    """Delete all cached copies (called when the integration unloads)."""
    await hass.async_add_executor_job(
        lambda: shutil.rmtree(_cache_dir(), ignore_errors=True)
    )
