"""Validate a rendered MP4 against a project's target settings."""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
from pathlib import Path
from typing import Any


_RATE_RE = re.compile(r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*/\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*$")
_VOLUME_RE = {
    "mean_volume": re.compile(r"mean_volume:\s*([-+]?\d+(?:\.\d+)?)\s+dB", re.MULTILINE),
    "max_volume": re.compile(r"max_volume:\s*([-+]?\d+(?:\.\d+)?)\s+dB", re.MULTILINE),
}
_EBUR_RE = {
    "integrated_lufs": re.compile(r"(?:^|\])\s*I:\s*([-+]?\d+(?:\.\d+)?)\s+LUFS", re.MULTILINE),
    "lra_lu": re.compile(r"(?:^|\])\s*LRA:\s*([-+]?\d+(?:\.\d+)?)\s+LU", re.MULTILINE),
    "true_peak_dbfs": re.compile(r"(?:^|\])\s*Peak:\s*([-+]?\d+(?:\.\d+)?)\s+dBFS", re.MULTILINE),
}


def _run(command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        shell=False,
        check=False,
    )
    return {
        "exit_code": int(getattr(completed, "returncode", 1)),
        "stdout": getattr(completed, "stdout", "") or "",
        "stderr": getattr(completed, "stderr", "") or "",
    }


def _number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _rate(value: object) -> float | None:
    text = str(value).strip()
    if not text or text in {"N/A", "0/0"}:
        return None
    match = _RATE_RE.match(text)
    try:
        result = float(match.group(1)) / float(match.group(2)) if match else float(text)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    return result if math.isfinite(result) and result > 0 else None


def _probe_json(data: dict[str, Any], exit_code: int = 0, stderr: str = "") -> dict[str, Any]:
    streams = data.get("streams") if isinstance(data, dict) else None
    streams = streams if isinstance(streams, list) else []
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
    video = video if isinstance(video, dict) else {}
    audio = audio if isinstance(audio, dict) else {}
    fps = None
    for value in (video.get("avg_frame_rate"), video.get("r_frame_rate")):
        fps = _rate(value)
        if fps is not None:
            break
    format_data = data.get("format") if isinstance(data, dict) else {}
    format_data = format_data if isinstance(format_data, dict) else {}
    duration = _number(video.get("duration"))
    if duration is None:
        duration = _number(format_data.get("duration"))
    return {
        "exit_code": exit_code,
        "stderr": stderr,
        "streams": streams,
        "duration": duration,
        "format_name": format_data.get("format_name"),
        "fps": fps,
        "width": video.get("width"),
        "height": video.get("height"),
        "video_codec": video.get("codec_name"),
        "audio_codec": audio.get("codec_name") if audio else None,
        "has_video": bool(video),
        "has_audio": bool(audio),
    }


def probe_output(path: Path | str, ffprobe: str = "ffprobe") -> dict[str, Any]:
    """Probe streams and duration with FFprobe, retaining its exit code."""
    result = _run(
        [
            ffprobe,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(Path(path).resolve()),
        ]
    )
    if result["exit_code"] != 0:
        return _probe_json({}, result["exit_code"], result["stderr"])
    try:
        data = json.loads(result["stdout"])
    except (TypeError, json.JSONDecodeError):
        return _probe_json({}, result["exit_code"], result["stderr"] or "invalid ffprobe JSON")
    return _probe_json(data, result["exit_code"], result["stderr"])


def probe_output_from_json(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize a decoded FFprobe payload (useful at the subprocess boundary)."""
    return _probe_json(data)


def decode_all(path: Path | str, ffmpeg: str = "ffmpeg") -> dict[str, Any]:
    """Decode the entire output and return FFmpeg's exit code and diagnostics."""
    return _run([ffmpeg, "-v", "error", "-i", str(Path(path).resolve()), "-f", "null", "-"])


def packet_hash(path: Path | str, ffmpeg: str = "ffmpeg") -> dict[str, Any]:
    """Hash video packets without decoding them, using FFmpeg's hash muxer."""
    result = _run(
        [
            ffmpeg,
            "-v",
            "error",
            "-i",
            str(Path(path).resolve()),
            "-map",
            "0:v:0",
            "-c",
            "copy",
            "-f",
            "hash",
            "-hash",
            "sha256",
            "-",
        ]
    )
    match = re.search(r"(?:SHA256=)?([0-9a-fA-F]{64})", result["stdout"])
    result["sha256"] = match.group(1).lower() if match else None
    return result


def parse_volume_summary(text: str) -> dict[str, float | None]:
    """Parse FFmpeg ``volumedetect`` output without inventing absent values."""
    values = {}
    for key, pattern in _VOLUME_RE.items():
        match = pattern.search(text)
        values[key] = _number(match.group(1)) if match else None
    return values


def parse_ebur_summary(text: str) -> dict[str, float | None]:
    """Parse FFmpeg ``ebur128=peak=true`` output without inventing absent values."""
    values = {}
    for key, pattern in _EBUR_RE.items():
        match = pattern.search(text)
        values[key] = _number(match.group(1)) if match else None
    return values


def _command_result(value: dict[str, Any] | int | None) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {"exit_code": value if isinstance(value, int) else None}


def validate_result(
    probe_output: dict[str, Any] | Path | str,
    decode: dict[str, Any] | int | None = None,
    packet_hash: dict[str, Any] | str | None = None,
    volume: dict[str, Any] | None = None,
    ebur: dict[str, Any] | None = None,
    target: dict[str, Any] | None = None,
    file_size: int | None = None,
    source_hash: str | None = None,
    qc_frame: dict[str, Any] | None = None,
    *,
    ffmpeg: str = "ffmpeg",
    ffprobe: str = "ffprobe",
) -> dict[str, Any]:
    """Evaluate normalized measurements against the manifest target."""
    if isinstance(probe_output, (str, Path)):
        if target is None and isinstance(decode, dict):
            target = decode
        if target is None:
            raise ValueError("target is required")
        return validate_output(probe_output, target, ffmpeg, ffprobe, source_hash)
    if target is None:
        raise ValueError("target is required")
    probe = _command_result(probe_output)
    decode_result = _command_result(decode)
    packet = _command_result(packet_hash if isinstance(packet_hash, dict) else None)
    if isinstance(packet_hash, str):
        packet["sha256"] = packet_hash
    volume_result = _command_result(volume)
    ebur_result = _command_result(ebur)
    volume_values = volume_result.get("values") if isinstance(volume_result.get("values"), dict) else {}
    ebur_values = ebur_result.get("values") if isinstance(ebur_result.get("values"), dict) else {}
    qc_result = _command_result(qc_frame)
    expected_fps = _number(target.get("fps"))
    actual_fps = _number(probe.get("fps"))
    expected_duration = _number(target.get("duration"))
    actual_duration = _number(probe.get("duration"))
    format_names = {name.strip().lower() for name in str(probe.get("format_name") or "").split(",") if name.strip()}
    expected_container = str(target.get("container") or "").lower()
    container_ok = expected_container in format_names
    duration_tolerance = max(0.1, 2.0 / expected_fps) if expected_fps else 0.1
    checks = {
        "probe": probe.get("exit_code") == 0 and bool(probe.get("has_video")),
        "decode": decode_result.get("exit_code") == 0,
        "audio": bool(probe.get("has_audio")),
        "fps": expected_fps is not None and actual_fps is not None and abs(actual_fps - expected_fps) < 0.001,
        "container": bool(expected_container) and container_ok,
        "duration": expected_duration is not None and actual_duration is not None and abs(actual_duration - expected_duration) <= duration_tolerance,
        "measurements": volume_result.get("exit_code") == 0 and ebur_result.get("exit_code") == 0,
        "true_peak": _number(ebur_values.get("true_peak_dbfs")) is not None and _number(ebur_values.get("true_peak_dbfs")) <= -1.0,
        "packet_hash": packet.get("exit_code") in (None, 0) and bool(packet.get("sha256")),
        "file": file_size is not None and file_size >= 0,
        "qc_frame": qc_result.get("exit_code") == 0 and bool(qc_result.get("path")),
    }
    for key in ("width", "height", "video_codec", "audio_codec"):
        expected = target.get(key)
        if expected is not None:
            checks[key] = probe.get(key) == expected
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "target": target,
        "probe": probe,
        "decode": decode_result,
        "packet_hash": packet,
        "sha256": packet.get("sha256"),
        "volume": volume_result,
        "ebur": ebur_result,
        "qc_frame": qc_result,
        "file_size": file_size,
        "source_hash": source_hash,
    }


def _measurement(output: Path, ffmpeg: str, filter_name: str) -> dict[str, Any]:
    result = _run([ffmpeg, "-v", "info", "-i", str(output.resolve()), "-af", filter_name, "-f", "null", "-"])
    parsed = parse_volume_summary(result["stderr"]) if filter_name == "volumedetect" else parse_ebur_summary(result["stderr"])
    result["values"] = parsed
    return result


def _qc_frame(output: Path, ffmpeg: str, duration: float) -> dict[str, Any]:
    path = output.with_name(f"{output.stem}-qc.jpg")
    result = _run(
        [ffmpeg, "-v", "error", "-n", "-ss", f"{duration / 2:g}", "-i", str(output), "-frames:v", "1", "-q:v", "2", str(path)]
    )
    result["path"] = str(path) if result["exit_code"] == 0 and path.is_file() else None
    return result


def validate_output(
    output: Path | str,
    target: dict[str, Any],
    ffmpeg: str = "ffmpeg",
    ffprobe: str = "ffprobe",
    source_hash: str | None = None,
) -> dict[str, Any]:
    """Run all probes and measurements, returning a JSON-serializable report."""
    output = Path(output).resolve()
    probe = probe_output(output, ffprobe)
    decode = decode_all(output, ffmpeg)
    packets = packet_hash(output, ffmpeg)
    volume_command = _measurement(output, ffmpeg, "volumedetect")
    ebur_command = _measurement(output, ffmpeg, "ebur128=peak=true")
    expected_duration = _number(target.get("duration"))
    qc_command = _qc_frame(output, ffmpeg, expected_duration) if expected_duration is not None else {"exit_code": 1, "path": None, "stderr": "target duration is required"}
    report = validate_result(
        probe_output=probe,
        decode=decode,
        packet_hash=packets,
        volume=volume_command,
        ebur=ebur_command,
        target=target,
        file_size=output.stat().st_size if output.is_file() else None,
        source_hash=source_hash,
        qc_frame=qc_command,
    )
    report["commands"] = {"probe": probe, "decode": decode, "packet_hash": packets, "volume": volume_command, "ebur": ebur_command, "qc_frame": qc_command}
    return report


def _target_from_args(args: argparse.Namespace) -> dict[str, Any]:
    if args.target:
        value = Path(args.target)
        if value.is_file():
            return json.loads(value.read_text(encoding="utf-8"))
        return json.loads(args.target)
    if args.manifest:
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        target = dict(manifest["target"])
        output = args.output.resolve()
        matches = [
            version for version in manifest.get("versions", [])
            if Path(str(version.get("path", ""))).resolve() == output
        ]
        if len(matches) != 1 or _number(matches[0].get("duration")) is None:
            raise ValueError("manifest must contain one output version with duration")
        target["duration"] = _number(matches[0]["duration"])
        return target
    raise ValueError("target JSON or manifest is required")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--target", help="target JSON object or JSON file")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument("--source-hash")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    report = validate_output(args.output, _target_from_args(args), args.ffmpeg, args.ffprobe, args.source_hash)
    report_path = args.report or args.output.with_name(f"{args.output.stem}-verification.json")
    with report_path.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
