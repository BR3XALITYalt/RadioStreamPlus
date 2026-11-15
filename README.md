<p align="center">
  <img src="assets/radiostreamplus-banner.svg" alt="RadioStream+" />
</p>

RadioStream+ helps you build continuous radio-monitoring livestreams using public internet SDR receivers. It finds KiwiSDR receivers that cover a selected frequency, tunes them, and can rotate playback between eligible receivers. Its local SDR player and information overlay are designed to be added to an OBS scene, which you can broadcast to YouTube or another streaming platform.

The project is intended for broadcasts such as long-running UVB-76 monitoring streams: keep a signal on air, move between suitable public receivers, and show useful receiver and propagation information to viewers.

## How it fits together

1. **Choose a signal.** Set the frequency, demodulation mode, and search area.
2. **Find receivers.** RadioStream+ locates public KiwiSDR receivers whose published frequency coverage includes the signal.
3. **Keep the feed moving.** Select a receiver and let automatic rotation move playback between eligible KiwiSDRs on the configured interval.
4. **Build the scene in OBS.** Add the local SDR player and information overlay as Browser Sources. Capture browser-source audio from the SDR player.
5. **Go live with OBS.** OBS handles the scene, encoding, and broadcast to YouTube or another platform. RadioStream+ supplies the receiver player and overlay; it does not upload the livestream itself.

## Features

- Map-based discovery of public KiwiSDR receivers with distance and frequency filtering.
- Automatic rotation between eligible KiwiSDR receivers for long-running monitoring streams.
- Frequency, demodulation mode, zoom, passband, and volume controls.
- Like, dislike, and block preferences to influence receiver selection.
- A local SDR player designed to be captured in OBS, including receiver audio.
- A transparent 1920 × 1080 OBS overlay with clocks, HF propagation information, and configurable viewer notices.
- Public Receiverbook listings and custom OpenWebRX instances. OpenWebRX entries open directly in a separate browser tab; they are not part of KiwiSDR rotation.
- Saved frequency and mode presets.

For a first livestream setup, see the [Getting Started guide](wiki/getting-started.md) and [OBS Overlay guide](wiki/obs-overlay.md).

## Getting started

Python 3.10 or newer is recommended.

**Windows**

```powershell
py radiostream.py
```

**macOS / Linux**

```sh
python3 radiostream.py
```

Open the management page at **http://localhost:5056/**.

## Windows executable

An experimental Windows x64 launcher is available in the [continuous pre-release](https://github.com/BR3XALITYalt/RadioStreamPlus/releases/download/continuous/RadioStreamPlus.exe), or as the [latest Windows executable package](https://nightly.link/BR3XALITYalt/RadioStreamPlus/workflows/continuous-prerelease.yml/main/windows-executable.zip) through nightly.link. The package contains the executable. It includes its own Python runtime, downloads the current source from GitHub, and runs that source locally. After a successful online launch, it keeps a source cache and can start from that cache when GitHub is unavailable. The first launch needs an internet connection unless a source cache is already present.

The executable stores settings, presets, preferences, and other application data in `%LOCALAPPDATA%\RadioStreamPlus\data`, separately from the downloaded application files. This executable is experimental; the Python launcher remains available above.

## Local pages

| Page | Address |
|---|---|
| Management | [localhost:5056/](http://localhost:5056/) |
| SDR player for OBS | [localhost:5056/sdr](http://localhost:5056/sdr) |
| OBS information overlay | [localhost:5056/overlay](http://localhost:5056/overlay) |

Keep RadioStream+ running while OBS uses these pages as Browser Sources. The application runs locally on the computer producing the livestream.

## Documentation

The [RadioStream+ Wiki](wiki/main.md) contains the getting-started guide, management instructions, receiver discovery notes, configuration reference, API reference, troubleshooting, development information, and the full page directory.

## License

The main RadioStream+ application is licensed under **GPL-3.0-only**. Some inherited overlay material retains separate terms. See [LICENSE](LICENSE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
