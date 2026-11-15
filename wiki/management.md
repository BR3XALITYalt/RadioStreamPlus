# Management Page

**Navigation:** [Wiki home](main.md) · [Getting Started](getting-started.md) · [Receiver Discovery](receiver-discovery.md) · [Radio Presets](radio-presets.md)

The management page is available at `http://localhost:5056/`. It contains the receiver map, radio settings, discovery results, OpenWebRX source controls, and saved presets.

## Map and search area

The map uses Leaflet with OpenStreetMap tiles.

- Click the map to move the search center.
- Drag the center marker to reposition it.
- Change **Search range (km)** to control the maximum distance from the center.
- **Use browser location** asks the browser for a location fix and moves the center marker. The browser displays its normal permission prompt.
- **Find receivers in range** saves the current settings and searches the enabled receiver sources.
- **Refresh directory** requests fresh directory data instead of relying only on the current cache.

The map legend distinguishes available and unavailable KiwiSDR entries from OpenWebRX entries. OpenWebRX markers use the same style regardless of whether they came from Receiverbook or your custom list; their source is shown in the result card.

## Radio settings

The main settings include:

| Setting | Purpose |
|---|---|
| Frequency | Frequency to search and tune, with Hz, kHz, MHz, and GHz entry units |
| Demodulation mode | AM, LSB, USB, CW, or NBFM |
| KiwiSDR zoom | Waterfall zoom value applied when opening KiwiSDR |
| Rotation interval | Time spent on a KiwiSDR receiver before automatic rotation |
| KiwiSDR volume | Player volume value |
| Passband low / high | Passband edges in Hz relative to the carrier |
| Overlay messages | Custom text displayed in the OBS overlay |

The **Save settings** button writes the settings to `radiostream.json`.

## Receiver results

KiwiSDR result cards show directory availability, distance, HF SNR, occupancy, and preference controls. A station can be liked, disliked, or blocked. Those preferences affect KiwiSDR rotation and selection.

OpenWebRX cards provide an **Open at selected frequency** link. OpenWebRX does not participate in KiwiSDR's automatic rotation.

## OpenWebRX source controls

The two checkboxes independently control discovery sources:

- **Include public Receiverbook listings** adds public OpenWebRX entries from Receiverbook.
- **Include your custom instances** adds entries stored in your personal custom list.

Disable either source to hide its results without deleting its saved records. Disable both to temporarily hide all OpenWebRX entries.

The **Your OpenWebRX instances** section lets you add or remove custom receivers. Each entry needs a public HTTP or HTTPS receiver URL and map coordinates. Use **Use map pin for coordinates** after moving the map to the receiver's location, or enter latitude and longitude manually.

## Radio presets

The **Radio presets** section saves the current frequency, mode, and passband under a name. Select a saved preset and load it to apply those tuning settings. See [Radio Presets](radio-presets.md) for details.
