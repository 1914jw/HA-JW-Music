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
    INTERNATIONAL_MUSIC_KEY,
    KNOWN_SOUNDTRACKS,
    LOGGER,
)

SoundtrackFolder = dict[str, Any]  # {"name": str, "tracks": dict[str, Track]}


@dataclass
class MusicLibrary:
    """Holds the in-memory library and persists it to disk."""

    hass: HomeAssistant
    store: Store
    soj_songs: dict[str, Track] = field(default_factory=dict)
    international_songs: dict[str, Track] = field(default_factory=dict)
    soundtracks: dict[str, SoundtrackFolder] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        """True if nothing has ever been fetched yet (fresh install)."""
        return not (self.soj_songs or self.international_songs or self.soundtracks)

    async def async_save(self) -> None:
        """Persist the current library."""
        await self.store.async_save(
            {
                "soj_songs": self.soj_songs,
                "international_songs": self.international_songs,
                "soundtracks": self.soundtracks,
            }
        )

    async def async_full_fetch(self, session: aiohttp.ClientSession) -> None:
        """First-ever setup: populate all three groups from scratch."""
        self.soj_songs = await async_fetch_soj_songs(session)

        intl = await async_fetch_flat_category(session, INTERNATIONAL_MUSIC_KEY)
        self.international_songs = intl[1] if intl else {}

        self.soundtracks = await self._async_discover_all_soundtracks(session)

        await self.async_save()

    async def async_refresh(self, session: aiohttp.ClientSession) -> None:
        """Weekly check: add new songs/soundtracks. Never changes or
        removes existing entries.
        """
        changed = False

        try:
            changed |= await self._refresh_soj(session)
        except Exception:  # noqa: BLE001
            LOGGER.exception("JW Music: weekly Sing Out Joyfully check failed")

        try:
            changed |= await self._refresh_international(session)
        except Exception:  # noqa: BLE001
            LOGGER.exception("JW Music: weekly International Music check failed")

        try:
            changed |= await self._refresh_soundtracks(session)
        except Exception:  # noqa: BLE001
            LOGGER.exception("JW Music: weekly Soundtracks check failed")

        if changed:
            await self.async_save()

    async def _refresh_soj(self, session: aiohttp.ClientSession) -> bool:
        latest = await async_fetch_soj_songs(session)
        new_numbers = [n for n in latest if n not in self.soj_songs]
        if not new_numbers:
            return False
        for number in new_numbers:
            self.soj_songs[number] = latest[number]
        LOGGER.info(
            "JW Music: added %d new Sing Out Joyfully song(s): %s",
            len(new_numbers),
            ", ".join(sorted(new_numbers, key=int)),
        )
        return True

    async def _refresh_international(self, session: aiohttp.ClientSession) -> bool:
        result = await async_fetch_flat_category(session, INTERNATIONAL_MUSIC_KEY)
        if result is None:
            return False
        _, latest = result
        new_guids = [g for g in latest if g not in self.international_songs]
        if not new_guids:
            return False
        for guid in new_guids:
            self.international_songs[guid] = latest[guid]
        LOGGER.info(
            "JW Music: added %d new International Music track(s)", len(new_guids)
        )
        return True

    async def _async_discover_all_soundtracks(
        self, session: aiohttp.ClientSession
    ) -> dict[str, SoundtrackFolder]:
        """Recursive scan of the whole Audio tree, plus the explicitly
        known soundtracks as a safety net in case the scan doesn't reach
        them -- checked by mediator category key first, falling back to
        their pub-media pub code (like Sing Out Joyfully) if that comes
        back empty.
        """
        discovered = await async_discover_soundtracks(session, AUDIO_ROOT_KEY)

        for key, (pub_code, _, _) in KNOWN_SOUNDTRACKS.items():
            if key in discovered and discovered[key][1]:
                continue
            result = await async_fetch_flat_category(session, key)
            if result is None or not result[1]:
                result = await async_fetch_pub_media_tracks(session, pub_code)
            if result and result[1]:
                discovered[key] = result

        folders: dict[str, SoundtrackFolder] = {
            key: {"name": name, "tracks": tracks}
            for key, (name, tracks) in discovered.items()
        }

        # The official name/thumbnail always win for the four known
        # soundtracks, regardless of which lookup found them.
        for key, (_, official_name, thumbnail) in KNOWN_SOUNDTRACKS.items():
            if key in folders:
                folders[key]["name"] = official_name
                folders[key]["thumbnail"] = thumbnail

        return folders

    async def _refresh_soundtracks(self, session: aiohttp.ClientSession) -> bool:
        """One scan covers new tracks in known soundtracks, entirely new
        soundtrack folders, and keeps name/thumbnail in sync for the
        four explicitly known ones (so e.g. a newly added thumbnail
        reaches installs that already have the folder stored).
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
