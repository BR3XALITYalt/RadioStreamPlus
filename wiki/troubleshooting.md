# Troubleshooting

**Navigation:** [Wiki home](main.md) · [Getting Started](getting-started.md) · [Management Page](management.md) · [Privacy](privacy.md)

## The server does not start

- Confirm Python 3.10 or newer is installed.
- Run the launcher from the project directory.
- Read the terminal output for the actual error.
- Check whether another application is already using port 5056.

Windows launch command: `py radiostream.py`

macOS / Linux launch command: `python3 radiostream.py`

## The management page does not open

Confirm that RadioStream+ is still running. Open `http://localhost:5056/` on the same computer. The server binds to the loopback interface and is not reachable from another device on the network.

## The map is blank

The map uses public OpenStreetMap tiles and Leaflet. Check the internet connection and browser developer console for blocked tile or script requests. The map may not render if a network filter blocks those services.

## No KiwiSDR receivers appear

- Move the map center closer to the area you want to search.
- Increase the search radius.
- Check that the frequency is inside the receivers' published frequency bands.
- Use **Refresh directory** to request fresh listings.
- If the public directory is unavailable, the application may use its cached copy.

A receiver listed as available can still reject playback. The directory is a snapshot, not a live connection guarantee.

## No OpenWebRX receivers appear

- Confirm that at least one source checkbox is enabled.
- Check that the map radius includes the receiver's coordinates.
- Check that the selected frequency is covered by an advertised profile or band.
- For custom entries, verify the URL and coordinates.
- A receiver with unreadable status information is excluded from the result list.

## An OpenWebRX receiver rejects the tuning link

OpenWebRX+ may accept tuning only inside its currently active profile. The directory check can detect multiple advertised profiles, but the generated link does not switch the receiver's active profile. Try a frequency in the currently active profile or contact the receiver operator.

## A radio preset does not appear

Confirm that **Save preset** reported success. Presets are saved to `radio_presets.json`. Restarting the application should reload the list from that file. Saving a preset with the same name updates the existing preset.

## The OBS overlay is missing or opaque

- Confirm RadioStream+ is running.
- Use `http://localhost:5056/overlay` as the Browser Source URL.
- Set the Browser Source dimensions to 1920 × 1080.
- Keep the Browser Source background transparent.
- Check OBS Browser Source logs for network or script errors.

## Propagation data is unavailable

The solar feed is retrieved by the local server and cached. HamQSL refreshes are limited to once per hour. A valid cached response can be used when the live feed is unavailable.
