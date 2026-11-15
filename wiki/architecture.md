# Architecture

**Navigation:** [Wiki home](main.md) · [Development](development.md) · [API Reference](api-reference.md) · [Privacy](privacy.md)

RadioStream+ is a small Python application with a browser-based management interface, a KiwiSDR player, and an OBS overlay.

## Components

| File | Responsibility |
|---|---|
| `radiostream.py` | Launcher and application updater |
| `radiostream_server.py` | Local HTTP server, API routes, current receiver, and rotation |
| `radiostream_core.py` | Settings validation, receiver directory handling, map filtering, frequency parsing, and local data files |
| `manage.html` | Management interface, map, source controls, and radio presets |
| `sdr.html` | KiwiSDR browser player |
| `index.html` | Transparent OBS information overlay |
| `app.js` | Overlay client-side behavior |
| `maintenance.js` and `m.html` | Update maintenance screen and page handling |
| `tests/test_radiostream.py` | Automated Python tests |

## Request flow

1. The browser loads the management page from the local server.
2. The page reads and saves settings through the local API.
3. Discovery retrieves cached or refreshed directory records.
4. The core module filters records by location and frequency.
5. The server returns matching records to the page for display on the map and in the result lists.
6. When a KiwiSDR is selected, the server updates the current receiver state. The SDR player reads that state and opens the receiver.
7. The rotation timer selects another eligible KiwiSDR when the configured interval expires.

OpenWebRX links are generated from the selected frequency and mode and open directly in a new browser tab. They are not routed through the KiwiSDR player.

## Local state

General settings, station preferences, custom OpenWebRX entries, radio presets, and directory caches are each stored in separate local files.

See [Configuration](configuration.md) for the complete data-file list.
