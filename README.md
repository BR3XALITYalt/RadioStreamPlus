# uvbinfobar

A small UVB-76 livestream information panel, adapted from [chfour/uvbinfobar](https://github.com/chfour/uvbinfobar) to run directly as an OBS Browser Source local file.

## OBS setup

1. Download this repository (Code → Download ZIP) and extract it somewhere permanent.
2. In OBS, add a **Browser** source.
3. Enable **Local file** and select `index.html` from this folder.
4. Set Width to `1920` and Height to `1080`.
5. Keep the page background transparent. OBS's default Browser Source CSS already does this.

The information panel occupies the left 667 × 1080 pixels. The rest of the 1920 × 1080 canvas is transparent, matching the original composition.

## Requirements

- OBS Studio with the Browser Source plugin
- Internet access for live propagation data from HamQSL

No Caddy, local web server, Node.js, npm, build step, framework, or external JavaScript library is required. `index.html` contains the SVG inline, and `app.js` is loaded from the same local folder.

## Data source and refresh

The page requests `https://www.hamqsl.com/solarxml.php` directly from the OBS browser runtime. Data refreshes every hour. A failed request is retried after five minutes, and each request has a 15-second timeout. Requests are sequential, so they cannot overlap.

Direct browser access depends on HamQSL allowing cross-origin requests (CORS). If HamQSL does not send a suitable CORS header, OBS will block the XML request. A local HTML file cannot bypass that browser security restriction by itself. In that case, a small local proxy would be required; this version intentionally does not run one because the goal is a server-free setup.

## What it displays

- UTC and Moscow time (UTC+3)
- 80m/40m daytime and nighttime propagation conditions
- Solar flux index
- Signal noise floor
- Geomagnetic activity from the HamQSL K-index

## Changes

- Removed the Caddy template dependency and `/propdata` proxy route.
- Embedded the original SVG directly in `index.html` so OBS can open it as a local file.
- Fetches the HamQSL XML endpoint directly over HTTPS.
- Retains the original 1920 × 1080 canvas and 667-pixel-wide panel.
- Keeps XML validation, required-field checks, request timeout, retry handling, non-overlapping polling, one-second clock updates, and reduced-motion support.
- Uses no build tooling or runtime dependencies.

## License

The upstream project is released under the Unlicense. See [LICENSE](LICENSE).
