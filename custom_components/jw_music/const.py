"""Constants for the JW Music integration."""

import logging
from typing import Final

DOMAIN: Final = "jw_music"
NAME: Final = "JW Music"

LOGGER = logging.getLogger(__package__)

# -- "Sing Out Joyfully" to Jehovah (publication media API) --
PUB_MEDIA_LINKS_URL: Final = "https://app.jw-cdn.org/apis/pub-media/GETPUBMEDIALINKS"
PUB_SYMBOL: Final = "sjjm"  # "Sing Out Joyfully" to Jehovah -- Meetings (pub code)
LANGWRITTEN: Final = "E"  # English
FILEFORMAT: Final = "MP3"
MIME_TYPE: Final = "audio/mpeg"

STREAMABLE_MIME_TYPES: Final = ("audio/mpeg", "audio/flac", "audio/ogg", "audio/wav")
# Common spelling variants -> the canonical type used above.
MIME_TYPE_ALIASES: Final = {
    "audio/mp3": "audio/mpeg",
    "audio/x-mp3": "audio/mpeg",
    "audio/x-mpeg": "audio/mpeg",
    "audio/x-flac": "audio/flac",
    "audio/x-wav": "audio/wav",
    "audio/wave": "audio/wav",
    "audio/vorbis": "audio/ogg",
    "audio/x-ogg": "audio/ogg",
}
SOJ_FOLDER_NAME: Final = "“Sing Out Joyfully” to Jehovah"
SOJ_FOLDER_THUMBNAIL: Final = (
    "https://cms-imgp.jw-cdn.org/img/p/sjj/univ/pt/sjj_univ_lg.jpg"
)

# -- International Music / Soundtracks (mediator categories API) --
MEDIATOR_CATEGORIES_URL: Final = "https://b.jw-cdn.org/apis/mediator/v1/categories"

INTERNATIONAL_MUSIC_KEY: Final = "AudioInternationalMusic"
INTERNATIONAL_MUSIC_FOLDER_NAME: Final = "International Music"

SOUNDTRACKS_FOLDER_NAME: Final = "Soundtracks"
SOUNDTRACKS_FOLDER_STATIC_URL: Final = "/jw_music_static/soundtracks-folder.png"
SOUNDTRACKS_FOLDER_STATIC_FILE: Final = "soundtracks-folder.png"

AUDIO_ROOT_KEY: Final = "Audio"
# jw.org has no "type: soundtrack" field in this API
SOUNDTRACK_KEY_HINT: Final = "soundtrack"
SOUNDTRACK_SCAN_MAX_DEPTH: Final = 6
SOUNDTRACK_SCAN_MAX_REQUESTS: Final = 250

# Explicitly known soundtracks: mediator category key -> (pub-media pub
# code, official display name, jw-cdn.org cover image)
KNOWN_SOUNDTRACKS: Final = {
    "GNJST1Soundtrack": (
        "gnjst1",
        "The Good News According to Jesus—Soundtrack 1",
        "https://cms-imgp.jw-cdn.org/img/p/gnjst1/univ/pt/gnjst1_univ_lg.jpg",
    ),
    "GNJST2Soundtrack": (
        "gnjst2",
        "The Good News According to Jesus—Soundtrack 2",
        "https://cms-imgp.jw-cdn.org/img/p/gnjst2/univ/pt/gnjst2_univ_lg.jpg",
    ),
    "GNJST3Soundtrack": (
        "gnjst3",
        "The Good News According to Jesus—Soundtrack 3",
        "https://cms-imgp.jw-cdn.org/img/p/gnjst3/univ/pt/gnjst3_univ_lg.jpg",
    ),
    "AudioCYWSoundtrack": (
        "cywst",
        "Commit Your Way to Jehovah—Soundtrack",
        "https://cms-imgp.jw-cdn.org/img/p/cywst/univ/pt/cywst_univ_lg.jpg",
    ),
}

FILE_STREAMING_PLATFORMS: Final = ("apple_tv",)
CACHE_DIR_NAME: Final = "jw_music"
CACHE_MAX_FILES: Final = 10
CACHE_MAX_BYTES: Final = 150 * 1024 * 1024
CACHE_DOWNLOAD_TIMEOUT: Final = 120  # seconds

STORAGE_VERSION: Final = 1
STORAGE_KEY: Final = DOMAIN

# Weekly refresh schedule: every Monday at 00:00:05.
CHECK_HOUR: Final = 0
CHECK_MINUTE: Final = 0
CHECK_SECOND: Final = 5
CHECK_WEEKDAY: Final = 0  # datetime.weekday(): Monday == 0
