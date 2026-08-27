"""Inspect source footage and create an edit-project manifest."""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import tempfile
from datetime import date
from pathlib import Path


MEDIA_EXTENSIONS = {".mkv", ".mp4", ".mov", ".avi", ".webm"}


def parse_rate(value: str) -> float:
    """Parse an ffprobe rate such as ``60/1`` or ``59.94``."""
    text = str(value).strip()
    if "/" in text:
        numerator, denominator = text.split("/", 1)
        denominator_value = float(denominator)
        if denominator_value == 0:
            raise ValueError(f"invalid frame rate: {value!r}")
        result = float(numerator) / denominator_value
    else:
        result = float(text)
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"frame rate must be finite and greater than 0: {value!r}")
    return result


def run_json(command: list[str]) -> dict:
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        shell=False,
    )
    return json.loads(completed.stdout)


def discover_media(path: Path) -> list[Path]:
    root = Path(path).resolve()
    if not root.exists():
        raise FileNotFoundError(root)
    if root.is_file():
        return [root] if root.suffix.lower() in MEDIA_EXTENSIONS else []
    return sorted(
        (item for item in root.rglob("*") if item.is_file() and item.suffix.lower() in MEDIA_EXTENSIONS),
        key=lambda item: str(item).lower(),
    )


def _number(value: object, default: float | None = None) -> float | None:
    if value is None or str(value).strip() in {"", "N/A"}:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def probe_file(path: Path, ffprobe: str) -> dict:
    resolved = Path(path).resolve()
    data = run_json(
        [
            ffprobe,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(resolved),
        ]
    )
    streams = data.get("streams", [])
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    if video is None:
        raise ValueError(f"no video stream found: {resolved}")
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    fps = None
    for candidate in (video.get("avg_frame_rate"), video.get("r_frame_rate")):
        if candidate in (None, "", "N/A"):
            continue
        try:
            fps = parse_rate(candidate)
            break
        except (TypeError, ValueError):
            continue
    if fps is None:
        raise ValueError(f"video stream has no valid frame rate: {resolved}")
    result = {
        "path": str(resolved),
        "duration": _number(video.get("duration"))
        or _number(data.get("format", {}).get("duration")),
        "fps": fps,
        "width": video.get("width"),
        "height": video.get("height"),
        "video_codec": video.get("codec_name"),
        "audio_codec": audio.get("codec_name") if audio else None,
    }
    return {key: value for key, value in result.items() if value is not None}


def _source_record(source: dict | Path, index: int) -> dict:
    if isinstance(source, (str, Path)):
        source = {"path": str(source)}
    record = dict(source)
    record["id"] = record.get("id") or f"source-{index}"
    record["path"] = str(Path(record["path"]).resolve())
    return record


def create_manifest(
    source_files: list[dict | Path],
    output_dir: Path,
    game: str,
    target_fps: float,
) -> dict:
    sources = [_source_record(source, index) for index, source in enumerate(source_files, 1)]
    requested_fps = _validate_fps(target_fps, "target FPS")
    native_rates = [
        _validate_fps(source["fps"], f"source FPS for {source['path']}")
        for source in sources
        if source.get("fps") is not None
    ]
    measured_fps = min([requested_fps, *native_rates])
    warnings = []
    if any(rate < requested_fps for rate in native_rates):
        warnings.append("source_fps_below_requested")
    first = sources[0] if sources else {}
    return {
        "schema_version": 1,
        "project_id": f"{game}-{date.today():%Y%m%d}",
        "game": game,
        "output_dir": str(Path(output_dir).resolve()),
        "source_files": sources,
        "target": {
            "container": "mp4",
            "width": first.get("width", 1920),
            "height": first.get("height", 1080),
            "fps": measured_fps,
            "video_codec": "h264",
            "audio_codec": "aac",
            "preserve_game_audio": True,
        },
        "candidates": [],
        "segments": [],
        "music": {"mode": "none"},
        "effects": [],
        "versions": [],
        "final_version": None,
        "artifacts": [],
        "warnings": warnings,
    }


def _write_json_atomic(path: Path, payload: dict) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, indent=2, ensure_ascii=False, allow_nan=False)
            handle.write("\n")
            handle.flush()
        os.link(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _validate_fps(value: object, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be finite and greater than 0") from exc
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{label} must be finite and greater than 0")
    return result


def _fps_argument(value: str) -> float:
    try:
        return _validate_fps(value, "target FPS")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="media file or directory")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--game", required=True)
    parser.add_argument("--target-fps", required=True, type=_fps_argument)
    parser.add_argument("--ffprobe", default="ffprobe")
    args = parser.parse_args(argv)

    media = discover_media(args.source)
    if not media:
        parser.error("source contains no supported media files")
    sources = [probe_file(item, args.ffprobe) for item in media]
    manifest = create_manifest(sources, args.output_dir, args.game, args.target_fps)
    _write_json_atomic(args.output_dir / "edit-project.json", manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
