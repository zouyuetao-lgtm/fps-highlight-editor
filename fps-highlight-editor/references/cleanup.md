# Cleanup

Cleanup is permanent deletion, not routine folder tidying. Before proposing deletion, read `edit-project.json` and classify every candidate path from manifest records.

## Protected files

Never include these in an ordinary cleanup plan:

- every `source_files` path;
- `edit-project.json` and approval history represented by its records;
- every version output while `final_version` is unset;
- once `final_version` uniquely identifies a version, that version and every `approved` or `final` version;
- report and license artifacts;
- approved music copies and any file needed to reproduce an approved or final version.

Once a unique `final_version` exists, a non-final `candidate` version may be proposed as a disposable old draft. Derive that proposal only from its `versions` record. An artifact with category `version` remains protected. Only propose disposable derived artifacts that are no longer needed, such as replaceable proxies, contact sheets, waveforms, spectrograms, transient QC frames, or rejected draft segments. State why each item is disposable.

## Exact-plan confirmation

Build a canonical deletion plan containing each exact absolute path, category, source manifest record ID, SHA-256, stable file identity, size, modification time, and total item count. Calculate one plan digest from that complete ordered data set and display both the full list and digest. The user confirms the displayed digest once; a general request to clean up is not confirmation.

At execution, `scripts/cleanup_project.py` must recompute and verify the same plan digest before deleting anything. Execution must not add files after approval. Any digest mismatch, path addition, path removal, or path change requires a new proposal, a new displayed digest, and new confirmation. Do not use ad-hoc recursive deletion, broad globs, or a filename guess.

All protected records must be structurally valid or cleanup stops. On Windows, reject device/extended namespace paths and alternate data streams; reject any candidate whose file identity matches a protected source, including hard links.

The no-deletion guarantee applies only when the complete preflight rejects a plan. After deletion starts, this standard-library script does not provide transactional rollback for concurrent filesystem changes or storage failures.

Warn that deletion is permanent before requesting confirmation. If the cleanup script is unavailable or the manifest cannot classify a path, stop and retain the file.
