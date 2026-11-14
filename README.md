# UVB-76 Info Bar

UVB-76 Info Bar is a transparent 1920 × 1080 information overlay for a UVB-76 livestream or radio-monitoring scene. It is designed to sit over another scene in OBS, with the information panel occupying the left side and the rest of the canvas remaining transparent.

The panel displays two clocks, current high-frequency (HF) propagation information, and a small status message when the data feed cannot be reached. It does not receive or play radio audio, decode the UVB-76 signal, or provide a waterfall display. It is an information overlay only.

## What it displays

- **UTC clock:** always shows Coordinated Universal Time.
- **Configurable second clock:** starts in the browser's detected time zone. Its display name and time zone can be changed from the overlay.
- **80m/40m propagation:** daytime and nighttime band conditions reported by HamQSL.
- **Solar flux index (SFI):** the current solar flux value from HamQSL.
- **Noise floor:** the reported signal-noise range, with a simple condition color.
- **Geomagnetic field:** a text description derived from the reported K-index.
- **Feed status:** an error message appears if the data request fails, including the last successful update time.

## Configure the second clock

The second clock uses the browser or OBS browser runtime's local time zone on first launch. It does not default to Moscow.

1. Click the second clock in the overlay.
2. Edit **Location / display name** to change its visible label, such as `Los Angeles` or `Tokyo`.
3. Edit **Time zone** using an IANA time-zone name, such as `America/Los_Angeles`, `Europe/Moscow`, or `Asia/Tokyo`.
4. Select **Done** to apply and save the settings. **Use browser time** restores the detected local time zone. **Cancel**, Escape, or clicking outside the popup closes it without applying unsaved changes.

The clock updates every second and observes daylight-saving changes through the selected IANA time zone. Settings are stored in the browser's local storage when the runtime permits it. If local-file storage is restricted, the clock still works for the current session, but settings may reset when the page reloads.

The settings popup is placed in the otherwise transparent portion of the canvas so it does not cover the information panel. It has no visible edit icon; click the clock itself to open it.

## Use it in OBS

1. Download this repository and extract the files into a permanent folder.
2. In OBS, add a **Browser** source.
3. Enable **Local file** and select `index.html`.
4. Set the Browser source width to `1920` and height to `1080`.
5. Keep the source background transparent and place it above the scene you want it to overlay.

The information panel is approximately 667 × 1080 pixels. The remaining area is transparent and is used for the temporary clock-settings popup.

## Requirements

- OBS Studio with its Browser Source support
- Internet access for the HamQSL data feed
- The files in this repository kept together in the same folder

No Caddy, local web server, Node.js, npm, build step, framework, or external JavaScript library is required. The SVG artwork is embedded in `index.html`, and the page loads `app.js` from the same folder.

## Data source and refresh behavior

The overlay requests `https://www.hamqsl.com/solarxml.php` directly from the OBS browser runtime. Successful data is refreshed every hour. A failed request is retried after five minutes, and each request has a 15-second timeout. Requests run sequentially so that two refreshes cannot overlap.

Direct browser access depends on HamQSL allowing cross-origin requests (CORS). If HamQSL does not send a suitable CORS header, the browser may block the XML request. Opening a local HTML file cannot bypass that browser security restriction. A local proxy would be needed in that case; this project intentionally does not run one so the overlay can remain server-free.

## Project notes

This version adapts [chfour/uvbinfobar](https://github.com/chfour/uvbinfobar) for local OBS Browser Source use. It embeds the original SVG, removes the Caddy template and proxy dependency, and keeps the project free of build tooling and runtime libraries.

## License

The upstream project is released under the Unlicense. See [LICENSE](LICENSE).