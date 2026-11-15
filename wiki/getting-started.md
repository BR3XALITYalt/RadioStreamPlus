# Getting Started

**Navigation:** [Wiki home](main.md) · [Management Page](management.md) · [Configuration](configuration.md)

## What you're setting up

RadioStream+ is the receiver and player side of a radio livestream setup. It helps you find public KiwiSDR receivers for a signal, tune the player, and rotate between eligible receivers automatically. You then add two local browser sources to OBS: the SDR player for receiver picture and sound, and the information overlay for clocks and propagation details.

OBS combines those sources into a scene and handles encoding and broadcasting to YouTube or another platform. RadioStream+ does not upload or broadcast to the platform itself. This setup is intended for continuous monitoring streams, including broadcasts focused on signals such as UVB-76.

## Requirements

- Windows, macOS, or Linux.
- Python 3.10 or newer when running from source.
- OBS Studio on the computer that will produce the livestream.
- An internet connection for receiver directories, map tiles, propagation data, remote receivers, and the streaming platform.

RadioStream+ uses Python's standard library for its local server. The management map loads Leaflet and OpenStreetMap tiles from their public services.


## Start from source

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

The launcher starts the local server and checks for application updates automatically. Keep RadioStream+ running while using the pages.

## Build the OBS livestream

1. Start RadioStream+ and open the [management page](http://localhost:5056/).
2. Set the monitoring frequency and demodulation mode, then choose a map center and search radius that cover suitable receivers.
3. Select **Find receivers in range**, then choose **Use** on an available KiwiSDR receiver.
4. In OBS, add a **Browser Source** for the SDR player: `http://localhost:5056/sdr`. Set the source dimensions to suit your scene and enable browser-source audio capture so the receiver audio reaches the stream.
5. Add a second **Browser Source** for the information overlay: `http://localhost:5056/overlay`. Set it to `1920 × 1080` and keep its background transparent.
6. Arrange the sources in your OBS scene, configure OBS streaming output, and start the broadcast from OBS.

Keep RadioStream+ running while OBS uses its local pages. The SDR player follows the selected KiwiSDR and its automatic rotations.

OpenWebRX entries are available as separate tuning links, but they do not participate in the automatic KiwiSDR player rotation.

## First run

On first run, RadioStream+ creates `radiostream.json` for its settings. Receiver caches, preferences, custom OpenWebRX entries, and radio presets are saved locally as you use the application.

Open the management page and set the map center, search radius, frequency, and demodulation mode. Select **Find receivers in range**, then choose an available KiwiSDR receiver with **Use**. The selected receiver becomes the SDR player's current feed.

You can save the current frequency and mode as a named preset. See [Radio Presets](radio-presets.md).

## Stop the application

Stop the launcher with Ctrl+C in the terminal. The local server and its pages will no longer be available until it is started again.

## Where to go next

- [Management Page](management.md) explains the controls.
- [Receiver Discovery](receiver-discovery.md) explains how the map is populated.
- [OBS Setup](obs-overlay.md) explains how to add the SDR player and information overlay to a scene.
- [Troubleshooting](troubleshooting.md) covers common startup and connection problems.
