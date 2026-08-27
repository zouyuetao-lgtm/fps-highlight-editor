"""Create and execute one-confirmation cleanup plans for an edit project."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path


DISPOSABLE_CATEGORIES = {"proxy", "contact-sheet", "waveform", "spectrogram", "qc-frame"}
PROTECTED_CATEGORIES = {"license", "music-copy", "report", "version"}


def _absolute_path(value: object, base: Path) -> Path:
    if not isinstance(value, (str, Path)) or not str(value).strip():
        raise ValueError("manifest path is required")
    raw = str(value).strip()
    if os.name == "nt":
        normalized = raw.replace("/", "\\")
        if normalized.startswith(("\\\\?\\", "\\\\.\\")):
            raise ValueError("Windows device and extended paths are not allowed")
        drive, tail = os.path.splitdrive(normalized)
        if ":" in tail:
            raise ValueError("Windows alternate data streams are not allowed")
    path = Path(value)
    return Path(os.path.abspath(path if path.is_absolute() else base / path))


def _has_reparse_component(path: Path) -> bool:
    current = Path(path.anchor)
    for component in path.parts[1:]:
        current /= component
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        if current.is_symlink() or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
            return True
    return False


def _resolve(value: object, base: Path) -> Path:
    path = _absolute_path(value, base)
    if _has_reparse_component(path):
        raise ValueError("manifest paths must not traverse symlinks or reparse points")
    return path.resolve()


def _load_manifest(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("manifest must be a JSON object")
    return data


def _output_dir(manifest: dict, manifest_path: Path) -> Path:
    output_dir = _resolve(manifest.get("output_dir"), manifest_path.parent)
    if not output_dir.is_dir():
        raise ValueError("output_dir must be an existing directory")
    return output_dir


def _path_key(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def _is_child(path: Path, root: Path) -> bool:
    return path != root and path.is_relative_to(root)


def _fingerprint(path: Path) -> dict[str, int | str]:
    stat = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return {
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "sha256": digest.hexdigest(),
        "st_dev": stat.st_dev,
        "st_ino": stat.st_ino,
    }


def _record_path(record: dict, manifest_path: Path) -> Path | None:
    value = record.get("path")
    return _resolve(value, manifest_path.parent) if value is not None else None


def _records(manifest: dict, key: str) -> list[dict]:
    value = manifest.get(key)
    if not isinstance(value, list) or any(not isinstance(record, dict) for record in value):
        raise ValueError(f"manifest {key} must be an array of records")
    return value


def _required_record_path(record: dict, manifest_path: Path, label: str) -> Path:
    if not isinstance(record.get("id"), str) or not record["id"].strip():
        raise ValueError(f"{label} record id is required")
    path = _record_path(record, manifest_path)
    if path is None:
        raise ValueError(f"{label} record path is required")
    return path


def _same_file(path: Path, others: set[Path]) -> bool:
    for other in others:
        try:
            if os.path.samefile(path, other):
                return True
        except OSError:
            if _path_key(path) == _path_key(other):
                return True
    return False


def _protected_paths(manifest: dict, manifest_path: Path) -> set[Path]:
    protected = {manifest_path.resolve()}
    sources = _records(manifest, "source_files")
    versions = _records(manifest, "versions")
    artifacts = _records(manifest, "artifacts")
    for source in sources:
        protected.add(_required_record_path(source, manifest_path, "source"))
    version_ids = []
    for version in versions:
        _required_record_path(version, manifest_path, "version")
        if version.get("status") not in {"candidate", "approved", "final"}:
            raise ValueError("version status is invalid")
        version_ids.append(version["id"])
    if len(set(version_ids)) != len(version_ids):
        raise ValueError("version ids must be unique")
    final = manifest.get("final_version")
    if final is None:
        if any(version.get("status") == "final" for version in versions):
            raise ValueError("a final version requires final_version")
        protected.update(
            _record_path(version, manifest_path)
            for version in versions
        )
    else:
        final_records = [record for record in versions if record.get("status") == "final"]
        matches = [record for record in final_records if record.get("id") == final]
        if len(final_records) != 1 or len(matches) != 1:
            raise ValueError("final_version must identify the sole final version")
        protected.add(_record_path(matches[0], manifest_path))
        protected.update(
            _record_path(version, manifest_path)
            for version in versions
            if version.get("status") in {"approved", "final"}
        )
    music = manifest.get("music")
    if not isinstance(music, dict):
        raise ValueError("manifest music must be an object")
    if music.get("path") is not None:
        protected.add(_record_path(music, manifest_path))
    for artifact in artifacts:
        path = _required_record_path(artifact, manifest_path, "artifact")
        if not isinstance(artifact.get("category"), str) or not artifact["category"].strip():
            raise ValueError("artifact category is required")
        category = str(artifact.get("category", "")).lower()
        if category in PROTECTED_CATEGORIES or artifact.get("status") in {"approved", "final"}:
            protected.add(path)
    return protected


def _is_disposable(record: dict) -> bool:
    category = str(record.get("category", "")).lower()
    if record.get("status") in {"approved", "final"}:
        return False
    return category in DISPOSABLE_CATEGORIES or (category == "segment" and record.get("status") == "rejected")


def _directories(entries: list[dict], output_dir: Path) -> list[str]:
    directories: set[Path] = set()
    for entry in entries:
        directory = Path(entry["path"]).parent
        while directory != output_dir:
            directories.add(directory)
            directory = directory.parent
    return [str(path) for path in sorted(directories, key=_path_key)]


def build_plan(manifest_path: Path | str) -> dict:
    """Build an exact, reviewable plan from disposable manifest artifacts."""
    manifest_path = Path(manifest_path).resolve()
    manifest = _load_manifest(manifest_path)
    output_dir = _output_dir(manifest, manifest_path)
    protected = _protected_paths(manifest, manifest_path)
    if any(not path.is_file() for path in protected):
        raise ValueError("a protected project file is unavailable")
    entries = []
    seen: set[Path] = set()
    artifacts = _records(manifest, "artifacts")
    versions = _records(manifest, "versions")
    candidates = [
        (record, str(record.get("category", "")))
        for record in artifacts
        if _is_disposable(record)
    ]
    if manifest.get("final_version") is not None:
        candidates.extend(
            (version, "version")
            for version in versions
            if version.get("status") == "candidate"
            and version.get("id") != manifest["final_version"]
        )
    for record, category in candidates:
        raw = record.get("path")
        path = _resolve(raw, manifest_path.parent)
        raw_path = Path(raw) if isinstance(raw, (str, Path)) else path
        if not raw_path.is_absolute():
            raw_path = manifest_path.parent / raw_path
        if raw_path.is_symlink() or not _is_child(path, output_dir):
            raise ValueError("cleanup candidate must be a non-symlink file below output_dir")
        if not path.is_file():
            raise ValueError("cleanup candidate must be an existing regular file")
        if _same_file(path, protected):
            raise ValueError("cleanup candidate aliases a protected file")
        if path in seen:
            raise ValueError("cleanup candidates must not repeat a path")
        seen.add(path)
        entries.append(
            {
                "path": str(path),
                "category": category,
                "record_id": str(record.get("id", "")),
                **_fingerprint(path),
            }
        )
    entries.sort(key=lambda entry: _path_key(Path(entry["path"])))
    return {
        "manifest_path": str(manifest_path),
        "output_dir": str(output_dir),
        "protected_paths": [str(path) for path in sorted(protected, key=_path_key)],
        "entries": entries,
        "directories": _directories(entries, output_dir),
        "item_count": len(entries),
    }


def plan_digest(plan: dict) -> str:
    """Return the SHA256 confirmation token for canonical plan JSON."""
    canonical = json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _planned_path(value: object) -> Path:
    if not isinstance(value, str):
        raise ValueError("plan paths must be strings")
    path = Path(value)
    if not path.is_absolute() or path != path.resolve():
        raise ValueError("plan paths must be normalized absolute paths")
    return path


def preflight(plan: dict, digest: str) -> None:
    """Reject any changed, protected, or out-of-bound target before deletion."""
    if not isinstance(plan, dict) or not isinstance(digest, str) or digest != plan_digest(plan):
        raise ValueError("exact cleanup confirmation digest is required")
    manifest_path = _planned_path(plan.get("manifest_path"))
    if not manifest_path.is_file():
        raise ValueError("manifest is unavailable")
    manifest = _load_manifest(manifest_path)
    output_dir = _output_dir(manifest, manifest_path)
    if plan.get("output_dir") != str(output_dir):
        raise ValueError("manifest output_dir changed; build a new plan")
    protected = _protected_paths(manifest, manifest_path)
    if plan.get("protected_paths") != [str(path) for path in sorted(protected, key=_path_key)]:
        raise ValueError("manifest protection records changed; build a new plan")
    entries = plan.get("entries")
    if not isinstance(entries, list) or plan.get("item_count") != len(entries):
        raise ValueError("cleanup plan entries are invalid")
    if entries != build_plan(manifest_path)["entries"]:
        raise ValueError("cleanup plan no longer matches the manifest")
    paths = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("cleanup plan entry is invalid")
        path = _planned_path(entry.get("path"))
        if path.is_symlink() or not _is_child(path, output_dir) or _same_file(path, protected):
            raise ValueError("cleanup plan includes an unsafe target")
        if not path.is_file():
            raise ValueError("cleanup target is unavailable")
        stat = path.stat()
        if stat.st_size != entry.get("size") or stat.st_mtime_ns != entry.get("mtime_ns"):
            raise ValueError("cleanup target changed; build a new plan")
        paths.append(path)
    if len(set(paths)) != len(paths) or paths != sorted(paths, key=_path_key):
        raise ValueError("cleanup plan paths must be unique and sorted")
    directories = plan.get("directories")
    if not isinstance(directories, list) or directories != _directories(entries, output_dir):
        raise ValueError("cleanup plan directories are invalid")
    for value in directories:
        directory = _planned_path(value)
        if directory.is_symlink() or not _is_child(directory, output_dir) or not directory.is_dir():
            raise ValueError("cleanup plan includes an unsafe directory")


def execute_plan(plan_path: Path | str, digest: str) -> dict:
    """Delete only an unchanged, exact confirmed plan after full preflight."""
    plan_path = Path(plan_path).resolve()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    preflight(plan, digest)
    deleted = []
    for entry in plan["entries"]:
        path = Path(entry["path"])
        path.unlink()
        deleted.append(str(path))
    removed_directories = []
    for value in sorted(plan["directories"], key=lambda item: (len(Path(item).parts), _path_key(Path(item))), reverse=True):
        directory = Path(value)
        try:
            directory.rmdir()
        except OSError:
            continue
        removed_directories.append(str(directory))
    return {"deleted": deleted, "removed_directories": removed_directories, "item_count": len(deleted)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan_parser = commands.add_parser("plan")
    plan_parser.add_argument("manifest", type=Path)
    plan_parser.add_argument("--plan", type=Path)
    execute_parser = commands.add_parser("execute")
    execute_parser.add_argument("plan", type=Path)
    execute_parser.add_argument("digest")
    args = parser.parse_args(argv)
    if args.command == "plan":
        plan = build_plan(args.manifest)
        plan_path = (args.plan or Path(plan["manifest_path"]).with_name("cleanup-plan.json")).resolve()
        with plan_path.open("x", encoding="utf-8") as handle:
            json.dump(plan, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
        print(json.dumps({"plan": plan, "digest": plan_digest(plan)}, ensure_ascii=False, indent=2))
        return 0
    print(json.dumps(execute_plan(args.plan, args.digest), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
