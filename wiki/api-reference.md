# Local API Reference

**Navigation:** [Wiki home](main.md) · [Architecture](architecture.md) · [Configuration](configuration.md) · [Development](development.md)

The local HTTP API is used by the management page, the overlay, and the SDR player. It is intended for the local application only.

Base address: `http://127.0.0.1:5056`

## Read endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/state` | Current receiver, timing, and settings |
| GET | `/api/config` | Saved general settings |
| GET | `/api/discover` | Search KiwiSDR and enabled OpenWebRX sources |
| GET | `/api/openwebrx/custom` | List custom OpenWebRX instances |
| GET | `/api/presets` | List saved radio presets |
| GET | `/api/solar` | Retrieve the cached or refreshed propagation feed |
| GET | `/api/health` | Basic local server status |
| GET | `/api/maintenance` | Updater maintenance state |

## Write endpoints

POST requests use a JSON object as the request body.

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/config` | Validate and save general settings, including the numeric `frequencies_khz` rotation list |
| POST | `/api/openwebrx/custom` | Add or update a custom OpenWebRX instance |
| POST | `/api/openwebrx/custom/delete` | Remove a custom OpenWebRX instance by ID |
| POST | `/api/presets` | Save a radio preset; saving an existing name updates it |
| POST | `/api/presets/delete` | Remove a radio preset by ID |
| POST | `/api/preference` | Set or clear a KiwiSDR station preference |
| POST | `/api/select` | Select a specific available KiwiSDR receiver |
| POST | `/api/next` | Move to the next KiwiSDR receiver |
| POST | `/api/refresh-directory` | Refresh public receiver directories |

## Request limits and errors

JSON request bodies are limited to 64 KiB. Invalid input returns an HTTP error and a JSON object containing an `error` message. The API rejects cross-origin requests and requests addressed to hosts other than localhost or 127.0.0.1.

These endpoints are used by the local RadioStream+ pages and are only available on the computer running the application. Endpoint details may change between releases.
