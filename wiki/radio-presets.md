# Radio Presets

**Navigation:** [Wiki home](main.md) · [Management Page](management.md) · [Configuration](configuration.md)

Radio presets are named tuning profiles. They let you switch between regularly monitored signals without re-entering the frequency, demodulation mode, and passband every time.

Examples include separate entries for WWV frequencies, the Pip, the buzzer, local repeaters, or any other station you monitor. Presets are user-defined; RadioStream+ does not assume that a named signal is always on one fixed frequency.

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

The frequency is displayed in whichever unit is currently selected in the frequency control. The saved value itself is stored internally in kHz.

## Update a preset

Saving another preset with the same name updates the existing entry rather than creating a duplicate. Preset names are compared without regard to letter case.

## Delete a preset

Select it in **Saved presets** and choose **Delete**. This removes the saved preset but does not change the current radio settings.

## Storage

Presets are stored locally in `radio_presets.json`, separately from `radiostream.json`. They remain available across application restarts and are not replaced by application updates. The file is user data and is excluded from Git by the repository's `.gitignore`.

Up to 200 presets can be stored. Each preset must have a name, a supported frequency, a supported mode, and a valid passband.
