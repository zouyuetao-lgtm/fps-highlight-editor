"""Build and run safe FFmpeg commands for an approved edit project."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import tempfile
from pathlib import Path


MODES = {"draft", "music", "enhance"}
TRANSITIONS = {"fade", "flash", "hard"}
VERSION_NAME = re.compile(r"^v(\d+)-([A-Za-z0-9][A-Za-z0-9_-]*)$")
OUTPUT_NAME = re.compile(r"^v\d{2,}-[A-Za-z0-9][A-Za-z0-9_-]*\.mp4$")


def _number(value: object, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a finite number") from exc
    if not math.isfinite(result):
        raise ValueError(f"{label} must be a finite number")
    return result


def _fmt(value: float) -> str:
    text = f"{value:g}"
    return text if "." in text or "e" in text.lower() else f"{text}.0"


def _record_index(manifest: dict, key: str) -> dict[str, dict]:
    records = manifest.get(key)
    if not isinstance(records, list) or any(not isinstance(item, dict) for item in records):
        raise ValueError(f"manifest {key} must be an array of records")
    result = {}
    for item in records:
        record_id = item.get("id")
        if not isinstance(record_id, str) or not record_id.strip() or record_id in result:
            raise ValueError(f"manifest {key} ids must be present and unique")
        result[record_id] = item
    return result


def _sources(manifest: dict) -> dict[str, dict]:
    return _record_index(manifest, "source_files")


def _candidates(manifest: dict) -> dict[str, dict]:
    return _record_index(manifest, "candidates")


def validate_approved_segments(manifest: dict) -> list[dict]:
    """Return approved segments after checking their source bounds."""
    sources = _sources(manifest)
    candidates = _candidates(manifest)
    segments = manifest.get("segments", [])
    if not segments:
        raise ValueError("no approved segments")

    approved = []
    segment_ids = set()
    for segment in segments:
        if not isinstance(segment, dict) or not isinstance(segment.get("id"), str) or segment["id"] in segment_ids:
            raise ValueError("segment ids must be present and unique")
        segment_ids.add(segment["id"])
        if segment.get("status") != "approved":
            raise ValueError(f"segment {segment.get('id', '<unknown>')} is not approved")
        candidate = candidates.get(str(segment.get("candidate_id")))
        if candidate is None or candidate.get("status") != "approved":
            raise ValueError(f"segment {segment.get('id', '<unknown>')} requires an approved candidate")
        source = sources.get(str(segment.get("source_id")))
        if source is None:
            raise ValueError(f"segment {segment.get('id', '<unknown>')} has an unknown source")
        start = _number(segment.get("start"), "segment start")
        end = _number(segment.get("end"), "segment end")
        duration = _number(source.get("duration"), "source duration")
        if start < 0 or start >= end or end > duration:
            raise ValueError(f"segment {segment.get('id', '<unknown>')} is outside the source range")
        candidate_start = _number(candidate.get("start"), "candidate start")
        candidate_end = _number(candidate.get("end"), "candidate end")
        if candidate.get("source_id") != segment.get("source_id") or start < candidate_start or end > candidate_end:
            raise ValueError(f"segment {segment.get('id', '<unknown>')} is outside its approved candidate")
        approved.append(segment)
    return approved


def _label(label: str) -> str:
    if not isinstance(label, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", label):
        raise ValueError("version label is invalid")
    return label


def next_version(manifest: dict, label: str) -> str:
    """Return the first unused vNN label across records and output files."""
    label = _label(label)
    used = set()
    highest = 0
    for version in manifest.get("versions", []):
        for value in (version.get("id"), Path(str(version.get("path", ""))).stem):
            match = VERSION_NAME.match(str(value or ""))
            if match:
                number = int(match.group(1))
                highest = max(highest, number)
                used.add(f"v{number:02d}-{match.group(2)}")
    output_dir = Path(manifest.get("output_dir", ".")).resolve()
    if output_dir.exists():
        for path in output_dir.glob("v[0-9][0-9]*-*.mp4"):
            match = VERSION_NAME.match(path.stem)
            if match:
                number = int(match.group(1))
                highest = max(highest, number)
                used.add(path.stem)
    number = highest + 1
    candidate = f"v{number:02d}-{label}"
    while candidate in used:
        number += 1
        candidate = f"v{number:02d}-{label}"
    return candidate


def atempo_chain(speed: float) -> str:
    """Split a positive speed into FFmpeg's supported 0.5..2.0 factors."""
    value = _number(speed, "speed")
    if value <= 0:
        raise ValueError("speed must be greater than 0")
    factors = []
    while value > 2.0:
        factors.append(2.0)
        value /= 2.0
    while value < 0.5:
        factors.append(0.5)
        value /= 0.5
    factors.append(value)
    return ",".join(f"atempo={_fmt(factor)}" for factor in factors)


def _output_path(manifest: dict, output: Path) -> Path:
    raw_root = manifest.get("output_dir")
    if not isinstance(raw_root, (str, Path)) or not str(raw_root).strip():
        raise ValueError("manifest output_dir is required")
    root = Path(raw_root).resolve()
    result = Path(output).resolve()
    try:
        result.relative_to(root)
    except ValueError as exc:
        raise ValueError("output must stay below manifest output_dir") from exc
    if result == root or not OUTPUT_NAME.fullmatch(result.name):
        raise ValueError("output must match vNN-label.mp4 below manifest output_dir")
    if result.exists() or any(
        Path(str(version.get("path", ""))).resolve() == result
        for version in manifest.get("versions", [])
        if version.get("path")
    ):
        raise ValueError("output already exists and cannot be overwritten")
    return result


def _source_path(segment: dict, sources: dict[str, dict]) -> Path:
    source = sources[str(segment["source_id"])]
    raw_path = source.get("path")
    if not isinstance(raw_path, (str, Path)) or not str(raw_path).strip():
        raise ValueError("source path is required")
    return Path(raw_path).resolve()


def _target_filters(manifest: dict) -> tuple[str, str]:
    target = manifest.get("target")
    if not isinstance(target, dict):
        raise ValueError("manifest target is required")
    width = int(_number(target.get("width"), "target width"))
    height = int(_number(target.get("height"), "target height"))
    fps = _number(target.get("fps"), "target FPS")
    if width <= 0 or height <= 0 or fps <= 0:
        raise ValueError("target dimensions and FPS must be greater than 0")
    video = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,fps={_fmt(fps)},format=yuv420p"
    )
    audio = "aformat=sample_rates=48000:channel_layouts=stereo,aresample=48000"
    return video, audio


def build_draft_commands(manifest: dict, ffmpeg: str, output: Path) -> list[list[str]]:
    segments = validate_approved_segments(manifest)
    output = _output_path(manifest, Path(output))
    sources = _sources(manifest)
    command = [ffmpeg, "-n"]
    for segment in segments:
        start = _number(segment["start"], "segment start")
        duration = _number(segment["end"], "segment end") - start
        command.extend(["-ss", _fmt(start), "-t", _fmt(duration), "-i", str(_source_path(segment, sources))])
    video_filter, audio_filter = _target_filters(manifest)
    filters = []
    for index in range(len(segments)):
        filters.append(f"[{index}:v:0]{video_filter}[v{index}]")
        filters.append(f"[{index}:a:0]{audio_filter}[a{index}]")
    inputs = "".join(f"[v{index}][a{index}]" for index in range(len(segments)))
    filters.append(f"{inputs}concat=n={len(segments)}:v=1:a=1[v][a]")
    command.extend(["-filter_complex", ";".join(filters), "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-c:a", "aac"])
    command.append(str(output))
    return [command]


def _approved_parent(manifest: dict, parent_version: str | None = None) -> dict:
    versions = manifest.get("versions", [])
    if parent_version:
        matches = [version for version in versions if version.get("id") == parent_version or str(version.get("path")) == parent_version]
    else:
        matches = [version for version in versions if version.get("status") == "approved"]
    if not matches:
        raise ValueError("music rendering requires an approved parent version")
    parent = matches[-1]
    if parent.get("status") != "approved":
        raise ValueError("parent version must be approved")
    path = Path(str(parent.get("path", ""))).resolve()
    if not str(parent.get("path", "")).strip():
        raise ValueError("approved parent version has no path")
    duration = _number(parent.get("duration"), "approved parent duration")
    if duration <= 0:
        raise ValueError("approved parent duration must be greater than 0")
    return parent


def _music(manifest: dict) -> dict:
    music = manifest.get("music") or {}
    if music.get("mode") not in {"provided", "licensed-web"} or music.get("status") != "approved":
        raise ValueError("music must be approved")
    if music.get("approval_confirmed") is not True:
        raise ValueError("music rights approval must be confirmed")
    path = Path(str(music.get("path", ""))).resolve()
    if not path.is_file():
        raise ValueError("approved music path must be local")
    artifacts = _record_index(manifest, "artifacts")
    copy_record = artifacts.get(str(music.get("music_copy_artifact_id")))
    if copy_record is None or copy_record.get("category") != "music-copy" or copy_record.get("status") != "approved":
        raise ValueError("approved music-copy artifact is required")
    copy_path = Path(str(copy_record.get("path", ""))).resolve()
    if not copy_path.is_file() or not os.path.samefile(path, copy_path):
        raise ValueError("music path must match the approved music-copy artifact")
    authorization = artifacts.get(str(music.get("authorization_artifact_id")))
    if authorization is None or authorization.get("category") != "license" or authorization.get("status") != "approved":
        raise ValueError("approved publication authorization artifact is required")
    authorization_path = Path(str(authorization.get("path", ""))).resolve()
    if not authorization_path.is_file():
        raise ValueError("publication authorization evidence is unavailable")
    source_start = _number(music.get("source_start", 0), "music source_start")
    gain = _number(music.get("gain", 0), "music gain")
    fade_in = _number(music.get("fade_in", 0), "music fade_in")
    fade_out = _number(music.get("fade_out", 0), "music fade_out")
    if min(source_start, fade_in, fade_out) < 0:
        raise ValueError("music timings must not be negative")
    return {"path": path, "source_start": source_start, "gain": gain, "fade_in": fade_in, "fade_out": fade_out}


def build_music_command(manifest: dict, ffmpeg: str, output: Path, parent_version: str | None = None) -> list[str]:
    parent = _approved_parent(manifest, parent_version)
    music = _music(manifest)
    output = _output_path(manifest, Path(output))
    start = _fmt(music["source_start"])
    duration = _number(parent["duration"], "approved parent duration")
    fade_in = _fmt(music["fade_in"])
    fade_out_duration = music["fade_out"]
    fade_out_start = max(0.0, duration - fade_out_duration)
    fades = []
    if music["fade_in"] > 0:
        fades.append(f"afade=t=in:st=0:d={fade_in}")
    if fade_out_duration > 0:
        fades.append(f"afade=t=out:st={_fmt(fade_out_start)}:d={_fmt(fade_out_duration)}")
    fade_chain = "," + ",".join(fades) if fades else ""
    filter_graph = (
        "[0:a]aformat=sample_rates=48000:channel_layouts=stereo,asplit=2[game_mix][game_side];"
        f"[1:a]atrim=duration={_fmt(duration)},asetpts=PTS-STARTPTS,volume={_fmt(music['gain'])}dB"
        f"{fade_chain},apad,atrim=duration={_fmt(duration)}[music];"
        "[music][game_side]sidechaincompress=threshold=0.05:ratio=8:attack=20:release=250[music_ducked];"
        "[game_mix][music_ducked]amix=inputs=2:duration=first:dropout_transition=0,alimiter=level=0[aout]"
    )
    return [
        ffmpeg,
        "-n",
        "-i",
        str(Path(str(parent["path"])).resolve()),
        "-ss",
        start,
        "-i",
        str(music["path"]),
        "-filter_complex",
        filter_graph,
        "-map",
        "0:v:0",
        "-map",
        "[aout]",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-shortest",
        str(output),
    ]


def _effect_name(effect: dict) -> str:
    name = effect.get("effect", effect.get("type", effect.get("name", "")))
    return str(name).strip().lower()


def _effect_window(effect: dict, segment: dict) -> tuple[float, float]:
    parameters = effect.get("parameters")
    parameters = parameters if isinstance(parameters, dict) else {}
    start = _number(parameters.get("start", effect.get("start", segment["start"])), "effect start")
    raw_end = parameters.get("end", effect.get("end"))
    if raw_end is None:
        duration = parameters.get("duration", effect.get("duration"))
        raw_end = start + _number(duration, "effect duration") if duration is not None else segment["end"]
    end = _number(raw_end, "effect end")
    segment_start = _number(segment["start"], "segment start")
    segment_end = _number(segment["end"], "segment end")
    if start < segment_start or start >= end or end > segment_end:
        raise ValueError("effect range must stay inside its approved segment")
    return start, end


def _enhance_piece_filters(manifest: dict, effect: dict | None, start: float, end: float) -> tuple[str, str]:
    video = f"trim=start={_fmt(start)}:end={_fmt(end)},setpts=PTS-STARTPTS"
    audio = f"atrim=start={_fmt(start)}:end={_fmt(end)},asetpts=PTS-STARTPTS"
    video_target, audio_target = _target_filters(manifest)
    if effect is None:
        return f"{video},{video_target}", f"{audio},{audio_target}"
    name = _effect_name(effect)
    if name in {"speed", "setpts", "setpts + atempo"}:
        parameters = effect.get("parameters")
        parameters = parameters if isinstance(parameters, dict) else {}
        speed = _number(parameters.get("speed", effect.get("speed")), "effect speed")
        if speed <= 0:
            raise ValueError("effect speed must be greater than 0")
        return f"{video},setpts=PTS/{_fmt(speed)},{video_target}", f"{audio},{atempo_chain(speed)},{audio_target}"
    duration = end - start
    if name == "fade":
        return f"{video},fade=t=in:st=0:d={_fmt(duration)},{video_target}", f"{audio},{audio_target}"
    if name == "flash":
        return f"{video},eq=brightness=1,{video_target}", f"{audio},{audio_target}"
    if name == "hard":
        return f"{video},{video_target}", f"{audio},{audio_target}"
    raise ValueError(f"unsupported enhancement effect: {name or '<unknown>'}")


def build_enhance_commands(manifest: dict, ffmpeg: str, output: Path) -> list[list[str]]:
    segments = validate_approved_segments(manifest)
    effects = manifest.get("effects", [])
    if any(effect.get("status") != "approved" for effect in effects):
        raise ValueError("enhancement effects must be approved")
    by_id = {str(segment.get("id")): segment for segment in segments}
    effects_by_segment: dict[str, list[tuple[float, float, dict]]] = {str(segment["id"]): [] for segment in segments}
    for effect in effects:
        segment_id = effect.get("segment_id")
        if not segment_id or str(segment_id) not in by_id:
            raise ValueError("effect must reference an approved segment")
        segment = by_id[str(segment_id)]
        name = _effect_name(effect)
        if name not in TRANSITIONS and name not in {"speed", "setpts", "setpts + atempo"}:
            raise ValueError(f"unsupported enhancement effect: {name or '<unknown>'}")
        start, end = _effect_window(effect, segment)
        effects_by_segment[str(segment_id)].append((start, end, effect))

    filters = []
    video_labels = []
    audio_labels = []
    input_paths = []
    for input_index, segment in enumerate(segments):
        input_paths.append(str(_source_path(segment, _sources(manifest))))
        segment_start = _number(segment["start"], "segment start")
        segment_end = _number(segment["end"], "segment end")
        windows = sorted(effects_by_segment[str(segment["id"])], key=lambda item: item[0])
        cursor = segment_start
        pieces = []
        for start, end, effect in windows:
            if start < cursor:
                raise ValueError("enhancement effect ranges must not overlap")
            if cursor < start:
                pieces.append((cursor, start, None))
            pieces.append((start, end, effect))
            cursor = end
        if cursor < segment_end:
            pieces.append((cursor, segment_end, None))
        for piece_index, (start, end, effect) in enumerate(pieces):
            video_filter, audio_filter = _enhance_piece_filters(manifest, effect, start, end)
            video_label = f"v{input_index}_{piece_index}"
            audio_label = f"a{input_index}_{piece_index}"
            filters.append(f"[{input_index}:v]{video_filter}[{video_label}]")
            filters.append(f"[{input_index}:a]{audio_filter}[{audio_label}]")
            video_labels.append(video_label)
            audio_labels.append(audio_label)
    video_inputs = "".join(f"[{label}]" for label in video_labels)
    audio_inputs = "".join(f"[{label}]" for label in audio_labels)
    filters.append(f"{video_inputs}concat=n={len(video_labels)}:v=1:a=0[vout]")
    filters.append(f"{audio_inputs}concat=n={len(audio_labels)}:v=0:a=1[aout]")
    output = _output_path(manifest, Path(output))
    command = [ffmpeg, "-n"]
    for input_path in input_paths:
        command.extend(["-i", input_path])
    command.extend(["-filter_complex", ";".join(filters), "-map", "[vout]", "-map", "[aout]", "-c:v", "libx264", "-c:a", "aac", str(output)])
    return [command]


def run_command(args: list[str]):
    return subprocess.run(args, check=True, shell=False)


def _render_duration(manifest: dict, mode: str, parent_version: str | None) -> float:
    if mode == "music":
        return _number(_approved_parent(manifest, parent_version)["duration"], "approved parent duration")
    segments = validate_approved_segments(manifest)
    duration = sum(_number(item["end"], "segment end") - _number(item["start"], "segment start") for item in segments)
    if mode == "enhance":
        by_id = {str(item["id"]): item for item in segments}
        for effect in manifest.get("effects", []):
            if _effect_name(effect) in {"speed", "setpts", "setpts + atempo"}:
                start, end = _effect_window(effect, by_id[str(effect["segment_id"])])
                parameters = effect.get("parameters") if isinstance(effect.get("parameters"), dict) else {}
                speed = _number(parameters.get("speed", effect.get("speed")), "effect speed")
                duration += (end - start) / speed - (end - start)
    return duration


def _write_manifest(path: Path, manifest: dict) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(manifest, handle, indent=2, ensure_ascii=False, allow_nan=False)
            handle.write("\n")
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def render_project(manifest_or_path: dict | Path | str, mode: str, ffmpeg: str = "ffmpeg", parent_version: str | None = None) -> dict:
    """Render one new candidate version and update an on-disk manifest when supplied."""
    if mode not in MODES:
        raise ValueError(f"unsupported render mode: {mode}")
    manifest_path = Path(manifest_or_path) if isinstance(manifest_or_path, (str, Path)) else None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path else manifest_or_path
    label = "enhanced" if mode == "enhance" else mode
    version_id = next_version(manifest, label)
    output = _output_path(manifest, Path(manifest["output_dir"]) / f"{version_id}.mp4")
    if mode == "draft":
        commands = build_draft_commands(manifest, ffmpeg, output)
        segment_ids = [segment.get("id") for segment in validate_approved_segments(manifest)]
    elif mode == "music":
        commands = [build_music_command(manifest, ffmpeg, output, parent_version)]
        segment_ids = []
    else:
        commands = build_enhance_commands(manifest, ffmpeg, output)
        segment_ids = [segment.get("id") for segment in validate_approved_segments(manifest)]
    for command in commands:
        run_command(command)
    record = {"id": version_id, "path": str(output), "duration": _render_duration(manifest, mode, parent_version), "input_segment_ids": segment_ids, "render_settings": {"mode": mode, "ffmpeg": ffmpeg}, "status": "candidate"}
    if parent_version:
        record["parent_version"] = parent_version
    manifest.setdefault("versions", []).append(record)
    if manifest_path:
        _write_manifest(manifest_path, manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("mode", choices=sorted(MODES))
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--parent-version")
    args = parser.parse_args(argv)
    render_project(args.manifest, args.mode, args.ffmpeg, args.parent_version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
