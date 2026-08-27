---
name: fps-highlight-editor
description: "Use when turning Valorant or PUBG footage into reviewable, versioned highlight edits with optional music, effects, or safe cleanup."
---

# Fps Highlight Editor

Use `edit-project.json` as the project record. Propose candidates, segments, music, and effects before rendering; do not render an unapproved proposal. Every render is a new version: preserve prior versions and mark the final version only after approval. Source footage is never ordinary cleanup material. For cleanup, use `scripts/cleanup_project.py` with a confirmed exact plan; do not use ad-hoc recursive deletion.

Run `python scripts/<name>.py --help` for arguments. The five modes are: inspect with `inspect_media.py`; draft/music/enhance with `render_project.py`; verify with `validate_output.py`; and two-stage cleanup with `cleanup_project.py plan|execute`.

- For source inspection and first cuts, read `references/workflow.md`.
- For project state, read `references/project-manifest.md`.
- For Valorant or PUBG event selection, also read `references/game-profiles.md`.
- For supplied or web-sourced music, read `references/music-and-rights.md`.
- For transitions, speed changes, or emphasis effects, read `references/enhancements.md`.
- For final cleanup, read `references/cleanup.md` before proposing any deletion.
