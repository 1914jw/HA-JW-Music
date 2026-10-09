"""Low-level jw.org API calls. No storage or refresh-diffing here."""

from __future__ import annotations

from typing import Any

import aiohttp

from .const import (
    FILEFORMAT,
    LANGWRITTEN,
    LOGGER,
    MEDIATOR_CATEGORIES_URL,
    MIME_TYPE,
    MIME_TYPE_ALIASES,
    PUB_MEDIA_LINKS_URL,
    PUB_SYMBOL,
    SOUNDTRACK_KEY_HINT,
    SOUNDTRACK_SCAN_MAX_DEPTH,
    SOUNDTRACK_SCAN_MAX_REQUESTS,
    STREAMABLE_MIME_TYPES,
)

Track = dict[str, str]  # {"title": ..., "url": ..., "mime_type": ...}


async def async_fetch_soj_songs(session: aiohttp.ClientSession) -> dict[str, Track]:
    """Fetch the current "Sing Out Joyfully" song list.

    Returns song number (as string, e.g. "1") -> {"title", "url"},
    matching the numbering and titles shown on jw.org exactly.
    """
    params = {
        "langwritten": LANGWRITTEN,
        "pub": PUB_SYMBOL,
        "fileformat": FILEFORMAT,
    }
    async with session.get(PUB_MEDIA_LINKS_URL, params=params) as resp:
        resp.raise_for_status()
        payload: dict[str, Any] = await resp.json(content_type=None)

    files = payload.get("files", {}).get(LANGWRITTEN, {}).get(FILEFORMAT, [])

    songs: dict[str, Track] = {}
    for item in files:
        track = item.get("track")
        title = item.get("title")
        url = (item.get("file") or {}).get("url")
        if not track or not title or not url:
            continue
        if item.get("specialty") or "audio description" in title.lower():
            # Skip the Audio Description edition published alongside every
            # song -- only the standard recording belongs in the folder.
            continue
        songs[str(track)] = {"title": title, "url": url, "mime_type": MIME_TYPE}

    return songs


async def async_fetch_pub_media_tracks(
    session: aiohttp.ClientSession, pub_code: str
) -> tuple[str | None, dict[str, Track]] | None:
    """Fetch a publication's tracks via the pub-media API (the same API
    and fileformat used for Sing Out Joyfully). Used as a fallback for
    the known soundtracks in case one isn't reachable as a mediator
    category. Returns None if the pub code doesn't exist or has no
    audio. The returned name is None -- callers that need a display
    name should supply their own (e.g. from KNOWN_SOUNDTRACKS).
    """
    params = {"langwritten": LANGWRITTEN, "pub": pub_code, "fileformat": FILEFORMAT}
    async with session.get(PUB_MEDIA_LINKS_URL, params=params) as resp:
        if resp.status == 404:
            return None
        resp.raise_for_status()
        payload: dict[str, Any] = await resp.json(content_type=None)

    files = payload.get("files", {}).get(LANGWRITTEN, {}).get(FILEFORMAT, [])
    if not files:
        return None

    tracks: dict[str, Track] = {}
    for idx, item in enumerate(files, start=1):
        title = item.get("title")
        url = (item.get("file") or {}).get("url")
        if not title or not url:
            continue
        if item.get("specialty") or "audio description" in title.lower():
            continue
        key = str(item.get("track") or idx)
        tracks[key] = {"title": title, "url": url, "mime_type": MIME_TYPE}

    return (None, tracks) if tracks else None


def normalize_mime_type(mime_type: str | None) -> str:
    """Return a canonical audio MIME type (e.g. "audio/mp3" -> "audio/mpeg").

    Falls back to the default MP3 type when the value is missing or empty.
    """
    base = str(mime_type or "").split(";")[0].strip().lower()
    if not base:
        return MIME_TYPE
    return MIME_TYPE_ALIASES.get(base, base)


def _bitrate(media_file: dict[str, Any]) -> float:
    try:
        return float(media_file.get("bitRate") or 0)
    except (TypeError, ValueError):
        return 0.0


def _best_audio_file(files: list[dict[str, Any]]) -> tuple[str, str] | None:
    """Pick the best audio file from a media item's files.

    Formats every player can handle (MP3, FLAC, Ogg, WAV) win over exotic
    ones, so Apple TV / AirPlay -- where Home Assistant decodes the
    stream -- plays the same tracks as Google Cast. Within that, the
    highest bitrate wins.

    Returns (url, mimetype) -- the real mimetype is kept (not assumed)
    so playback works correctly on media players that validate it.
    """
    audio_files = [
        (normalize_mime_type(f.get("mimetype")), f)
        for f in files
        if str(f.get("mimetype", "")).startswith("audio")
        and f.get("progressiveDownloadURL")
    ]
    if not audio_files:
        return None
    mime_type, best = max(
        audio_files,
        key=lambda pair: (pair[0] in STREAMABLE_MIME_TYPES, _bitrate(pair[1])),
    )
    return best["progressiveDownloadURL"], mime_type


def _parse_media_items(media: list[dict[str, Any]]) -> dict[str, Track]:
    """Turn a category's raw "media" list into {guid: {title, url, mime_type}}."""
    tracks: dict[str, Track] = {}
    for item in media:
        guid = item.get("guid")
        title = item.get("title")
        picked = _best_audio_file(item.get("files") or [])
        if not guid or not title or not picked:
            continue
        url, mime_type = picked
        tracks[guid] = {"title": title, "url": url, "mime_type": mime_type}
    return tracks


async def async_fetch_category(
    session: aiohttp.ClientSession, key: str
) -> dict[str, Any] | None:
    """Fetch one mediator category by key. Returns None if not found."""
    url = f"{MEDIATOR_CATEGORIES_URL}/{LANGWRITTEN}/{key}"
    async with session.get(
        url, params={"detailed": "1", "clientType": "www"}
    ) as resp:
        if resp.status == 404:
            return None
        resp.raise_for_status()
        payload: dict[str, Any] = await resp.json(content_type=None)
    return payload.get("category")


async def async_fetch_flat_category(
    session: aiohttp.ClientSession, key: str
) -> tuple[str, dict[str, Track]] | None:
    """Fetch a single category's own tracks (International Music, or one
    already-known soundtrack). Returns (display name, tracks), or None if
    the category no longer exists.
    """
    category = await async_fetch_category(session, key)
    if category is None:
        return None
    name = category.get("name") or key
    tracks = _parse_media_items(category.get("media") or [])
    return name, tracks


def _looks_like_soundtrack(category: dict[str, Any]) -> bool:
    hint = SOUNDTRACK_KEY_HINT
    return hint in str(category.get("key", "")).lower() or hint in str(
        category.get("name", "")
    ).lower()


async def async_discover_soundtracks(
    session: aiohttp.ClientSession, root_key: str
) -> dict[str, tuple[str, dict[str, Track]]]:
    """Recursively scan a category tree for soundtrack categories.

    Returns {category_key: (display name, tracks)} for every category
    found whose key or name contains "Soundtrack" and that has at least
    one playable track. Best-effort: jw.org has no explicit
    "type: soundtrack" field, so this is a heuristic, not a guarantee --
    see SOUNDTRACK_KEY_HINT in const.py.
    """
    found: dict[str, tuple[str, dict[str, Track]]] = {}
    visited: set[str] = set()
    requests_made = 0

    async def _walk(key: str, depth: int) -> None:
        nonlocal requests_made
        if (
            key in visited
            or depth > SOUNDTRACK_SCAN_MAX_DEPTH
            or requests_made >= SOUNDTRACK_SCAN_MAX_REQUESTS
        ):
            return
        visited.add(key)
        category = await async_fetch_category(session, key)
        requests_made += 1
        if category is None:
            return

        media = category.get("media") or []
        if media and _looks_like_soundtrack(category):
            tracks = _parse_media_items(media)
            if tracks:
                found[key] = (category.get("name") or key, tracks)

        for sub in category.get("subcategories") or []:
            sub_key = sub.get("key")
            if sub_key:
                await _walk(sub_key, depth + 1)

    await _walk(root_key, 0)
    if requests_made >= SOUNDTRACK_SCAN_MAX_REQUESTS:
        LOGGER.warning(
            "JW Music: soundtrack scan stopped at the %d-request safety "
            "cap; some soundtracks may not have been found this run",
            SOUNDTRACK_SCAN_MAX_REQUESTS,
        )
    return found
