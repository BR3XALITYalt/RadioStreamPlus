# Development

**Navigation:** [Wiki home](main.md) · [Architecture](architecture.md) · [API Reference](api-reference.md) · [Licensing](licensing.md)

## Source layout

The main application is intentionally small:

- `radiostream.py`: updater and process launcher.
- `radiostream_server.py`: local HTTP server and state management.
- `radiostream_core.py`: receiver discovery and shared application logic.
- `manage.html`: management interface.
- `index.html` and `app.js`: OBS overlay.
- `sdr.html`: KiwiSDR player.
- `tests/test_radiostream.py`: unit tests.

## Requirements

Python 3.10 or newer is recommended. The application server uses Python's standard library. The browser interface loads Leaflet and OpenStreetMap resources from their public services.

## Run tests

From the project root:

```sh
python -m unittest discover -s tests -v
```

The tests cover configuration and preset validation, receiver parsing, directory handling, tuning URLs, frequency-range parsing, and persistence of custom receiver lists and radio presets.

## Update behavior

The launcher checks the public `main` branch for changes on a two-minute interval. It verifies downloaded files against their Git blob SHA-1 values before installing them.

The launcher has an explicit allowlist of application files. It does not replace user data such as configuration, caches, preferences, custom OpenWebRX instances, or radio presets. The launcher itself is not self-updated by this mechanism.

The `wiki/` directory and the test suite are repository documentation and development resources, not runtime application files.

## Contribution guidelines

- Keep the application small and avoid adding frameworks or services without a clear need.
- Preserve existing user data when changing configuration schemas.
- Validate data at the server boundary, not only in the browser.
- Keep public receiver URL handling restricted to public addresses.
- Add regression tests for new parsing, persistence, and validation behavior.
- Update the relevant wiki page when adding user-facing functionality.
