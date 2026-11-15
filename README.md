<p align="center">
  <img src="assets/radiostreamplus-banner.svg" alt="RadioStream+" />
</p>

RadioStream+ is a local radio receiver manager and transparent OBS information overlay. It maps publicly listed KiwiSDR and OpenWebRX instances by their published coordinates. KiwiSDR receivers can be filtered by frequency, selected for playback, and rotated automatically.

Start the project with the cross-platform `radiostream.py` entrypoint. The two accompanying Python modules provide the directory and server logic. Everything uses the Python standard library; no Caddy, Flask, Node.js, npm, database server, or build step is required.

## Pages

| Address | Purpose |
|---|---|
| `http://localhost:5056/` | Management window with the Leaflet / OpenStreetMap receiver map and settings |
| `http://localhost:5056/overlay` | Transparent 1920 × 1080 information overlay for OBS |
| `http://localhost:5056/sdr` | Current KiwiSDR browser player; automatically follows receiver rotations |

The server binds to `127.0.0.1` only. It is intended for use on the computer running OBS, not as a public web server.

## Run it

Python 3.10 or newer is recommended. No third-party Python packages are required.

**Windows**

```powershell
py radiostream.py
```

**macOS / Linux**

```sh
python3 radiostream.py
```

Open `http://localhost:5056/` in a browser. The first start creates `radiostream.json` beside the script. You can edit that file directly or use the management page; saved settings are written back to it.

## Automatic updates

The `radiostream.py` launcher checks the public `main` branch for application updates every two minutes. It downloads changed files over HTTPS, verifies each file against its Git blob SHA-1, stages the complete update, and then replaces the files atomically. If a Python module changes, the launcher stops its request loop, reloads the modules in the same process, and starts the server again. It does not spawn a replacement process, so stopping the launcher from an IDE also stops the local server. Otherwise, the open pages leave maintenance mode and return to the page they were using.

During installation, `/`, `/manage`, `/overlay`, and `/sdr` are redirected to `m.html` (`Maintenance in progress...`). Already-open pages check the maintenance endpoint and redirect there too. They return automatically when the server is ready again.

The updater only replaces its explicit application-file allowlist. It never updates `radiostream.py` itself, and it does not replace `radiostream.json`, `station_preferences.json`, `openwebrx_custom.json`, directory caches, solar caches, logs, or other user data. Updating the launcher requires installing a newer project copy manually.

## Find receivers on the map

1. Click the map to place the search center, or drag the center pin.
2. Set the search range in kilometers.
3. Optionally use **Use browser location** to ask the browser to move the pin to the computer's current location. This is optional; RadioStream+ does not request location permission on its own.
4. Set the frequency and mode, then choose **Find receivers in range**.
5. Select an available KiwiSDR receiver. OpenWebRX entries have a direct link and open in a separate browser tab.
6. To manage OpenWebRX sources, add your own instances in the **Your OpenWebRX instances** section. Set the map pin to each receiver location or enter its coordinates, then add its public URL. Use the two source checkboxes to choose public listings, your custom list, or both.

The map uses Leaflet and OpenStreetMap tiles. Map data is fetched from OpenStreetMap's public tile service and attribution is shown in the map. Internet access is required for the map tiles.

## Radio settings

The management page and `radiostream.json` support:

- `center_lat`, `center_lon`: center pin coordinates.
- `radius_km`: discovery range, from 1 to 20,000 km.
- `frequency_khz`: tuned frequency stored in kHz, from 1 Hz to 300 GHz. The management page lets you enter it in Hz, kHz, MHz, or GHz.
- `mode`: `am`, `lsb`, `usb`, `cw`, or `nbfm`.
- `zoom`: KiwiSDR waterfall zoom, applied to every receiver when it is opened (0–14).
- `volume`: KiwiSDR volume value (0–200).
- `passband_low`, `passband_high`: KiwiSDR passband edges in Hz, relative to the tuned carrier.

Default passbands (low / high):

| Mode | Low (Hz) | High (Hz) |
|---|---:|---:|
| AM | -4900 | 4900 |
| LSB | -2700 | -300 |
| USB | 300 | 2700 |
| CW | 300 | 700 |
| NBFM | -6000 | 6000 |

Changing the modulation mode in the management page applies that mode's default passband. You can then edit either edge manually. Existing saved passbands are preserved when the page loads.

- `openwebrx_receiverbook_enabled`: whether public Receiverbook OpenWebRX listings are included in discovery (default `true`).
- `openwebrx_custom_enabled`: whether saved custom OpenWebRX entries are included in discovery (default `true`). Both source settings can be toggled independently.
- `rotation_minutes`: how long to stay on a receiver before switching (3–60 minutes; default 14).
- `overlay_reload_notice`: multiline text shown in the OBS overlay to describe the periodic receiver reload. The `${M}` placeholder is replaced with `rotation_minutes` when displayed.
- `overlay_black_notice`: multiline text shown in the OBS overlay if the receiver window stays black.

Both overlay messages can be edited in the management page and are saved in `radiostream.json`. Keep their line breaks where you want the lines to appear; each message supports up to 8 lines and 800 characters. Older configuration files are migrated automatically on startup, with the default messages written back without changing their existing radio settings.

Frequency, mode, zoom, volume, and passband settings are applied consistently when switching between receivers.

## Receiver discovery and rotation

RadioStream+ downloads the schema-1 public receiver list from the AetherSDR KiwiSDR directory mirror at `https://cdn.aethersdr.com/kiwi.json`. The directory's published cache window is 30 minutes; RadioStream+ respects that and keeps a local cache in `kiwi_directory_cache.json` so a temporary directory outage does not immediately erase the map. The mirror's `fetched_at` timestamp is shown in the management page.

OpenWebRX discovery can use Receiverbook's public listings, your own saved instances, or both. The two source checkboxes in the management page can be used independently, so you can temporarily hide either source without deleting its entries. Custom entries require a public HTTP or HTTPS URL and map coordinates; they are stored locally in `openwebrx_custom.json`. Nearby instances from enabled sources are checked against their advertised frequency ranges, and only receivers with a profile covering the selected frequency are shown. Their links open the receiver at the selected frequency and modulation. OpenWebRX+ only accepts tuning inside its currently active profile, so a receiver may still reject the link when a different profile is active. OpenWebRX instances open separately in the browser and are not part of automatic KiwiSDR rotation.

KiwiSDR coordinates come from the AetherSDR directory's `gps` pair. Receiverbook OpenWebRX coordinates come from its GeoJSON `location.coordinates` pair; custom OpenWebRX coordinates are supplied when you add each instance. All use the same map center and search radius. KiwiSDR receivers without a valid GPS fix, outside the selected radius or configured frequency band, marked offline, flagged by the directory, or listed as full are not selected for playback. The map can still show unavailable KiwiSDR entries when their locations are valid.

Receiver rotation uses the directory's published HF SNR and occupancy snapshot, avoids recently used stations where possible, and applies a weighted random order to eligible receivers. In the management list, the thumbs-up button gives a station four times the preference weight, while thumbs-down gives it one fifth of the normal weight. Receiver quality also contributes to the selection weight. The block button excludes a station from automatic rotation and manual selection until its block is cleared. Clicking an active preference again clears it. Preferences are saved in `station_preferences.json`, separately from the radio settings. The directory is a cached public listing, not a real-time guarantee: receiver availability can change after the listing was generated, and an individual receiver may stop accepting connections without warning.

Before opening a receiver, the player checks its landing page and skips pages that report an offline receiver, require a visitor name, or visibly display an `Enter Password:` prompt. Password detection ignores page scripts, styles, and comments, so unrelated source text does not trigger it. Other receiver page types are not excluded based on their HTML framework or branding. For receivers that request an identity dynamically after connecting, RadioStream+ supplies KiwiSDR's native `u=` URL parameter with a generated pseudonymous ID in the form `rsplus-XXXX`. KiwiSDR pre-fills and submits this value itself. The four-character suffix is generated once when RadioStream+ starts and remains stable during that run, including receiver rotations. It is a session label, not a callsign. A station may still require a genuine callsign or reject pseudonymous identities. The player also includes KiwiSDR's `ext=` parameter to suppress its nonessential first-visit readme panel.

The `ext_api` directory field governs non-browser external-API connections. RadioStream+ opens the regular KiwiSDR web interface in a browser frame, not the KiwiSDR native external API, so it does not filter web-only receivers based on that field.


## KiwiSDR panel auto-hide

RadioStream+ adds KiwiSDR's native `keys=x` shortcut to every receiver URL. After the receiver initializes, KiwiSDR hides its panel UI, including the **Readme** and **Control** panels. The existing `ext=` parameter also suppresses the nonessential first-visit Readme panel.

This uses KiwiSDR's own URL-shortcut feature, not injected JavaScript. The RadioStream+ page cannot click elements inside a cross-origin KiwiSDR iframe. The `x` shortcut hides all KiwiSDR panels, not just those two, and may take a few seconds to run after the receiver loads.

## Use in OBS

1. Start RadioStream+ with the Python command above.
2. In OBS, add a **Browser Source**.
3. Set its URL to `http://localhost:5056/overlay`.
4. Set width to `1920` and height to `1080`.
5. Keep the Browser Source background transparent.

Add a separate Browser Source at `http://localhost:5056/sdr` when the KiwiSDR player should be part of the OBS scene. Enable browser-source audio capture in OBS if you want to capture the receiver audio through that source. The player checks the local server every five seconds and unloads the remote KiwiSDR frame after three consecutive failed checks, so the receiver disconnects when RadioStream+ is stopped. You can also open `/sdr` in a regular browser.

The overlay retains the UTC clock, configurable local-time clock, and HF propagation panel. The local-time clock opens its settings when clicked. HamQSL XML is now retrieved through the local Python server at `/api/solar`, avoiding the direct-browser CORS dependency from the earlier standalone version.


HamQSL's [Solar-Terrestrial Data FAQ](https://www.hamqsl.com/FAQ.html#Solar) offers XML and RSS feeds and asks clients to refresh them no more often than once per hour. RadioStream+ enforces that limit in the server, including after failed requests and across restarts. It serves a one-hour local cache between refreshes and can use a valid stale cache for up to 14 days if the feed is unavailable.

## Data, privacy, and limitations

- The server listens only on the local loopback interface (`127.0.0.1`).
- The optional browser geolocation action sends its coordinates only to the local RadioStream+ server, where they are saved in `radiostream.json`.
- The public KiwiSDR directory request goes to the AetherSDR mirror. Receiver selection and playback then load the chosen public KiwiSDR website directly in the browser frame.
- OpenWebRX discovery requests Receiverbook's public map page when that source is enabled. Custom instance URLs and coordinates remain in the local `openwebrx_custom.json` file. Selecting an entry opens its receiver directly in a separate browser tab.
- The map uses OpenStreetMap tiles through its public tile service. Follow the [OpenStreetMap tile usage policy](https://operations.osmfoundation.org/policies/tiles/) for high-volume or redistributed deployments.
- RadioStream+ does not bypass a receiver's own password, connection limit, idle timeout, or other access rules. A selected receiver can still refuse or terminate a connection.
- The receiver directory is cached and may lag real-world availability. Rotation is based on the published snapshot and is not a promise that every station will accept a connection.
- Internet access is needed for the KiwiSDR directory, OSM map tiles, HamQSL propagation data, and remote receivers.

## Project origin and licensing

The original RadioStream+ software maintained by BR3XALITY is licensed under the **GNU General Public License version 3 only** (SPDX: `GPL-3.0-only`). See [LICENSE](LICENSE) for the complete terms. This is strong copyleft: people may use, modify, redistribute, and sell copies, but anyone conveying a modified version must provide the corresponding source under GPL-3.0.

The inherited UVB-76 overlay artwork and information-panel material retain the Unlicense terms under which they were obtained. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for the component boundaries and other third-party notices.

This change applies to the current version and future releases. Previously published versions remain under the licenses that accompanied them; changing the current license does not retroactively revoke permissions granted for older releases.

