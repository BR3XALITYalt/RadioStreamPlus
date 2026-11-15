# Privacy and Network Behavior

**Navigation:** [Wiki home](main.md) · [Configuration](configuration.md) · [Architecture](architecture.md) · [Troubleshooting](troubleshooting.md)

RadioStream+ runs a local server and requests public receiver, map, and propagation data.

## Local server

The HTTP server binds to `127.0.0.1` on port `5056`. It is intended for use on the computer running RadioStream+, not as a public web server.

The server checks the Host and Origin headers on requests. Requests addressed to other hosts or from non-local origins are rejected.

## External services

Depending on the features being used, RadioStream+ contacts:

| Service | Purpose |
|---|---|
| AetherSDR public directory mirror | KiwiSDR receiver listings and metadata |
| Receiverbook | Public OpenWebRX map listings |
| Custom OpenWebRX hosts | Read public status endpoints to learn frequency coverage; the browser opens the selected receiver |
| OpenStreetMap tile service | Map tiles displayed through Leaflet |
| HamQSL | Solar and HF propagation information |
| GitHub | Launcher checks for application updates |

The management map also loads Leaflet from the configured public content delivery network.

## Location

Browser location is optional. The browser asks for permission when **Use browser location** is selected. The resulting coordinates are sent to the local RadioStream+ server and saved as the map center in `radiostream.json`.

Custom OpenWebRX coordinates are entered by the user and saved in `openwebrx_custom.json`.

## Custom receiver URLs

Custom OpenWebRX URLs must use HTTP or HTTPS and must not contain embedded usernames or passwords. Localhost, private, and reserved address targets are rejected. During frequency-range checks, the server resolves the hostname and rejects non-public addresses; redirects are checked too.

A custom receiver is still an independently operated public service. Its operator controls access, availability, logging, and connection limits.

## Local files

Configuration, presets, station preferences, receiver lists, and caches are stored on the computer running RadioStream+. RadioStream+ does not synchronize these files to a cloud account.

## Limitations

RadioStream+ does not bypass receiver passwords, connection limits, idle timeouts, or other access restrictions. A public directory listing does not guarantee that a receiver will accept a connection.
