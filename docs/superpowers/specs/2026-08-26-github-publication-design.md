# FPS Highlight Editor GitHub Publication Design

## Goal

Publish the completed `fps-highlight-editor` Codex Skill as a public, maintainable first GitHub project. The repository must be useful to a new user, safe to clone, and ready for future improvements without publishing gameplay footage, music, FFmpeg binaries, local caches, or machine-specific validation files.

## Repository identity

- Repository name: `fps-highlight-editor`
- Visibility: public
- Default branch: `main`
- License: MIT, copyright attributed to `fps-highlight-editor contributors`
- Description: an agent-guided, FFmpeg-based workflow for reviewable Valorant and PUBG highlight edits with music, effects, validation, and safe cleanup
- Initial release tags and binary releases are intentionally deferred until the project has a stable external user workflow.

## Layout

Keep the runtime Skill isolated from repository-level material:

```text
fps-highlight-editor/
├── .github/workflows/tests.yml
├── docs/superpowers/specs/
├── fps-highlight-editor/
│   ├── SKILL.md
│   ├── agents/openai.yaml
│   ├── references/
│   └── scripts/
├── tests/fps-highlight-editor/
├── .gitignore
├── CONTRIBUTING.md
├── LICENSE
├── README.md
└── SECURITY.md
```

The installable package remains the `fps-highlight-editor/` subdirectory. Repository documentation, tests, Git metadata, and CI files are never copied into the personal Skill directory.

## Public documentation

`README.md` is human-facing and concise. It contains:

1. A Chinese-first introduction with a short English summary.
2. The distinction between agent-guided editing and fully autonomous kill detection.
3. Supported modes: inspect, draft, music, enhance, verify, and two-stage cleanup.
4. Requirements: Python 3.10 or newer and FFmpeg/FFprobe.
5. Installation for Codex by cloning the repository and copying only the Skill subdirectory.
6. A minimal workflow showing manifest creation, proposal approval, versioned rendering, validation, and cleanup.
7. Safety guarantees: read-only source footage, no overwrite, exact-plan cleanup, and preflight failure causing zero deletions.
8. Music-rights requirements: attribution alone is not authorization; publication evidence must match the rendered local music copy.
9. Current limitations and a small roadmap based on real user needs.
10. Related projects and standards, clearly labeled as references rather than copied code.

The related-project list links to the Agent Skills specification, FFmpeg, Auto-Editor, PySceneDetect, and GameVideoEdit. No third-party source code or assets are incorporated.

`CONTRIBUTING.md` describes the smallest useful contribution workflow: create a short branch, add or update a focused test, run the suite, and open a pull request. `SECURITY.md` asks reporters not to publish possible source-deletion or command-injection issues before coordinated review.

## Repository safety

Extend `.gitignore` to exclude:

- Python caches and local validator/tool directories;
- common gameplay video and BGM extensions;
- generated manifests, cleanup plans, validation reports, QC frames, and video-output directories;
- the ignored local SDD audit workspace.

Before publication, scan tracked paths and history for large files, media, credentials, absolute user paths, tokens, and machine-only artifacts. The repository must contain only source, tests, and documentation.

## Continuous integration

Add one GitHub Actions workflow using the standard Python setup action and Python 3.12. It runs the complete standard-library unittest suite on Windows because Windows path safety is part of the cleanup contract. It does not download FFmpeg or run the heavier synthetic-media integration in CI; that remains a documented local release check.

No dependency manager, packaging framework, coverage service, release automation, website, logo, or issue-template suite is added in the initial version.

## Publication flow

1. Add and validate the public documentation, ignore rules, and Windows CI on the feature branch.
2. Run 57 unit tests, Skill validation, the local real FFmpeg integration, a tracked-file safety scan, and `git diff --check`.
3. Commit the publication package.
4. Fast-forward local `main` to the reviewed feature branch.
5. In the user's authenticated GitHub session, create an empty public `fps-highlight-editor` repository without generated README, license, or `.gitignore` files.
6. Add the repository as `origin` and push `main` with upstream tracking.
7. Verify the public repository URL, default branch, README rendering, license detection, and Actions status.

If GitHub authentication is unavailable, stop after the local commit and report the exact login step required. Do not create a repository under an unverified account or expose credentials in commands or files.

## Future changes

`main` remains the stable branch. Each later improvement uses a short feature branch, tests proportionate to the change, review, and merge back to `main`; the corresponding GitHub history is pushed. Releases and changelogs are added only after there is a real versioning need.

## Acceptance criteria

- The public repository is owned by the user's authenticated GitHub account and named `fps-highlight-editor`.
- GitHub shows the README and MIT license on `main`.
- Clone and install instructions reference the real repository URL and copy only the Skill subdirectory.
- The Windows CI workflow runs the full unit test suite.
- No media, FFmpeg binary, credential, user-home path, cache, or local audit artifact is tracked or present in the pushed history.
- The installed personal Skill remains byte-for-byte identical to the validated 12-file package.
