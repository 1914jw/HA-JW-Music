"""Low-level jw.org API calls. No storage or refresh-diffing here."""

from __future__ import annotations

from typing import Any

import aiohttp

from .const import (
    AUDIO_DESCRIPTION_MIN_TRACK,
    FILEFORMAT,
    INTERNATIONAL_MUSIC_KEY,
    LOGGER,
    MEDIATOR_CATEGORIES_URL,
    MEDIATOR_LANGUAGES_URL,
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


class LanguageError(Exception):
    """A language code cannot be used with jw.org."""


class UnknownLanguageError(LanguageError):
    """The code is not in jw.org's language list."""


class NoContentError(LanguageError):
    """The language exists, but has no music content."""


async def async_fetch_language_codes(session: aiohttp.ClientSession) -> dict[str, str]:
    """Fetch jw.org's current language list as {UPPERCASE code: exact code}."""
    url = f"{MEDIATOR_LANGUAGES_URL}/E/web"
    async with session.get(url) as resp:
        resp.raise_for_status()
        payload: dict[str, Any] = await resp.json(content_type=None)
    return {
        str(lang["code"]).upper(): str(lang["code"])
        for lang in payload.get("languages") or []
        if lang.get("code")
    }


async def async_validate_language(session: aiohttp.ClientSession, code: str) -> str:
    """Return the exact jw.org code for ``code``.

    Raises UnknownLanguageError if jw.org does not list it and
    NoContentError if it has neither songbook nor International Music
    audio. Network errors propagate.
    """
    codes = await async_fetch_language_codes(session)
    language = codes.get(code.strip().upper())
    if language is None:
        raise UnknownLanguageError(code)
    _, songs = await async_fetch_soj_songs(session, language)
    if songs:
        return language
    intl = await async_fetch_flat_category(session, INTERNATIONAL_MUSIC_KEY, language)
    if intl and intl[1]:
        return language
    raise NoContentError(language)


async def _async_fetch_pub_media(
    session: aiohttp.ClientSession, pub_code: str, language: str
) -> tuple[str | None, list[dict[str, Any]]]:
    """Fetch a publication's (name, MP3 files); empty if it does not exist."""
    params = {"langwritten": language, "pub": pub_code, "fileformat": FILEFORMAT}
    async with session.get(PUB_MEDIA_LINKS_URL, params=params) as resp:
        if resp.status == 404:
            return None, []
        resp.raise_for_status()
        payload: dict[str, Any] = await resp.json(content_type=None)
    # The parent title has no edition suffix; fall back to the publication's own.
    name = payload.get("parentPubName") or payload.get("pubName")
    files = (payload.get("files") or {}).get(language, {}).get(FILEFORMAT, [])
    return name or None, files


def _is_audio_description(item: dict[str, Any], title: str) -> bool:
    """Language-independent: described editions are numbered from 500."""
    try:
        if int(item.get("track") or 0) >= AUDIO_DESCRIPTION_MIN_TRACK:
            return True
    except (TypeError, ValueError):
        pass
    return bool(item.get("specialty")) or "audio description" in title.lower()


async def async_fetch_soj_songs(
    session: aiohttp.ClientSession, language: str
) -> tuple[str | None, dict[str, Track]]:
    """Fetch the "Sing Out Joyfully" songbook as (name, songs).

    Songs map song number (as string, e.g. "1") -> track. Titles are
    pre-formatted by the API ("1. Title") and used as-is.
    """
    name, files = await _async_fetch_pub_media(session, PUB_SYMBOL, language)
    songs: dict[str, Track] = {}
    for item in files:
        track = item.get("track")
        title = item.get("title")
        url = (item.get("file") or {}).get("url")
        if not track or not title or not url:
            continue
        if _is_audio_description(item, title):
            continue
        songs[str(track)] = {"title": title, "url": url, "mime_type": MIME_TYPE}

    return name, songs


async def async_fetch_pub_media_tracks(
    session: aiohttp.ClientSession, pub_code: str, language: str
) -> tuple[str | None, dict[str, Track]] | None:
    """Fetch a publication's tracks via the pub-media API.

    Fallback for known soundtracks that are not reachable as a mediator
    category. The name is always None; callers supply their own.
    """
    tracks: dict[str, Track] = {}
    _, files = await _async_fetch_pub_media(session, pub_code, language)
    for idx, item in enumerate(files, start=1):
        title = item.get("title")
        url = (item.get("file") or {}).get("url")
        if not title or not url or _is_audio_description(item, title):
            continue
        key = str(item.get("track") or idx)
        tracks[key] = {"title": title, "url": url, "mime_type": MIME_TYPE}

    return (None, tracks) if tracks else None


def normalize_mime_type(mime_type: str | None) -> str:
    """Return a canonical audio MIME type (e.g. "audio/mp3" -> "audio/mpeg")."""
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
    """Pick (url, mimetype) of the best audio file.

    Widely playable formats win over exotic ones, then the highest bitrate.
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
    """Turn a category's raw "media" list into {guid: track}."""
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
    session: aiohttp.ClientSession, key: str, language: str
) -> dict[str, Any] | None:
    """Fetch one mediator category by key. Returns None if not found."""
    url = f"{MEDIATOR_CATEGORIES_URL}/{language}/{key}"
    async with session.get(
        url, params={"detailed": "1", "clientType": "www"}
    ) as resp:
        if resp.status == 404:
            return None
        resp.raise_for_status()
        payload: dict[str, Any] = await resp.json(content_type=None)
    return payload.get("category")


async def async_fetch_flat_category(
    session: aiohttp.ClientSession, key: str, language: str
) -> tuple[str, dict[str, Track]] | None:
    """Fetch a category's own tracks. Returns (name, tracks) or None."""
    category = await async_fetch_category(session, key, language)
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
    session: aiohttp.ClientSession, root_key: str, language: str
) -> dict[str, tuple[str, dict[str, Track]]]:
    """Recursively scan a category tree for soundtrack categories.

    Best-effort heuristic: matches "soundtrack" in a category's key or
    name and requires at least one playable track.
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
        category = await async_fetch_category(session, key, language)
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
