# Getting Started

**Navigation:** [Wiki home](main.md) · [Management Page](management.md) · [Configuration](configuration.md)

## Requirements

- Windows, macOS, or Linux.
- Python 3.10 or newer.
- An internet connection for receiver directories, map tiles, propagation data, and remote receivers.

RadioStream+ uses Python's standard library for its local server. The management map loads Leaflet and OpenStreetMap tiles from their public services.

## Start RadioStream+

Open a terminal in the project directory.

**Windows**

```powershell
py radiostream.py
```

**macOS / Linux**

```sh
python3 radiostream.py
```

Then open:

- [Management page](http://localhost:5056/)
- [OBS overlay](http://localhost:5056/overlay)
- [SDR player](http://localhost:5056/sdr)

The launcher starts the local server and checks the project's public `main` branch for application updates. Keep the terminal or process running while using the pages.

## First run

The first start creates `radiostream.json` beside the application files. The application also creates local data files as needed for receiver caches, preferences, custom OpenWebRX entries, and radio presets.

Open the management page and:

1. Set the map center by clicking the map or dragging the center pin.
2. Set a search range.
3. Enter a frequency and demodulation mode.
4. Select **Find receivers in range**.
5. Select an available KiwiSDR receiver or open an OpenWebRX entry in a separate tab.

You can save the current frequency and mode as a named preset. See [Radio Presets](radio-presets.md).

## Stop the application

Stop the launcher with Ctrl+C in the terminal. The local server and its pages will no longer be available until it is started again.

## Where to go next

- [Management Page](management.md) explains the controls.
- [Receiver Discovery](receiver-discovery.md) explains how the map is populated.
- [OBS Overlay](obs-overlay.md) explains how to add the overlay to a scene.
- [Troubleshooting](troubleshooting.md) covers common startup and connection problems.
