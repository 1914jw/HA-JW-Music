"""The JW Music integration.

Adds a media source with three folders: "Sing Out Joyfully" to Jehovah,
International Music, and Soundtracks. Tracks stream directly from jw.org.
No entities or devices are created.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.storage import Store

from .cache import async_clear_cache
from .const import (
    CHECK_HOUR,
    CHECK_MINUTE,
    CHECK_SECOND,
    CHECK_WEEKDAY,
    CONF_LANGUAGE,
    DEFAULT_LANGUAGE,
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
            # Already registered by an earlier setup of this entry.
            pass
    else:
        LOGGER.warning(
            "JW Music: %s not found -- Soundtracks folder will show without "
            "a custom icon until it's added",
            static_file,
        )

    session = async_get_clientsession(hass)
    store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    language = entry.options.get(CONF_LANGUAGE, DEFAULT_LANGUAGE)
    stored = await store.async_load() or {}
    if stored.get("language", DEFAULT_LANGUAGE) != language:
        # Titles are language-specific: start over after a language change.
        stored = {}
    library = MusicLibrary(
        hass=hass,
        store=store,
        language=language,
        names=stored.get("names", {}),
        soj_songs=stored.get("soj_songs", {}),
        international_songs=stored.get("international_songs", {}),
        soundtracks=stored.get("soundtracks", {}),
    )

    fetched_now = library.is_empty
    if fetched_now:
        # First setup or language change: fetch once so the folders aren't empty.
        try:
            await library.async_full_fetch(session)
        except Exception as err:  # noqa: BLE001
            raise ConfigEntryNotReady(
                "Could not reach jw.org to load the JW Music library"
            ) from err
    elif library.prune_invalid():
        await library.async_save()

    entry.runtime_data = library

    @callback
    def _async_refresh_after_start(_: HomeAssistant) -> None:
        """Pick up new content after every start, reload, or update."""
        entry.async_create_background_task(
            hass, library.async_refresh(session), "jw_music_refresh_on_setup"
        )

    if not fetched_now:
        entry.async_on_unload(async_at_started(hass, _async_refresh_after_start))

    async def _async_weekly_check(now: dt.datetime) -> None:
        """Weekly check (fires daily, acts on Mondays only)."""
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
