# Third-party notices

## UVB-76 information overlay

The overlay artwork and original information panel were adapted from [chfour/uvbinfobar](https://github.com/chfour/uvbinfobar). The upstream repository's `LICENSE` declares the Unlicense. The adapted overlay files retain that permissive licensing.

## Kiwi-Reload

[noaa-apt/kiwi-reload](https://github.com/noaa-apt/kiwi-reload) is a GPL-3.0-licensed project with automatic KiwiSDR receiver rotation, receiver status ranking, and frequency/receiver settings. RadioStream+ implements its own local server and receiver-selection logic; it does not copy or bundle Kiwi-Reload source files. Kiwi-Reload is acknowledged as the reference implementation for the rotation feature.

## KiwiSDR public receiver directory

Receiver discovery uses the public JSON mirror documented by [AetherSDR](https://github.com/aethersdr/AetherSDR/blob/main/docs/kiwi-json-schema.md): `https://cdn.aethersdr.com/kiwi.json`. Directory metadata is used as published; receiver operators control their own devices and may change availability or access rules at any time.

## Map tiles

The management page uses [Leaflet](https://leafletjs.com/) and [OpenStreetMap](https://www.openstreetmap.org/) tiles. OpenStreetMap attribution is displayed in the map. Tile usage is subject to the [OpenStreetMap tile usage policy](https://operations.osmfoundation.org/policies/tiles/).