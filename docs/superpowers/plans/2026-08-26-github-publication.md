# FPS Highlight Editor GitHub Publication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish the validated `fps-highlight-editor` Skill as a safe, useful public GitHub repository under the user's authenticated account.

**Architecture:** Keep the installable Skill isolated in `fps-highlight-editor/`; place human documentation, tests, and CI at repository level. Use only Git, Python's standard-library `unittest`, GitHub Actions, and the existing FFmpeg-based validation workflow; do not add a package manager, build system, or release automation.

**Tech Stack:** Markdown, Git, Python 3.12, standard-library `unittest`, FFmpeg/FFprobe, GitHub Actions on `windows-latest`

## Global Constraints

- Repository name: `fps-highlight-editor`; visibility: public; default branch: `main`.
- License: MIT, copyright `fps-highlight-editor contributors`.
- Runtime requirements documented as Python 3.10+ and FFmpeg/FFprobe.
- Only `fps-highlight-editor/` is copied into the user's personal Codex Skill directory.
- Do not publish gameplay footage, music, generated outputs, FFmpeg binaries, credentials, user-home paths, caches, or local audit artifacts.
- Preserve the current 12-file Skill package byte-for-byte while adding repository-level material.
- CI runs the full unit test suite on Windows with Python 3.12 and does not download FFmpeg.
- Use the authenticated GitHub account; never place credentials or tokens in files or command arguments.
- Keep the initial repository minimal: no website, logo, dependency manager, coverage service, release automation, or issue-template suite.

---

### Task 1: Public repository documentation and ignore rules

**Files:**
- Create: `README.md`
- Create: `LICENSE`
- Create: `CONTRIBUTING.md`
- Create: `SECURITY.md`
- Modify: `.gitignore`
- Fix: `docs/superpowers/specs/2026-08-26-github-publication-design.md`

**Interfaces:**
- Consumes: the validated CLI contracts in `fps-highlight-editor/SKILL.md` and scripts under `fps-highlight-editor/scripts/`.
- Produces: a Chinese-first public landing page, install instructions that copy only `fps-highlight-editor/`, contribution/security policy, MIT license, and exclusions used by the publication scan.

- [ ] **Step 1: Confirm repository-level documents do not already exist**

  Run: `@('README.md','LICENSE','CONTRIBUTING.md','SECURITY.md') | ForEach-Object { "$_=$([bool](Test-Path $_))" }`

  Expected: all four values are `False`.

- [ ] **Step 2: Write the minimum complete public documents**

  `README.md` must contain, in this order: Chinese project summary; short English summary; agent-guided versus autonomous detection boundary; features (`inspect`, `draft`, `music`, `enhance`, `verify`, two-stage cleanup); requirements; clone/install instructions; concise workflow; safety and music-rights rules; limitations; roadmap; related-project links; MIT license notice.

  `CONTRIBUTING.md` must require a focused branch, focused test, `unittest` command, Skill validation, and pull request. `SECURITY.md` must request private reporting for source-deletion or command-injection issues and must not invent an email address. `LICENSE` must contain the standard MIT text with year 2026 and `fps-highlight-editor contributors`.

- [ ] **Step 3: Extend `.gitignore` with public-repository safety exclusions**

  Add Python caches, `.superpowers/`, `.tools/`, `.validator-deps/`, common video/audio extensions, `video-output/`, and generated manifest/proposal/cleanup/validation/QC artifacts. Keep source Markdown, Python, YAML, JSON test fixtures, and committed `docs/superpowers/` content trackable.

- [ ] **Step 4: Verify documentation coverage and absence of placeholders**

  Run: `rg -n "agent-guided|Python 3\.10|FFmpeg|inspect|draft|music|enhance|verify|cleanup|MIT|Auto-Editor|PySceneDetect|GameVideoEdit" README.md`

  Expected: every required topic appears.

  Run: `rg -n -i "placeholder|change[-_ ]?me|example\.com" README.md CONTRIBUTING.md SECURITY.md LICENSE`

  Expected: no matches.

- [ ] **Step 5: Commit the documentation package**

  Run: `git add .gitignore README.md LICENSE CONTRIBUTING.md SECURITY.md docs/superpowers/specs/2026-08-26-github-publication-design.md docs/superpowers/plans/2026-08-26-github-publication.md`

  Run: `git commit -m "docs: prepare public GitHub repository"`

  Expected: one commit containing only repository publication documentation and ignore rules.

### Task 2: Windows CI and pre-publication verification

**Files:**
- Create: `.github/workflows/tests.yml`
- Test: `tests/fps-highlight-editor/test_*.py`
- Validate: `fps-highlight-editor/`

**Interfaces:**
- Consumes: Python 3.12 and the repository's existing standard-library unit tests.
- Produces: a GitHub Actions check named `unit-tests` on pushes and pull requests, plus local evidence that the public tree is safe and the installed Skill is unchanged.

- [ ] **Step 1: Create the Windows unit-test workflow**

  Use `actions/checkout@v7`, `actions/setup-python@v7`, Python `3.12`, `windows-latest`, and this command:

  ```powershell
  python -B -m unittest discover -s tests/fps-highlight-editor -p "test_*.py" -v
  ```

- [ ] **Step 2: Parse and inspect the workflow**

  Run: `$env:PYTHONPATH='.validator-deps'; python -c "from pathlib import Path; import yaml; d=yaml.safe_load(Path('.github/workflows/tests.yml').read_text(encoding='utf-8')); assert d['jobs']['unit-tests']['runs-on']=='windows-latest'"`

  Expected: exit code 0.

- [ ] **Step 3: Run the complete unit suite**

  Run: `python -B -m unittest discover -s tests/fps-highlight-editor -p "test_*.py" -v`

  Expected: 57 tests pass.

- [ ] **Step 4: Validate the build and installed Skill packages**

  Run the repository's existing quick-validation command against `fps-highlight-editor/`, then against `$env:USERPROFILE\.codex\skills\fps-highlight-editor`.

  Expected: both validations succeed; recursive SHA-256 comparison reports the same 12 relative files and no content differences.

- [ ] **Step 5: Run the existing real FFmpeg integration check**

  Execute the established synthetic-media workflow for inspect, draft, music, enhance, and verify using the local FFmpeg/ffprobe tools.

  Expected: the source hash is unchanged, video output is 60 fps, game and BGM tones are both present, and every validation check is true.

- [ ] **Step 6: Scan the tracked tree and history before publication**

  Run checks over `git ls-files` and `git rev-list --objects --all` for media extensions, FFmpeg executables, large blobs, credentials/tokens, drive-qualified paths, user profile directories, `.tools`, `.validator-deps`, and generated output names.

  Expected: no prohibited tracked file or historical blob. Documentation may contain generic Windows syntax but no user-home path.

- [ ] **Step 7: Run final Git checks and commit CI**

  Run: `git diff --check`

  Run: `git status --short`

  Expected before commit: only `.github/workflows/tests.yml` is uncommitted.

  Run: `git add .github/workflows/tests.yml; git commit -m "ci: test skill on Windows"`

### Task 3: Create and publish the GitHub repository

**Files:**
- Modify Git refs and remote configuration only; do not modify Skill package contents.

**Interfaces:**
- Consumes: the authenticated in-app GitHub session and the verified local feature branch.
- Produces: the public repository URL, local `origin`, pushed `main`, and visible GitHub README/license/Actions metadata.

- [ ] **Step 1: Record the validated Skill package hash inventory**

  Run the same 12-file SHA-256 inventory used in Task 2 and retain it for the post-push comparison.

- [ ] **Step 2: Fast-forward local `main`**

  Verify `main` is an ancestor of `feature/fps-highlight-editor`, switch to `main`, and fast-forward with `git merge --ff-only feature/fps-highlight-editor`.

  Expected: no merge commit and no content conflict.

- [ ] **Step 3: Create an empty public GitHub repository**

  In the user's authenticated GitHub session, create `fps-highlight-editor` with visibility `Public`; do not initialize a README, license, or `.gitignore`. Set the description to: `Agent-guided FFmpeg workflow for reviewable Valorant and PUBG highlight edits.`

  Expected: GitHub displays the empty repository quick-setup page under the authenticated account.

- [ ] **Step 4: Add the exact remote and push `main`**

  Copy the HTTPS URL shown by GitHub on the empty repository quick-setup page, confirm that it ends in `/fps-highlight-editor.git`, and pass that exact visible value to `git remote add origin`.

  Run: `git push -u origin main`

  Expected: `main` is uploaded and tracks `origin/main`.

- [ ] **Step 5: Verify the public result**

  Open the repository URL and confirm: visibility is public; `main` is default; README renders; GitHub detects the MIT license; Actions shows the `tests` workflow; the repository tree has no media, binaries, local cache, or audit folders.

- [ ] **Step 6: Recheck local integrity**

  Run: `git status --short --branch`

  Expected: clean `main` tracking `origin/main`.

  Re-run the 12-file Skill SHA-256 inventory.

  Expected: it exactly matches the inventory captured before publication and the installed personal Skill.
