# OpenWebRX

**Navigation:** [Wiki home](main.md) · [Receiver Discovery](receiver-discovery.md) · [Management Page](management.md) · [Radio Presets](radio-presets.md)

RadioStream+ discovers OpenWebRX receivers from Receiverbook and from a user-managed custom list. Unlike KiwiSDR, OpenWebRX entries open directly in a separate browser tab and do not take part in automatic rotation.

## Public Receiverbook listings

The public source reads OpenWebRX entries and coordinates from Receiverbook's map page. The **Include public Receiverbook listings** checkbox controls whether those records are searched.

## Add a custom receiver

1. Find the receiver's public web address.
2. Move the map center pin to the receiver's location, or find its latitude and longitude.
3. Enter the receiver URL.
4. Optionally give it a display name.
5. Enter the coordinates, or select **Use map pin for coordinates**.
6. Select **Add instance**.

The URL must use HTTP or HTTPS and must not point to localhost or a private/reserved IP address. RadioStream+ uses public receiver status endpoints to determine the advertised frequency coverage.

Custom records are saved locally in `openwebrx_custom.json`. Removing an entry deletes it from that local list. Turning off **Include your custom instances** merely hides the list from discovery; it does not delete entries.

## Frequency filtering

RadioStream+ reads frequency coverage from the OpenWebRX+ `status.json` response or the classic OpenWebRX `/status` response. Only receivers with an advertised range containing the selected frequency appear in the result list.

A receiver can still reject the tuning link. OpenWebRX+ may only accept tuning within its currently active profile, while discovery can see the ranges of multiple advertised profiles. The link does not force a profile switch.

## URL behavior

The tuning link includes the selected frequency in Hz and the selected demodulation mode. NBFM is translated to OpenWebRX's `nfm` mode name.

## Location and availability

Custom coordinates are entered manually and should identify the receiver's location, not necessarily the computer running RadioStream+. The receiver must also fall within the current map radius.

A saved URL is not a guarantee that the instance is online. Receiver operators can move, close, restrict, or reconfigure their instances at any time.
