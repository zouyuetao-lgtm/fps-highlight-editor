# Inspection and first-cut workflow

Use this sequence for source footage and ordinary highlight drafts.

1. **Inspect.** Inventory each source, read stream properties and duration, and review low-cost derivatives such as proxies, contact sheets, waveforms, or spectrograms. Record every created derivative as an artifact in `edit-project.json`. `inspect_media.py` creates a new manifest exclusively; if one already exists, continue from it or choose a new output directory instead of overwriting it.
2. **Propose.** Identify candidate events with source IDs, time ranges, evidence, and an editing rationale. Build a first-cut proposal from those candidates; it is not a render request.
3. **Get approval.** Wait for approval or requested changes. Mark only accepted candidates and segments as approved in the manifest. Do not render while selection is still proposed.
4. **Render a version.** Render approved segments into a new version record with its exact settings and output path. Keep every earlier version intact.
5. **Verify.** Check container, resolution, frame rate, codecs, version duration, audio presence, measurement command results, and a representative QC frame against `target`. Record the result as a report artifact. A user-approved candidate version may become `approved`; mark it `final` and set `final_version` only after explicit final approval.

Keep original source files unchanged throughout. If later work needs music, effects, or cleanup, load that mode's reference before making its proposal.
