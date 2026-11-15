# Repository instructions

## Data format versioning

Whenever a field is added, removed, renamed, or changes meaning in saved radio presets or full-data backups:

- Increment the radio preset JSON schema version when the persisted preset object changes.
- Increment the individual radio preset XML version when its exported fields or structure change.
- Increment the full-data backup XML version when its contents or structure change, including nested preset data.
- Keep import support for earlier versions when practical. Apply explicit migrations or safe defaults for fields that did not exist in older formats.
- Add tests that assert the new exported version and verify backward-compatible imports.

Current format versions are defined in `radiostream_core.py`. Update those constants rather than scattering version literals throughout the code.

## End-user-facing code

- Keep all user-facing text focused on the application and its use. Do not expose internal development notes, implementation chatter, contributor instructions, or project-management details in application UI, dialogs, notifications, logs intended for users, or other user-facing output.
- Do not refer users to internal development workflows, version-control history, repository organization, or wikis. Link to public user documentation only when it is genuinely useful.
- Comments in public-facing code must explain what the code does or why the behavior is necessary. Do not use comments to describe project organization, development history, or instructions to future contributors.
- Keep developer-facing guidance in developer documentation such as `AGENTS.md`, not in application strings or end-user documentation.
