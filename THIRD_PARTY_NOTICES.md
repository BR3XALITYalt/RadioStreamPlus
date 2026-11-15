# Third-party notices

## UVB-76 information overlay

The overlay artwork and original information panel were adapted from [chfour/uvbinfobar](https://github.com/chfour/uvbinfobar). The upstream repository's `LICENSE` declares the Unlicense. The inherited overlay material retains that permissive licensing and is not relicensed by the RadioStream+ GPL-3.0-only license. The Unlicense is compatible with the GNU GPL, so this separately licensed material can coexist in the project.

## Kiwi-Reload

[noaa-apt/kiwi-reload](https://github.com/noaa-apt/kiwi-reload) is licensed under GPL-3.0 and provided a reference for automatic KiwiSDR receiver rotation, receiver status ranking, and frequency/receiver settings. RadioStream+ currently implements its own local server and receiver-selection logic; it does not copy or bundle Kiwi-Reload source files. If source code from Kiwi-Reload is incorporated in a future version, its copyright and license notices must be preserved and the combined work distributed in compliance with GPL-3.0.

## KiwiSDR public receiver directory

Receiver discovery uses the public JSON mirror documented by [AetherSDR](https://github.com/aethersdr/AetherSDR/blob/main/docs/kiwi-json-schema.md): `https://cdn.aethersdr.com/kiwi.json`. Directory metadata is used as published; receiver operators control their own devices and may change availability or access rules at any time.

## Map tiles

The management page uses [Leaflet](https://leafletjs.com/) and [OpenStreetMap](https://www.openstreetmap.org/) tiles. OpenStreetMap attribution is displayed in the map. Tile usage is subject to the [OpenStreetMap tile usage policy](https://operations.osmfoundation.org/policies/tiles/).
