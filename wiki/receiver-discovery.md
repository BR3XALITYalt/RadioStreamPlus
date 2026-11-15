# Receiver Discovery

**Navigation:** [Wiki home](main.md) · [Management Page](management.md) · [KiwiSDR](kiwisdr.md) · [OpenWebRX](openwebrx.md)

RadioStream+ searches receiver listings around the center pin on the management map. The search range applies to both KiwiSDR and OpenWebRX entries.

## KiwiSDR directory

KiwiSDR discovery uses the public JSON mirror provided by AetherSDR. Receiver coordinates, advertised frequency coverage, availability flags, HF SNR, and occupancy information are taken from that directory.

The map can show unavailable KiwiSDR entries when their coordinates are valid. Receiver selection excludes entries that are outside the search radius, have invalid coordinates, do not cover the selected frequency, are marked offline or flagged, or are listed as full.

The directory is a published snapshot, not a live connection test. A receiver may stop accepting connections after the snapshot was generated. RadioStream+ performs an additional receiver-page check before selecting a station for playback.

## OpenWebRX directories

OpenWebRX discovery combines the enabled sources:

1. Receiverbook's public OpenWebRX map listings.
2. The user's saved custom OpenWebRX list.

The sources can be toggled independently in the management page. If the same URL exists in both sources, the custom entry takes precedence so its manually supplied name and coordinates are used.

Each candidate must be within the map radius and have an advertised frequency range that covers the selected frequency. Instances whose frequency information cannot be read are not shown. Range information is cached to avoid repeatedly requesting status endpoints.

OpenWebRX entries are opened in a separate browser tab and are not included in KiwiSDR receiver rotation.

## Map coordinates

- KiwiSDR coordinates come from the AetherSDR directory's GPS pair.
- Receiverbook coordinates come from its map data.
- Custom OpenWebRX coordinates are entered by the user.

The map uses latitude and longitude in decimal degrees. Coordinates at 0, 0 are rejected because that location is commonly an accidental placeholder.

## Search tips

- Increase the radius when the map is empty.
- Verify that the entered frequency is within the receiver's advertised band.
- Make sure the map center is near the receiver locations you want.
- Check whether one or both OpenWebRX sources are enabled.
- Use the directory refresh control if the public listings appear stale.

See [Troubleshooting](troubleshooting.md) if results still look wrong.
