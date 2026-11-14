# RadioStream+

RadioStream+ is a local KiwiSDR receiver manager, player, and transparent OBS information overlay. It discovers publicly listed KiwiSDR receivers by their published GPS coordinates, finds stations inside a user-selected area, chooses a suitable receiver for the configured frequency, and rotates to another receiver at a configurable interval.

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

## Find receivers on the map

1. Click the map to place the search center, or drag the center pin.
2. Set the search range in kilometers.
3. Optionally use **Use browser location** to ask the browser to move the pin to the computer's current location. This is optional; RadioStream+ does not request location permission on its own.
4. Set the frequency and mode, then choose **Find receivers in range**.
5. Select an available receiver. The SDR player at `/sdr` loads it.

The map uses Leaflet and OpenStreetMap tiles. Map data is fetched from OpenStreetMap's public tile service and attribution is shown in the map. Internet access is required for the map tiles.

## Radio settings

The management page and `radiostream.json` support:

- `center_lat`, `center_lon`: center pin coordinates.
- `radius_km`: discovery range, from 1 to 20,000 km.
- `frequency_khz`: tuned frequency in kHz, from 10 to 30,000 kHz.
- `mode`: `am`, `lsb`, `usb`, `cw`, or `nbfm`.
- `zoom`: KiwiSDR waterfall zoom, applied to every receiver when it is opened (0–14).
- `volume`: KiwiSDR volume value (0–200).
- `passband_low`, `passband_high`: KiwiSDR passband edges in Hz.
- `rotation_minutes`: how long to stay on a receiver before switching (3–60 minutes; default 14).

Frequency, mode, zoom, volume, and passband settings are applied consistently when switching between receivers.

## Receiver discovery and rotation

RadioStream+ downloads the schema-1 public receiver list from the AetherSDR KiwiSDR directory mirror at `https://cdn.aethersdr.com/kiwi.json`. The directory's published cache window is 30 minutes; RadioStream+ respects that and keeps a local cache in `kiwi_directory_cache.json` so a temporary directory outage does not immediately erase the map. The mirror's `fetched_at` timestamp is shown in the management page.

Receiver locations are read from the directory's `gps` coordinate pair. Receivers without a valid GPS fix, outside the selected radius, outside the configured frequency band, marked offline, flagged by the directory, or listed as full are not selected for playback. The map may still show a receiver marked unavailable so its published location remains visible.

Available receivers are ranked using the directory's published HF SNR and occupancy snapshot. The player cycles through the ranked receivers and avoids recently used stations where possible. The directory is a cached public listing, not a real-time guarantee: receiver availability can change after the listing was generated, and an individual receiver may stop accepting connections without warning.

The `ext_api` directory field governs non-browser external-API connections. RadioStream+ opens the regular KiwiSDR web interface in a browser frame, not the KiwiSDR native external API, so it does not filter web-only receivers based on that field.

## Use in OBS

1. Start RadioStream+ with the Python command above.
2. In OBS, add a **Browser Source**.
3. Set its URL to `http://localhost:5056/overlay`.
4. Set width to `1920` and height to `1080`.
5. Keep the Browser Source background transparent.

Add a separate Browser Source at `http://localhost:5056/sdr` when the KiwiSDR player should be part of the OBS scene. Enable browser-source audio capture in OBS if you want to capture the receiver audio through that source. You can also open `/sdr` in a regular browser.

The overlay retains the UTC clock, configurable local-time clock, and HF propagation panel. The local-time clock opens its settings when clicked. HamQSL XML is now retrieved through the local Python server at `/api/solar`, avoiding the direct-browser CORS dependency from the earlier standalone version.

## Data, privacy, and limitations

- The server listens only on the local loopback interface (`127.0.0.1`).
- The optional browser geolocation action sends its coordinates only to the local RadioStream+ server, where they are saved in `radiostream.json`.
- The public KiwiSDR directory request goes to the AetherSDR mirror. Receiver selection and playback then load the chosen public KiwiSDR website directly in the browser frame.
- The map uses OpenStreetMap tiles through its public tile service. Follow the [OpenStreetMap tile usage policy](https://operations.osmfoundation.org/policies/tiles/) for high-volume or redistributed deployments.
- RadioStream+ does not bypass a receiver's own password, connection limit, idle timeout, or other access rules. A selected receiver can still refuse or terminate a connection.
- The receiver directory is cached and may lag real-world availability. Rotation is based on the published snapshot and is not a promise that every station will accept a connection.
- Internet access is needed for the KiwiSDR directory, OSM map tiles, HamQSL propagation data, and remote receivers.

## Project origin and licensing

The information overlay was adapted from [chfour/uvbinfobar](https://github.com/chfour/uvbinfobar), whose upstream project is released under the Unlicense. KiwiSDR rotation behavior was implemented for RadioStream+ using the public receiver metadata and the feature approach documented by [noaa-apt/kiwi-reload](https://github.com/noaa-apt/kiwi-reload). RadioStream+ does not bundle Kiwi-Reload's source code. The relevant upstream Kiwi-Reload project is GPL-3.0 licensed.

See [UPSTREAM.md](UPSTREAM.md) for the overlay attribution and [LICENSE](LICENSE) for the overlay's Unlicense terms.