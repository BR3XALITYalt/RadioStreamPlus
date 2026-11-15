# Configuration

**Navigation:** [Wiki home](main.md) · [Management Page](management.md) · [Radio Presets](radio-presets.md) · [API Reference](api-reference.md)

RadioStream+ stores its general settings in `radiostream.json`. The management page is the recommended way to change them. The file can also be edited while RadioStream+ is stopped.

## General settings

| Key | Meaning | Accepted values |
|---|---|---|
| `center_lat` | Map search center latitude | -90 to 90 |
| `center_lon` | Map search center longitude | -180 to 180 |
| `radius_km` | Receiver search radius | 1 to 20,000 km |
| `frequency_khz` | Current frequency used for tuning | 0.001 to 300,000,000 kHz (1 Hz to 300 GHz) |
| `frequencies_khz` | Numeric frequencies shuffled during receiver rotation | 1 to 32 unique values, each 0.001 to 300,000,000 kHz |
| `mode` | Demodulation mode | `am`, `lsb`, `usb`, `cw`, `nbfm` |
| `zoom` | KiwiSDR waterfall zoom | Integer 0 to 14 |
| `volume` | KiwiSDR player volume | Integer 0 to 200 |
| `passband_low` | Lower passband edge relative to carrier | Integer -12,000 to 12,000 Hz |
| `passband_high` | Upper passband edge relative to carrier | Integer -12,000 to 12,000 Hz |
| `rotation_minutes` | Time between KiwiSDR rotations | 3 to 60 minutes |
| `openwebrx_receiverbook_enabled` | Include Receiverbook in OpenWebRX discovery | Boolean |
| `openwebrx_custom_enabled` | Include saved custom OpenWebRX instances | Boolean |

The passband low value must be smaller than the high value.

## Default passbands

Changing the mode selector in the management page fills the passband fields with the following defaults. Both values can be edited afterward.

| Mode | Low (Hz) | High (Hz) |
|---|---:|---:|
| AM | -4900 | 4900 |
| LSB | -2700 | -300 |
| USB | 300 | 2700 |
| CW | 300 | 700 |
| NBFM | -6000 | 6000 |

## Overlay messages

| Key | Meaning |
|---|---|
| `overlay_reload_notice` | Message about periodic receiver reloads |
| `overlay_black_notice` | Message shown when the receiver window stays black |

Each message supports up to 800 characters and eight lines. Line breaks are preserved. The `${M}` placeholder in the reload message is replaced with the configured rotation interval.

## Local data files

These files are created in the application data directory when needed. By default, this is the application directory:

| File | Contents |
|---|---|
| `radiostream.json` | General settings |
| `kiwi_directory_cache.json` | Cached KiwiSDR directory response |
| `receiverbook_cache.json` | Cached Receiverbook records and OpenWebRX frequency ranges |
| `station_preferences.json` | Liked, disliked, and blocked KiwiSDR IDs |
| `openwebrx_custom.json` | Custom OpenWebRX URLs, names, coordinates, and cached ranges |
| `radio_presets.json` | User-created frequency, mode, and passband presets |
| `solar_xml_cache.xml` | Cached propagation feed |

Settings, preferences, presets, custom receiver entries, and directory caches are stored locally. The automatic updater leaves these files intact.

## Example configuration

See [radiostream.example.json](../radiostream.example.json) for a sample settings file. It contains defaults, not personal presets or custom receiver entries.
