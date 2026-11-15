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
