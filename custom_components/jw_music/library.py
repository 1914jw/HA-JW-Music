"""In-memory JW Music library: storage plus additive-only refresh."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .api import (
    Track,
    async_discover_soundtracks,
    async_fetch_flat_category,
    async_fetch_pub_media_tracks,
    async_fetch_soj_songs,
)
from .const import (
    AUDIO_ROOT_KEY,
    AUDIO_DESCRIPTION_MIN_TRACK,
    DEFAULT_LANGUAGE,
    INTERNATIONAL_MUSIC_FOLDER_NAME,
    INTERNATIONAL_MUSIC_KEY,
    KNOWN_SOUNDTRACKS,
    LOGGER,
    SOJ_FOLDER_NAME,
)

SoundtrackFolder = dict[str, Any]  # {"name": str, "tracks": dict[str, Track]}


@dataclass
class MusicLibrary:
    """Holds the in-memory library and persists it to disk."""

    hass: HomeAssistant
    store: Store
    language: str = DEFAULT_LANGUAGE
    names: dict[str, str] = field(default_factory=dict)
    soj_songs: dict[str, Track] = field(default_factory=dict)
    international_songs: dict[str, Track] = field(default_factory=dict)
    soundtracks: dict[str, SoundtrackFolder] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        """True if nothing has been fetched yet (fresh install or new language)."""
        return not (self.soj_songs or self.international_songs or self.soundtracks)

    @property
    def soj_name(self) -> str:
        """Display name of the Sing Out Joyfully folder."""
        return self.names.get("soj", SOJ_FOLDER_NAME)

    @property
    def intl_name(self) -> str:
        """Display name of the International Music folder."""
        return self.names.get("intl", INTERNATIONAL_MUSIC_FOLDER_NAME)

    @staticmethod
    def _category_name(name: str | None) -> str | None:
        """The API falls back to the category key when a name is missing."""
        return None if name == INTERNATIONAL_MUSIC_KEY else name

    def _set_name(self, key: str, english: str, jw_name: str | None) -> bool:
        """Store a folder name from jw.org. English keeps the built-in name."""
        name = english
        if self.language != DEFAULT_LANGUAGE and jw_name and jw_name != english:
            name = jw_name
        if self.names.get(key) == name:
            return False
        self.names[key] = name
        return True

    def prune_invalid(self) -> bool:
        """Drop stored audio-description entries (song numbers from 500)."""
        stale = [
            n
            for n in self.soj_songs
            if n.isdigit() and int(n) >= AUDIO_DESCRIPTION_MIN_TRACK
        ]
        for number in stale:
            del self.soj_songs[number]
        return bool(stale)

    async def async_save(self) -> None:
        """Persist the current library."""
        await self.store.async_save(
            {
                "language": self.language,
                "names": self.names,
                "soj_songs": self.soj_songs,
                "international_songs": self.international_songs,
                "soundtracks": self.soundtracks,
            }
        )

    async def async_full_fetch(self, session: aiohttp.ClientSession) -> None:
        """Populate all three groups from scratch."""
        soj_name, self.soj_songs = await async_fetch_soj_songs(session, self.language)
        self._set_name("soj", SOJ_FOLDER_NAME, soj_name)

        intl = await async_fetch_flat_category(
            session, INTERNATIONAL_MUSIC_KEY, self.language
        )
        self.international_songs = intl[1] if intl else {}
        self._set_name(
            "intl",
            INTERNATIONAL_MUSIC_FOLDER_NAME,
            self._category_name(intl[0]) if intl else None,
        )

        self.soundtracks = await self._async_discover_all_soundtracks(session)

        await self.async_save()

    async def async_refresh(self, session: aiohttp.ClientSession) -> None:
        """Add new songs/soundtracks and sync folder names. Never changes
        or removes existing songs.
        """
        changed = False

        try:
            changed |= await self._refresh_soj(session)
        except Exception:  # noqa: BLE001
            LOGGER.exception("JW Music: Sing Out Joyfully refresh failed")

        try:
            changed |= await self._refresh_international(session)
        except Exception:  # noqa: BLE001
            LOGGER.exception("JW Music: International Music refresh failed")

        try:
            changed |= await self._refresh_soundtracks(session)
        except Exception:  # noqa: BLE001
            LOGGER.exception("JW Music: Soundtracks refresh failed")

        if changed:
            await self.async_save()

    async def _refresh_soj(self, session: aiohttp.ClientSession) -> bool:
        name, latest = await async_fetch_soj_songs(session, self.language)
        changed = self._set_name("soj", SOJ_FOLDER_NAME, name)
        new_numbers = [n for n in latest if n not in self.soj_songs]
        if not new_numbers:
            return changed
        for number in new_numbers:
            self.soj_songs[number] = latest[number]
        LOGGER.info(
            "JW Music: added %d new Sing Out Joyfully song(s): %s",
            len(new_numbers),
            ", ".join(sorted(new_numbers, key=int)),
        )
        return True

    async def _refresh_international(self, session: aiohttp.ClientSession) -> bool:
        result = await async_fetch_flat_category(
            session, INTERNATIONAL_MUSIC_KEY, self.language
        )
        if result is None:
            return False
        name, latest = result
        changed = self._set_name(
            "intl", INTERNATIONAL_MUSIC_FOLDER_NAME, self._category_name(name)
        )
        new_guids = [g for g in latest if g not in self.international_songs]
        if not new_guids:
            return changed
        for guid in new_guids:
            self.international_songs[guid] = latest[guid]
        LOGGER.info(
            "JW Music: added %d new International Music track(s)", len(new_guids)
        )
        return True

    async def _async_discover_all_soundtracks(
        self, session: aiohttp.ClientSession
    ) -> dict[str, SoundtrackFolder]:
        """Scan the whole Audio tree, then make sure the known soundtracks
        are present (mediator category first, pub-media as fallback).
        """
        discovered = await async_discover_soundtracks(
            session, AUDIO_ROOT_KEY, self.language
        )

        for key, (pub_code, _, _) in KNOWN_SOUNDTRACKS.items():
            if key in discovered and discovered[key][1]:
                continue
            result = await async_fetch_flat_category(session, key, self.language)
            if result is None or not result[1]:
                result = await async_fetch_pub_media_tracks(
                    session, pub_code, self.language
                )
            if result and result[1]:
                discovered[key] = result

        folders: dict[str, SoundtrackFolder] = {
            key: {"name": name, "tracks": tracks}
            for key, (name, tracks) in discovered.items()
        }

        # Known soundtracks always get their cover. The English name is
        # used for English, or when the lookup returned no localized name.
        for key, (_, english_name, thumbnail) in KNOWN_SOUNDTRACKS.items():
            if key in folders:
                if self.language == DEFAULT_LANGUAGE or folders[key]["name"] in (
                    None,
                    key,
                ):
                    folders[key]["name"] = english_name
                folders[key]["thumbnail"] = thumbnail

        return folders

    async def _refresh_soundtracks(self, session: aiohttp.ClientSession) -> bool:
        """One scan covers new tracks, new soundtrack folders, and keeps
        name/cover of the known ones in sync.
        """
        changed = False
        all_found = await self._async_discover_all_soundtracks(session)

        for key, folder in all_found.items():
            if key not in self.soundtracks:
                self.soundtracks[key] = folder
                LOGGER.info(
                    "JW Music: found new soundtrack folder: %s", folder["name"]
                )
                changed = True
                continue

            existing = self.soundtracks[key]
            existing_tracks = existing["tracks"]
            new_guids = [g for g in folder["tracks"] if g not in existing_tracks]
            for guid in new_guids:
                existing_tracks[guid] = folder["tracks"][guid]
            if new_guids:
                LOGGER.info(
                    "JW Music: added %d new track(s) to soundtrack '%s'",
                    len(new_guids),
                    existing["name"],
                )
                changed = True

            if (
                existing.get("name") != folder["name"]
                or existing.get("thumbnail") != folder.get("thumbnail")
            ):
                existing["name"] = folder["name"]
                if "thumbnail" in folder:
                    existing["thumbnail"] = folder["thumbnail"]
                changed = True

        return changed
