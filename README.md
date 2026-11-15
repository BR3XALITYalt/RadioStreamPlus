<p align="center">
  <img src="assets/radiostreamplus-banner.svg" alt="RadioStream+" />
</p>

RadioStream+ is a radio receiver manager and transparent OBS overlay. Find public KiwiSDR and OpenWebRX receivers, tune to a signal, and keep the frequencies you monitor in named presets.

## Features

- Map-based receiver discovery with frequency and distance filtering.
- KiwiSDR playback with automatic receiver rotation.
- Public Receiverbook listings and your own OpenWebRX instance list.
- Named frequency presets for signals such as WWV, the Pip, and the buzzer.
- A transparent information overlay for OBS.

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

An experimental Windows x64 launcher is available in the [continuous pre-release](https://github.com/BR3XALITYalt/RadioStreamPlus/releases/download/continuous/RadioStreamPlus.exe). It includes its own Python runtime, downloads the current source from GitHub, and runs that source locally. After a successful online launch, it keeps a source cache and can start from that cache when GitHub is unavailable. The first launch needs an internet connection unless a source cache is already present.

The executable stores settings, presets, preferences, and other application data in `%LOCALAPPDATA%\RadioStreamPlus\data`, separately from the downloaded application files. This executable is experimental; the Python launcher remains available above.

## Pages

| Page | Address |
|---|---|
| Management | [localhost:5056/](http://localhost:5056/) |
| OBS overlay | [localhost:5056/overlay](http://localhost:5056/overlay) |
| KiwiSDR player | [localhost:5056/sdr](http://localhost:5056/sdr) |

Keep RadioStream+ running while using these pages. It is designed to run locally on the computer running OBS.

## Documentation

The [RadioStream+ Wiki](wiki/main.md) contains the getting-started guide, management instructions, receiver discovery notes, configuration reference, API reference, troubleshooting, development information, and the full page directory.

## License

The main RadioStream+ application is licensed under **GPL-3.0-only**. Some inherited overlay material retains separate terms. See [LICENSE](LICENSE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
