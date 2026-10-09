"""Expose the JW Music library as a Home Assistant media source."""

from __future__ import annotations

from typing import override

from homeassistant.components.media_player import MediaClass, MediaType
from homeassistant.components.media_source import (
    BrowseMediaSource,
    MediaSource,
    MediaSourceItem,
    PlayMedia,
    Unresolvable,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import JwMusicConfigEntry
from .api import Track, normalize_mime_type
from .cache import async_get_track_file
from .const import (
    DOMAIN,
    FILE_STREAMING_PLATFORMS,
    INTERNATIONAL_MUSIC_FOLDER_NAME,
    LOGGER,
    NAME,
    SOJ_FOLDER_NAME,
    SOJ_FOLDER_THUMBNAIL,
    SOUNDTRACKS_FOLDER_NAME,
    SOUNDTRACKS_FOLDER_STATIC_URL,
)
from .library import MusicLibrary


async def async_get_media_source(hass: HomeAssistant) -> JwMusicMediaSource:
    """Set up the JW Music media source."""
    entry: JwMusicConfigEntry = hass.config_entries.async_entries(DOMAIN)[0]
    return JwMusicMediaSource(hass, entry)


class JwMusicMediaSource(MediaSource):
    """Provide Sing Out Joyfully, International Music, and Soundtracks.

    Identifiers are colon-delimited paths, e.g. "soj:12",
    "intl:<guid>", "soundtracks:GNJST1Soundtrack:<guid>". Each folder is
    only expanded (its children built) when it is the one actually being
    browsed -- parent listings show unexpanded stubs.
    """

    name = NAME

    def __init__(self, hass: HomeAssistant, entry: JwMusicConfigEntry) -> None:
        """Initialize the media source."""
        super().__init__(DOMAIN)
        self.hass = hass
        self.entry = entry

    @property
    def _library(self) -> MusicLibrary:
        return self.entry.runtime_data

    @override
    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        """Resolve a track to its current jw.org stream URL."""
        track = self._find_track(item.identifier)
        if track is None:
            raise Unresolvable(f"Track {item.identifier} not found")
        url = track.get("url", "")
        # Home Assistant version with PlayMedia.path
        if not url.startswith(("https://", "http://")):
            raise Unresolvable(f"Track {item.identifier} has no playable URL")
        mime_type = normalize_mime_type(track.get("mime_type"))

        path = None
        if self._target_needs_file(item):
            # Apple TV cannot stream a URL reliably -- give it a local file.
            path = await async_get_track_file(
                self.hass, async_get_clientsession(self.hass), url, mime_type
            )
        LOGGER.debug(
            "Resolved %s -> %s (%s, local file: %s)",
            item.identifier,
            url,
            mime_type,
            path,
        )
        if path is not None:
            try:
                return PlayMedia(url, mime_type, path=path)
            except TypeError:
                # Home Assistant version without PlayMedia.path
                LOGGER.debug("PlayMedia.path not supported; using the URL")
        return PlayMedia(url, mime_type)

    def _target_needs_file(self, item: MediaSourceItem) -> bool:
        """True if the player this item is resolved for needs a local file."""
        entity_id = item.target_media_player
        if not isinstance(entity_id, str):
            return False
        entry = er.async_get(self.hass).async_get(entity_id)
        return entry is not None and entry.platform in FILE_STREAMING_PLATFORMS

    @override
    async def async_browse_media(self, item: MediaSourceItem) -> BrowseMediaSource:
        """Return a folder listing, or a single track."""
        parts = item.identifier.split(":") if item.identifier else []

        if not parts:
            return self._browse_root()
        if parts == ["soj"]:
            return self._browse_soj()
        if parts == ["intl"]:
            return self._browse_intl()
        if parts == ["soundtracks"]:
            return self._browse_soundtracks()
        if len(parts) == 2 and parts[0] == "soundtracks":
            return self._browse_soundtrack(parts[1])
        if len(parts) in (2, 3) and parts[0] in ("soj", "intl", "soundtracks"):
            return self._leaf(item.identifier, self._find_track(item.identifier))

        raise Unresolvable(f"Unknown identifier {item.identifier}")

    def _find_track(self, identifier: str) -> Track | None:
        """Look up a track by its full colon-delimited identifier."""
        parts = identifier.split(":")
        if len(parts) == 2 and parts[0] == "soj":
            return self._library.soj_songs.get(parts[1])
        if len(parts) == 2 and parts[0] == "intl":
            return self._library.international_songs.get(parts[1])
        if len(parts) == 3 and parts[0] == "soundtracks":
            folder = self._library.soundtracks.get(parts[1])
            return folder["tracks"].get(parts[2]) if folder else None
        return None

    def _browse_root(self) -> BrowseMediaSource:
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=None,
            media_class=MediaClass.DIRECTORY,
            media_content_type=MediaType.MUSIC,
            title=NAME,
            can_play=False,
            can_expand=True,
            children_media_class=MediaClass.DIRECTORY,
            children=[
                self._stub("soj", SOJ_FOLDER_NAME, SOJ_FOLDER_THUMBNAIL),
                self._stub("intl", INTERNATIONAL_MUSIC_FOLDER_NAME),
                self._stub(
                    "soundtracks",
                    SOUNDTRACKS_FOLDER_NAME,
                    SOUNDTRACKS_FOLDER_STATIC_URL,
                ),
            ],
        )

    def _browse_soj(self) -> BrowseMediaSource:
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier="soj",
            media_class=MediaClass.DIRECTORY,
            media_content_type=MediaType.MUSIC,
            title=SOJ_FOLDER_NAME,
            thumbnail=SOJ_FOLDER_THUMBNAIL,
            can_play=False,
            can_expand=True,
            children_media_class=MediaClass.MUSIC,
            children=[
                self._leaf(f"soj:{number}", song, SOJ_FOLDER_THUMBNAIL)
                for number, song in sorted(
                    self._library.soj_songs.items(), key=lambda kv: int(kv[0])
                )
            ],
        )

    def _browse_intl(self) -> BrowseMediaSource:
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier="intl",
            media_class=MediaClass.DIRECTORY,
            media_content_type=MediaType.MUSIC,
            title=INTERNATIONAL_MUSIC_FOLDER_NAME,
            can_play=False,
            can_expand=True,
            children_media_class=MediaClass.MUSIC,
            children=[
                self._leaf(f"intl:{guid}", song)
                for guid, song in self._library.international_songs.items()
            ],
        )

    def _browse_soundtracks(self) -> BrowseMediaSource:
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier="soundtracks",
            media_class=MediaClass.DIRECTORY,
            media_content_type=MediaType.MUSIC,
            title=SOUNDTRACKS_FOLDER_NAME,
            thumbnail=SOUNDTRACKS_FOLDER_STATIC_URL,
            can_play=False,
            can_expand=True,
            children_media_class=MediaClass.DIRECTORY,
            children=[
                self._stub(f"soundtracks:{key}", sub["name"], sub.get("thumbnail"))
                for key, sub in self._library.soundtracks.items()
            ],
        )

    def _browse_soundtrack(self, key: str) -> BrowseMediaSource:
        sub = self._library.soundtracks.get(key)
        if sub is None:
            raise Unresolvable(f"Soundtrack {key} not found")
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=f"soundtracks:{key}",
            media_class=MediaClass.DIRECTORY,
            media_content_type=MediaType.MUSIC,
            title=sub["name"],
            thumbnail=sub.get("thumbnail"),
            can_play=False,
            can_expand=True,
            children_media_class=MediaClass.MUSIC,
            children=[
                self._leaf(
                    f"soundtracks:{key}:{guid}", track, sub.get("thumbnail")
                )
                for guid, track in sub["tracks"].items()
            ],
        )

    @staticmethod
    def _stub(
        identifier: str, title: str, thumbnail: str | None = None
    ) -> BrowseMediaSource:
        """An unexpanded folder entry inside a parent's children list."""
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=identifier,
            media_class=MediaClass.DIRECTORY,
            media_content_type=MediaType.MUSIC,
            title=title,
            thumbnail=thumbnail,
            can_play=False,
            can_expand=True,
        )

    @staticmethod
    def _leaf(
        identifier: str, track: Track | None, thumbnail: str | None = None
    ) -> BrowseMediaSource:
        if track is None:
            raise Unresolvable(f"Track {identifier} not found")
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=identifier,
            media_class=MediaClass.MUSIC,
            # Always an "audio/..." MIME type: Apple TV and Cast browse
            # filters hide anything else on audio-only players.
            media_content_type=normalize_mime_type(track.get("mime_type")),
            title=track["title"],
            thumbnail=thumbnail,
            can_play=True,
            can_expand=False,
        )
