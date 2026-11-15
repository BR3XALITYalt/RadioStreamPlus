# OBS Overlay

**Navigation:** [Wiki home](main.md) · [Getting Started](getting-started.md) · [Configuration](configuration.md)

RadioStream+ includes a transparent 1920 × 1080 information overlay designed for use as an OBS Browser Source.

## Add the overlay

1. Start RadioStream+.
2. In OBS, add a **Browser Source**.
3. Set the URL to `http://localhost:5056/overlay`.
4. Set the width to `1920` and height to `1080`.
5. Keep the Browser Source background transparent.

The overlay can run independently from the management page. Keep the RadioStream+ process running while the Browser Source is in use.

## Overlay content

The overlay includes the UTC clock, a configurable local-time clock, and an HF propagation information panel.

The local-time clock opens its settings when clicked. The information panel uses data retrieved by the local server and cached between refresh attempts.

## Custom messages

The management page includes two editable overlay messages:

- **Automatic receiver reload notice** explains the periodic receiver reload.
- **Black-screen warning** tells viewers what to expect if the receiver window remains black.

The reload message supports the `${M}` placeholder, which is replaced by the configured receiver rotation interval in minutes. Both messages support line breaks and up to eight lines.

## Add the SDR player separately

When the KiwiSDR picture and sound should appear in the OBS scene, add a second Browser Source:

- URL: `http://localhost:5056/sdr`

Enable browser-source audio capture in OBS when receiver audio is needed. The player automatically follows the selected KiwiSDR receiver and its rotations.
