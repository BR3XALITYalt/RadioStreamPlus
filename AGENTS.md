# Repository instructions

## Data format versioning

Whenever a field is added, removed, renamed, or changes meaning in saved radio presets or full-data backups:

- Increment the radio preset JSON schema version when the persisted preset object changes.
- Increment the individual radio preset XML version when its exported fields or structure change.
- Increment the full-data backup XML version when its contents or structure change, including nested preset data.
- Keep import support for earlier versions when practical. Apply explicit migrations or safe defaults for fields that did not exist in older formats.
- Add tests that assert the new exported version and verify backward-compatible imports.

Current format versions are defined in `radiostream_core.py`. Update those constants rather than scattering version literals throughout the code.
