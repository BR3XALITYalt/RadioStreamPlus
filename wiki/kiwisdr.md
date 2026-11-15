# KiwiSDR

**Navigation:** [Wiki home](main.md) · [Receiver Discovery](receiver-discovery.md) · [Management Page](management.md) · [Radio Presets](radio-presets.md)

KiwiSDR receivers are the primary playback source for RadioStream+. The local SDR player embeds the selected receiver and follows the server's automatic rotation.

## Selecting a receiver

1. Set a map center and search radius.
2. Enter a frequency and demodulation mode.
3. Select **Find receivers in range**.
4. Choose **Use** on an available KiwiSDR result.

The server rechecks the selected receiver before switching to it. A receiver can still refuse a connection because it may have changed state or reached its own connection limit.

## Automatic rotation

The rotation interval controls how long RadioStream+ stays on a receiver before selecting another one. The interval can be set from 3 to 60 minutes.

Receiver ordering uses the directory's published quality and occupancy information, applies the user's station preferences, and avoids recently used receivers where possible. It is a weighted selection process, not a fixed ranking.

## Station preferences

The three preference controls are:

- **Like:** increases the station's chance of being selected.
- **Dislike:** reduces its chance of being selected.
- **Block:** excludes the station from automatic rotation and manual selection.

Selecting the active preference again clears it. Preferences are stored in `station_preferences.json`.

## Tuning and panel behavior

RadioStream+ applies the saved frequency, mode, zoom, passband, and volume settings when opening a KiwiSDR receiver.

It also uses KiwiSDR's native `keys=x` URL shortcut to hide its panels after the receiver initializes. This hides all KiwiSDR panels, not only Readme and Control. The shortcut may take a few seconds to run.

The player's receiver frame is unloaded after repeated failures to contact the local RadioStream+ server. This disconnects the remote KiwiSDR frame when the local application has stopped.

## Limitations

Directory availability is not a guarantee of a successful connection. Receiver operators control their own devices, access rules, idle timeouts, and connection limits. RadioStream+ does not bypass those rules.
