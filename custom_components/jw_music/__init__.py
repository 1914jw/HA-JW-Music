"""The JW Music integration.

Adds a media source (Settings > Media) with three folders: "Sing Out
Joyfully" to Jehovah, International Music, and Soundtracks. Tracks
stream directly from jw.org; only for Apple TV targets a track is first
copied to the system temp folder (see cache.py) and removed again when the
integration unloads. This integration does not create any entities or
devices.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.storage import Store

from .cache import async_clear_cache
from .const import (
    CHECK_HOUR,
    CHECK_MINUTE,
    CHECK_SECOND,
    CHECK_WEEKDAY,
    LOGGER,
    SOUNDTRACKS_FOLDER_STATIC_FILE,
    SOUNDTRACKS_FOLDER_STATIC_URL,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .library import MusicLibrary

type JwMusicConfigEntry = ConfigEntry[MusicLibrary]


async def async_setup_entry(hass: HomeAssistant, entry: JwMusicConfigEntry) -> bool:
    """Set up JW Music from a config entry."""
    static_file = Path(__file__).parent / "static" / SOUNDTRACKS_FOLDER_STATIC_FILE
    if static_file.is_file():
        try:
            await hass.http.async_register_static_paths(
                [StaticPathConfig(SOUNDTRACKS_FOLDER_STATIC_URL, str(static_file), True)]
            )
        except RuntimeError:
            # Already registered by a previous setup/reload of this entry.
            pass
    else:
        LOGGER.warning(
            "JW Music: %s not found -- Soundtracks folder will show without "
            "a custom icon until it's added",
            static_file,
        )

    session = async_get_clientsession(hass)
    store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    stored = await store.async_load() or {}
    library = MusicLibrary(
        hass=hass,
        store=store,
        soj_songs=stored.get("soj_songs", {}),
        international_songs=stored.get("international_songs", {}),
        soundtracks=stored.get("soundtracks", {}),
    )

    if library.is_empty:
        # First-ever setup (nothing cached yet): fetch once so the folders
        # aren't empty. This happens because the user just added the
        # integration -- it is not a recurring/automatic request.
        try:
            await library.async_full_fetch(session)
        except Exception as err:  # noqa: BLE001
            raise ConfigEntryNotReady(
                "Could not reach jw.org to load the JW Music library"
            ) from err

    entry.runtime_data = library

    async def _async_weekly_check(now: dt.datetime) -> None:
        """Check jw.org for new content.

        This fires every day at the configured time but only acts on
        Mondays. It is the only automatic network request this
        integration ever makes.
        """
        if now.weekday() != CHECK_WEEKDAY:
            return
        try:
            await library.async_refresh(session)
        except Exception:  # noqa: BLE001
            LOGGER.exception("JW Music: weekly check failed")

    entry.async_on_unload(
        async_track_time_change(
            hass,
            _async_weekly_check,
            hour=CHECK_HOUR,
            minute=CHECK_MINUTE,
            second=CHECK_SECOND,
        )
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: JwMusicConfigEntry) -> bool:
    """Unload a config entry."""
    await async_clear_cache(hass)
    return True
