import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "fps-highlight-editor"
    / "scripts"
    / "validate_output.py"
)
SPEC = importlib.util.spec_from_file_location("validate_output", SCRIPT)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(module)


VOLUME_SUMMARY = """mean_volume: -19.0 dB
max_volume: -1.9 dB
"""
EBUR_SUMMARY = """I: -17.2 LUFS
LRA: 8.3 LU
Peak: -1.9 dBFS
"""


def probe_fixture(*, fps="60/1", audio=True, format_name="mov,mp4,m4a,3gp,3g2,mj2", duration="12.5"):
    streams = [
        {
            "index": 0,
            "codec_type": "video",
            "codec_name": "h264",
            "width": 1920,
            "height": 1080,
            "avg_frame_rate": fps,
            "duration": duration,
        }
    ]
    if audio:
        streams.append({"index": 1, "codec_type": "audio", "codec_name": "aac"})
    return {"streams": streams, "format": {"duration": duration, "format_name": format_name}}


def target_fixture(**overrides):
    target = {"container": "mp4", "fps": 60, "duration": 12.5}
    target.update(overrides)
    return target


def successful_measurement(values):
    return {"exit_code": 0, "values": values}


class ValidateOutputTests(unittest.TestCase):
    def test_parse_volume_summary_extracts_exact_decibel_values(self):
        self.assertEqual(
            module.parse_volume_summary(VOLUME_SUMMARY),
            {"mean_volume": -19.0, "max_volume": -1.9},
        )

    def test_parse_ebur_summary_extracts_exact_loudness_values(self):
        self.assertEqual(
            module.parse_ebur_summary(EBUR_SUMMARY),
            {"integrated_lufs": -17.2, "lra_lu": 8.3, "true_peak_dbfs": -1.9},
        )

    def test_probe_output_uses_ffprobe_json_and_reports_stream_properties(self):
        completed = type("Completed", (), {"returncode": 0, "stdout": json.dumps(probe_fixture()), "stderr": ""})()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "v01-draft.mp4"
            output.touch()
            with patch.object(module.subprocess, "run", return_value=completed) as run:
                result = module.probe_output(output, "fake-ffprobe")
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["fps"], 60.0)
        self.assertTrue(result["has_audio"])
        self.assertEqual(run.call_args.args[0][0], "fake-ffprobe")
        self.assertFalse(run.call_args.kwargs["shell"])

    def test_validation_fails_when_full_decode_exits_nonzero(self):
        result = module.validate_result(
            probe_output=module.probe_output_from_json(probe_fixture()),
            decode={"exit_code": 1},
            packet_hash="abc",
            volume=module.parse_volume_summary(VOLUME_SUMMARY),
            ebur=module.parse_ebur_summary(EBUR_SUMMARY),
            target=target_fixture(),
            file_size=10,
        )
        self.assertFalse(result["passed"])

    def test_validation_fails_when_audio_stream_is_missing(self):
        result = module.validate_result(
            probe_output=module.probe_output_from_json(probe_fixture(audio=False)),
            decode={"exit_code": 0},
            packet_hash="abc",
            volume=module.parse_volume_summary(VOLUME_SUMMARY),
            ebur=module.parse_ebur_summary(EBUR_SUMMARY),
            target=target_fixture(),
            file_size=10,
        )
        self.assertFalse(result["passed"])

    def test_validation_fails_when_output_fps_differs_from_target(self):
        result = module.validate_result(
            probe_output=module.probe_output_from_json(probe_fixture(fps="30/1")),
            decode={"exit_code": 0},
            packet_hash="abc",
            volume=module.parse_volume_summary(VOLUME_SUMMARY),
            ebur=module.parse_ebur_summary(EBUR_SUMMARY),
            target=target_fixture(),
            file_size=10,
        )
        self.assertFalse(result["passed"])

    def test_validation_fails_when_true_peak_is_above_minus_one_dbfs(self):
        ebur = module.parse_ebur_summary("I: -17.2 LUFS\nLRA: 8.3 LU\nPeak: -0.5 dBFS\n")
        result = module.validate_result(
            probe_output=module.probe_output_from_json(probe_fixture()),
            decode={"exit_code": 0},
            packet_hash="abc",
            volume=module.parse_volume_summary(VOLUME_SUMMARY),
            ebur=ebur,
            target=target_fixture(),
            file_size=10,
        )
        self.assertFalse(result["passed"])

    def test_validation_passes_when_all_required_measurements_are_valid(self):
        result = module.validate_result(
            probe_output=module.probe_output_from_json(probe_fixture()),
            decode={"exit_code": 0},
            packet_hash={"exit_code": 0, "sha256": "a" * 64},
            volume=successful_measurement(module.parse_volume_summary(VOLUME_SUMMARY)),
            ebur=successful_measurement(module.parse_ebur_summary(EBUR_SUMMARY)),
            target=target_fixture(),
            file_size=10,
            qc_frame={"exit_code": 0, "path": "qc.jpg"},
        )
        self.assertTrue(result["passed"])
        self.assertEqual(result["sha256"], "a" * 64)

    def test_validation_fails_for_wrong_container_or_duration(self):
        common = dict(
            decode={"exit_code": 0},
            packet_hash={"exit_code": 0, "sha256": "a" * 64},
            volume=successful_measurement(module.parse_volume_summary(VOLUME_SUMMARY)),
            ebur=successful_measurement(module.parse_ebur_summary(EBUR_SUMMARY)),
            target=target_fixture(),
            file_size=10,
            qc_frame={"exit_code": 0, "path": "qc.jpg"},
        )
        wrong_container = module.validate_result(
            probe_output=module.probe_output_from_json(probe_fixture(format_name="matroska,webm")),
            **common,
        )
        wrong_duration = module.validate_result(
            probe_output=module.probe_output_from_json(probe_fixture(duration="8.0")),
            **common,
        )
        self.assertFalse(wrong_container["passed"])
        self.assertFalse(wrong_duration["passed"])

    def test_validation_fails_when_measurement_or_qc_command_fails(self):
        result = module.validate_result(
            probe_output=module.probe_output_from_json(probe_fixture()),
            decode={"exit_code": 0},
            packet_hash={"exit_code": 0, "sha256": "a" * 64},
            volume={"exit_code": 1, "values": module.parse_volume_summary(VOLUME_SUMMARY)},
            ebur=successful_measurement(module.parse_ebur_summary(EBUR_SUMMARY)),
            target=target_fixture(),
            file_size=10,
            qc_frame={"exit_code": 1, "path": "qc.jpg"},
        )
        self.assertFalse(result["passed"])
        self.assertFalse(result["checks"]["measurements"])
        self.assertFalse(result["checks"]["qc_frame"])

    def test_measurement_keeps_filter_summary_visible_at_non_error_log_level(self):
        completed = type("Completed", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        def fake_run(command, **_kwargs):
            if command[command.index("-v") + 1] != "error":
                completed.stderr = VOLUME_SUMMARY
            return completed

        with patch.object(module.subprocess, "run", side_effect=fake_run) as run:
            result = module._measurement(Path("output.mp4"), "fake-ffmpeg", "volumedetect")
        self.assertEqual(result["values"], {"mean_volume": -19.0, "max_volume": -1.9})
        command = run.call_args.args[0]
        self.assertNotEqual(command[command.index("-v") + 1], "error")

    def test_cli_refuses_to_overwrite_existing_protected_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "v01-draft.mp4"
            report = root / "v01-draft-verification.json"
            output.touch()
            report.write_text("protected", encoding="utf-8")
            with patch.object(module, "validate_output", return_value={"passed": True}):
                with self.assertRaises(FileExistsError):
                    module.main(
                        [
                            str(output),
                            "--target",
                            '{"fps": 60}',
                            "--report",
                            str(report),
                        ]
                    )
            self.assertEqual(report.read_text(encoding="utf-8"), "protected")


if __name__ == "__main__":
    unittest.main()
