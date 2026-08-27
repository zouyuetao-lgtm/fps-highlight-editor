import importlib.util
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest.mock import patch


SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "fps-highlight-editor"
    / "scripts"
    / "inspect_media.py"
)
SPEC = importlib.util.spec_from_file_location("inspect_media", SCRIPT)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(module)


class InspectMediaTests(unittest.TestCase):
    def test_parse_rate_handles_fraction(self):
        self.assertEqual(module.parse_rate("60/1"), 60.0)

    def test_parse_rate_rejects_non_positive_or_non_finite_values(self):
        for value in ("nan", "inf", "-inf", "0", "-1"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    module.parse_rate(value)

    def test_probe_file_falls_back_to_valid_r_frame_rate(self):
        probe = {
            "streams": [
                {
                    "codec_type": "video",
                    "avg_frame_rate": "0/0",
                    "r_frame_rate": "30/1",
                    "width": 1920,
                    "height": 1080,
                }
            ],
            "format": {"duration": "1.0"},
        }
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "clip.mp4"
            source.touch()
            with patch.object(module, "run_json", return_value=probe):
                self.assertEqual(module.probe_file(source, "ffprobe")["fps"], 30.0)

    def test_discover_media_is_sorted_and_ignores_non_media(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "b.mp4").touch()
            (root / "a.mkv").touch()
            (root / "notes.txt").touch()
            self.assertEqual(
                [path.name for path in module.discover_media(root)],
                ["a.mkv", "b.mp4"],
            )

    def test_create_manifest_keeps_low_native_fps(self):
        manifest = module.create_manifest(
            source_files=[
                {
                    "id": "source-1",
                    "path": "clip.mp4",
                    "fps": 30.0,
                    "duration": 12.5,
                }
            ],
            output_dir=Path("output"),
            game="valorant",
            target_fps=60,
        )
        self.assertEqual(manifest["target"]["fps"], 30.0)
        self.assertIn("source_fps_below_requested", manifest["warnings"])

    def test_create_manifest_caps_high_native_fps_at_requested_rate(self):
        manifest = module.create_manifest(
            [{"path": "clip.mp4", "fps": 120.0, "duration": 1.0}],
            Path("output"),
            "valorant",
            60,
        )
        self.assertEqual(manifest["target"]["fps"], 60.0)

    def test_manifest_write_refuses_to_replace_existing_project(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "edit-project.json"
            path.write_text('{"keep": true}', encoding="utf-8")

            with self.assertRaises(FileExistsError):
                module._write_json_atomic(path, {"replace": True})

            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"keep": True})

    def test_create_manifest_rejects_invalid_target_and_source_fps(self):
        for target_fps in (float("nan"), float("inf"), 0, -1):
            with self.subTest(target_fps=target_fps):
                with self.assertRaises(ValueError):
                    module.create_manifest([], Path("output"), "valorant", target_fps)
        for source_fps in (float("nan"), float("inf"), 0, -1):
            with self.subTest(source_fps=source_fps):
                with self.assertRaises(ValueError):
                    module.create_manifest(
                        [{"path": "clip.mp4", "fps": source_fps}],
                        Path("output"),
                        "valorant",
                        60,
                    )

    def test_cli_reports_invalid_target_fps(self):
        error = StringIO()
        with redirect_stderr(error):
            with self.assertRaises(SystemExit) as raised:
                module.main(
                    [
                        "missing.mp4",
                        "--output-dir",
                        "output",
                        "--game",
                        "valorant",
                        "--target-fps",
                        "nan",
                    ]
                )
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("target FPS", error.getvalue())


if __name__ == "__main__":
    unittest.main()
