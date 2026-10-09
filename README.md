# JW Music — Home Assistant Integration

A Home Assistant custom integration that adds JW Music as a browsable [media source](https://www.home-assistant.io/integrations/media_source/). No entities, no devices — just media folders that any media player can browse and play from.

## Features

- 🎵 **“Sing Out Joyfully” to Jehovah** — every song, numbered and titled exactly as on jw.org
- 🌍 **International Music** — jw.org's International Music category
- 🎬 **Soundtracks** — one sub-folder per film/drama soundtrack, auto-discovered from jw.org's Audio section
- 📁 **Media browser integration** — adds a **JW Music** folder to Home Assistant's Media browser
- ☁️ **Direct streaming** — audio comes straight from jw.org; nothing is stored permanently on the Home Assistant host
- 🔄 **Weekly refresh** — checks jw.org every Monday at 00:00:05 for new songs, tracks, and soundtrack folders and adds them automatically
- 💾 **Additive storage** — known entries are never changed or removed during a refresh
- 🚫 **No entities, no devices** — purely a media source
- 🔒 **Single instance** — only one JW Music entry can be set up

## Installation

### HACS (Recommended)

1. Install Integration via HACS

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=1914jw&repository=HA-Sing-Out-Joyfully&category=integration)

2. Restart Home Assistant

[![Open your Home Assistant instance and show your repairs.](https://my.home-assistant.io/badges/repairs.svg)](https://my.home-assistant.io/redirect/repairs/)

3. Add integration to Home Assistant

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=jw_music)

### Manual

1. Copy the `custom_components/jw_music/` folder to `/config/custom_components/`
2. Restart Home Assistant
3. Add integration to Home Assistant

## Upgrading from “Sing Out Joyfully”

This replaces the old **Sing Out Joyfully** integration (`sing_out_joyfully` domain) — it does not upgrade in place. On the Home Assistant host:

1. **Settings → Devices & Services → Sing Out Joyfully →** delete the integration
2. Delete the old component folder: `/config/custom_components/sing_out_joyfully/`
3. Delete the old cache file: `/config/.storage/sing_out_joyfully`
4. Install **JW Music** as described above and add it fresh

## Setup

**Settings → Devices & Services → Add Integration → JW Music → confirm.**

No configuration, account, or API key is required. On first setup the integration fetches all songs, tracks, and soundtrack folders once so the folders are not empty.

## Usage

Open **Media** in the sidebar (or a media player's browse dialog) and select **JW Music**. Selecting a track plays it directly from jw.org.

| Folder | Content | Order |
| --- | --- | --- |
| **“Sing Out Joyfully” to Jehovah** | Songbook songs | Song number |
| **International Music** | jw.org International Music category | As on jw.org |
| **Soundtracks** | One sub-folder per soundtrack (e.g. *The Good News According to Jesus—Soundtrack 1*) | As on jw.org |

## How it works

| Step | What happens |
| --- | --- |
| First setup | Fetches Sing Out Joyfully, International Music, and every soundtrack folder once from jw.org and stores the result locally |
| Every Monday, 00:00:05 | Re-checks all three groups, including a scan of jw.org's Audio category tree for new soundtrack folders. Anything not already known is added; existing entries are never changed or removed. This is the only automatic network request the integration makes |
| Playback | Resolves the stored jw.org URL for the track at the moment you press play |

## Notes

- The integration icon ships inside the component (`custom_components/jw_music/brand/`) and is served via Home Assistant's Brands Proxy API (2026.3+) — no extra setup needed.
- Content is currently fetched in English (`langwritten=E`).
- Soundtrack auto-discovery is heuristic: jw.org's API has no explicit “soundtrack” flag, so folders are matched by category key/name. A soundtrack published under an unusual name could be missed — please open an issue if you find one.

## Folder structure

```
/config/
  custom_components/
    jw_music/
      ...               ← integration code
      brand/            ← integration icon
      static/           ← Soundtracks folder icon, served automatically
  .storage/
    jw_music            ← known songs/tracks (created automatically)
```

---

## License

MIT License – see [LICENSE](https://github.com/1914jw/HA-Sing-Out-Joyfully/blob/main/LICENSE)
> This project is unofficial and is not affiliated with, endorsed, sponsored, or specifically approved by jw.org. Audio is streamed from the official jw.org servers; nothing is hosted or redistributed by this integration. For more information see [Terms of Use (jw.org)](https://www.jw.org/en/terms-of-use/).
---
