# RadioStream+ Wiki

RadioStream+ is built to make continuous radio-monitoring livestreams easier to set up and keep running. It finds public KiwiSDR receivers for a selected signal, tunes the player, and can rotate between eligible receivers automatically. Add the local SDR player and information overlay to OBS, then use OBS to broadcast the scene to YouTube or another platform.

It is designed for streams such as long-running UVB-76 monitoring broadcasts. RadioStream+ manages the receiver feed and on-screen information; OBS handles the actual livestream output.

This wiki covers setup, receiver discovery and rotation, OBS configuration, application settings, and reference material.

## Start here

| Page | Description |
|---|---|
| [Getting Started](getting-started.md) | Set up a radio-monitoring feed and connect it to OBS |
| [Management Page](management.md) | Map, settings, discovery, and receiver controls |
| [Radio Presets](radio-presets.md) | Save and switch between named frequencies and modes |

## Everyday use

| Page | Description |
|---|---|
| [Receiver Discovery](receiver-discovery.md) | Search radius, frequency filtering, directory sources, and map markers |
| [KiwiSDR](kiwisdr.md) | The main livestream feed, receiver selection, playback, and automatic rotation |
| [OpenWebRX](openwebrx.md) | Receiverbook listings, custom instances, and tuning links |
| [OBS Setup](obs-overlay.md) | Add the SDR player and information overlay to an OBS scene |

## Reference

| Page | Description |
|---|---|
| [Configuration](configuration.md) | Settings, saved data files, and supported values |
| [Local API Reference](api-reference.md) | Local HTTP endpoints used by the management interface |
| [Architecture](architecture.md) | Application components and how they fit together |
| [Privacy and Network Behavior](privacy.md) | Local binding, external services, and data handling |
| [Troubleshooting](troubleshooting.md) | Common problems and practical checks |
| [Development](development.md) | Source layout, tests, and contribution notes |
| [Licensing and Notices](licensing.md) | Project license and third-party components |
| [Glossary](glossary.md) | Radio and project terminology |

## Project links

- [Source repository](https://github.com/BR3XALITYalt/RadioStreamPlus)
- [Issue tracker](https://github.com/BR3XALITYalt/RadioStreamPlus/issues)
- [License](../LICENSE)
- [Third-party notices](../THIRD_PARTY_NOTICES.md)

---

**Navigation:** [Wiki home](main.md) · [Getting Started](getting-started.md) · [Management](management.md) · [Presets](radio-presets.md) · [Troubleshooting](troubleshooting.md)
