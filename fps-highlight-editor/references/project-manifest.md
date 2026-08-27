# Project manifest

Each edit project has one `edit-project.json`. It is the authoritative record of inputs, decisions, outputs, and protected records; never infer those roles from file names.

```json
{
  "schema_version": 1,
  "project_id": "valorant-20260825",
  "game": "valorant",
  "output_dir": "D:/video-output/valorant-20260825",
  "source_files": [],
  "target": {
    "container": "mp4",
    "width": 1920,
    "height": 1080,
    "fps": 60,
    "video_codec": "h264",
    "audio_codec": "aac",
    "preserve_game_audio": true
  },
  "candidates": [],
  "segments": [],
  "music": {"mode": "none"},
  "effects": [],
  "versions": [],
  "final_version": null,
  "artifacts": []
}
```

`schema_version` is the integer `1`. Keep all required top-level fields, even when their arrays are empty. `project_id` identifies the edit; `output_dir` is the project-owned destination; `source_files` lists original footage and must not be treated as disposable output.

## Records

Use stable IDs and paths in records so relationships are explicit:

- A `source_files` record identifies one input with at least `id` and `path`; capture duration or a content hash when available.
- A `candidates` record links to a source ID and includes its time range, event evidence, rationale, and `status`. Candidate `status` is exactly `proposed|approved|rejected`.
- A `segments` record has `id`, `candidate_id`, `source_id`, numeric `start`/`end`, and `status`. Its source and range must stay inside the approved candidate.
- An `effects` record has `id`, `segment_id`, `status: approved`, `type`, and either numeric `start`/`end` or equivalent values in `parameters`.
- `music` has `mode` exactly `none|provided|licensed-web`. Non-`none` music requires `status: approved`, local `path`, numeric `source_start`, `gain`, `fade_in`, `fade_out`, `approval_confirmed: true`, `music_copy_artifact_id`, and `authorization_artifact_id`. The music path must identify the approved local copy; the authorization artifact must be an existing approved `license` record that documents publication rights.
- A `versions` record has an ID, output path, measured or expected `duration`, input segment IDs, render settings, and `status`. Version `status` is exactly `candidate|approved|final`. `final_version` is either `null` or the ID of the sole record with `status: final`.
- An `artifacts` record has a path, the source or version it derives from, and `category`. Artifact `category` is exactly `proxy|segment|contact-sheet|waveform|spectrogram|qc-frame|music-copy|report|license|version`.

Approval status, the final-version pointer, reports, and license records are protected project records. Keep them in the manifest even when a derived preview is removed. Update a record when state changes; do not replace it with a filename convention.
