# Radio Presets

**Navigation:** [Wiki home](main.md) · [Management Page](management.md) · [Configuration](configuration.md)

Radio presets are named tuning profiles. They let you switch between regularly monitored signals without re-entering the frequency, demodulation mode, and passband every time.

Use presets for the frequencies and demodulation modes in your regular monitoring schedule. A preset can represent any signal you monitor; RadioStream+ does not assume that a named signal is always on one fixed frequency.

## Save a preset

1. Set the frequency and its unit.
2. Choose the demodulation mode.
3. Set the passband low and high values.
4. Enter a name in **Save current frequency as**.
5. Select **Save preset**.

The saved profile includes:

- Name.
- Frequency.
- Demodulation mode.
- Passband low and high.

The preset does not store the map center, search radius, KiwiSDR zoom, receiver volume, or overlay messages.

## Load a preset

Choose the preset in **Saved presets** and select **Load preset**. RadioStream+ applies its frequency, mode, and passband, saves the updated radio settings, and refreshes the receiver search results.

The preset stores one frequency. Loading it changes the currently active frequency link and leaves the other links unchanged. The frequency value is stored internally in kHz.

## Update a preset

Saving another preset with the same name updates the existing entry rather than creating a duplicate. Preset names are compared without regard to letter case.

## Delete a preset

Select it in **Saved presets** and choose **Delete**. This removes the saved preset but does not change the current radio settings.

## Storage

Presets are stored locally in `radio_presets.json`, separately from `radiostream.json`. They remain available across application restarts and application updates.

Up to 200 presets can be stored. Each preset must have a name, a supported frequency, a supported mode, and a valid passband.
