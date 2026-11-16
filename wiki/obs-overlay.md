# OBS Overlay

**Navigation:** [Wiki home](main.md) · [Getting Started](getting-started.md) · [Configuration](configuration.md)

RadioStream+ provides the two browser sources used to build its OBS livestream scene: the SDR player, which supplies the selected KiwiSDR's picture and audio, and a transparent 1920 × 1080 information overlay with clocks and HF propagation details. Add both to OBS, arrange them into a scene, then let OBS handle encoding and broadcasting to YouTube or another platform. RadioStream+ does not directly publish a livestream.

## Add the information overlay

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

The reload message supports the `${M}` placeholder, which is replaced by the configured receiver rotation interval in minutes. Changes to the messages or rotation interval are reflected in the overlay automatically.

The overlay also shows a **Time until next reload** countdown. It follows the server's active receiver timer and updates once per second. The countdown waits when no receiver is selected; keep the SDR player running for automatic receiver rotation.

## Add the SDR player

Add another Browser Source for the actual receiver feed:

- URL: `http://localhost:5056/sdr`

Enable browser-source audio capture in OBS so the receiver audio is included in the broadcast. The player automatically follows the selected KiwiSDR receiver and its rotations. Place this source below or above the information overlay as needed for your scene.

## Go live

Once both sources are arranged, configure your normal OBS streaming output and start the broadcast from OBS. Keep RadioStream+ running for as long as the Browser Sources need to load and update. OBS, not RadioStream+, handles the connection to YouTube or your chosen streaming service.
