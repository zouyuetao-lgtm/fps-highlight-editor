import importlib.util
import tempfile
import unittest
from unittest import mock
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "fps-highlight-editor"
    / "scripts"
    / "render_project.py"
)
SPEC = importlib.util.spec_from_file_location("render_project", SCRIPT)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(module)


def manifest_fixture(output_dir: Path) -> dict:
    return {
        "output_dir": str(output_dir),
        "target": {"width": 1920, "height": 1080, "fps": 60},
        "source_files": [
            {"id": "source-1", "path": str(output_dir / "capture.mp4"), "duration": 30.0}
        ],
        "candidates": [
            {"id": "candidate-1", "source_id": "source-1", "start": 1.0, "end": 6.0, "status": "approved"},
            {"id": "candidate-proposed", "source_id": "source-1", "start": 6.0, "end": 8.0, "status": "proposed"},
        ],
        "segments": [
            {
                "id": "segment-1",
                "candidate_id": "candidate-1",
                "source_id": "source-1",
                "start": 2.0,
                "end": 5.0,
                "status": "approved",
            }
        ],
        "versions": [
            {"id": "v01-draft", "path": str(output_dir / "v01-draft.mp4"), "status": "candidate"},
            {"id": "v02-music", "path": str(output_dir / "v02-music.mp4"), "status": "approved", "duration": 3.0},
            {"id": "v03-enhanced", "path": str(output_dir / "v03-enhanced.mp4"), "status": "candidate"},
        ],
        "music": {
            "mode": "provided",
            "status": "approved",
            "path": str(output_dir / "track.wav"),
            "source_start": 12.5,
            "gain": -10.0,
            "fade_in": 0.5,
            "fade_out": 1.25,
            "approval_confirmed": True,
            "music_copy_artifact_id": "music-copy-1",
            "authorization_artifact_id": "authorization-1",
        },
        "artifacts": [
            {"id": "music-copy-1", "path": str(output_dir / "track.wav"), "category": "music-copy", "status": "approved"},
            {"id": "authorization-1", "path": str(output_dir / "authorization.txt"), "category": "license", "status": "approved"},
        ],
        "effects": [],
    }


class RenderProjectTests(unittest.TestCase):
    def test_rejects_unapproved_segment(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = manifest_fixture(Path(directory))
            manifest["segments"].append(
                {
                    "id": "segment-proposed",
                    "candidate_id": "candidate-proposed",
                    "source_id": "source-1",
                    "start": 6.0,
                    "end": 8.0,
                    "status": "proposed",
                }
            )
            with self.assertRaisesRegex(ValueError, "approved"):
                module.validate_approved_segments(manifest)

    def test_next_version_never_reuses_existing_name(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = manifest_fixture(Path(directory))
            self.assertEqual(module.next_version(manifest, "enhanced"), "v04-enhanced")

    def test_atempo_chain_stays_within_ffmpeg_limits(self):
        self.assertEqual(module.atempo_chain(4.0), "atempo=2.0,atempo=2.0")
        self.assertEqual(module.atempo_chain(0.25), "atempo=0.5,atempo=0.5")

    def test_music_command_uses_approved_mix_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = manifest_fixture(root)
            (root / "track.wav").touch()
            (root / "authorization.txt").touch()
            command = module.build_music_command(manifest, "ffmpeg", root / "v04-music.mp4")
            rendered = " ".join(command)
            self.assertIn(str(root / "v02-music.mp4"), rendered)
            self.assertEqual(rendered.count("12.5"), 1)
            self.assertIn("volume=-10.0dB", rendered)
            self.assertIn("afade=t=in:st=0:d=0.5", rendered)
            self.assertIn("afade=t=out:st=1.75:d=1.25", rendered)
            self.assertIn("sidechaincompress", rendered)
            self.assertIn("amix=inputs=2:duration=first", rendered)
            self.assertIn("apad", rendered)
            self.assertIn("alimiter=level=0", rendered)

    def test_music_command_requires_recorded_rights_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = manifest_fixture(root)
            (root / "track.wav").touch()
            (root / "authorization.txt").touch()
            manifest["music"].pop("approval_confirmed")

            with self.assertRaisesRegex(ValueError, "rights|approval"):
                module.build_music_command(manifest, "ffmpeg", root / "v04-music.mp4")

    def test_music_command_rejects_mismatched_copy_or_missing_authorization(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = manifest_fixture(root)
            (root / "track.wav").touch()
            (root / "other.wav").touch()
            (root / "authorization.txt").touch()
            manifest["artifacts"][0]["path"] = str(root / "other.wav")
            with self.assertRaisesRegex(ValueError, "music-copy"):
                module.build_music_command(manifest, "ffmpeg", root / "v04-music.mp4")

            manifest["artifacts"][0]["path"] = str(root / "track.wav")
            (root / "authorization.txt").unlink()
            with self.assertRaisesRegex(ValueError, "authorization"):
                module.build_music_command(manifest, "ffmpeg", root / "v04-music.mp4")

    def test_segment_must_match_approved_candidate_source_and_range(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = manifest_fixture(Path(directory))
            manifest["source_files"].append(
                {"id": "source-2", "path": str(Path(directory) / "other.mp4"), "duration": 30.0}
            )
            manifest["segments"][0]["source_id"] = "source-2"
            with self.assertRaisesRegex(ValueError, "candidate"):
                module.validate_approved_segments(manifest)

            manifest["segments"][0]["source_id"] = "source-1"
            manifest["segments"][0]["start"] = 0.5
            with self.assertRaisesRegex(ValueError, "candidate"):
                module.validate_approved_segments(manifest)

    def test_draft_command_contains_only_approved_ranges(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = manifest_fixture(root)
            command = module.build_draft_commands(manifest, "ffmpeg", root / "v04-draft.mp4")[0]
            self.assertIn("-ss", command)
            self.assertIn("2.0", command)
            self.assertIn("-t", command)
            self.assertIn("3.0", command)
            self.assertNotIn("proposed", " ".join(command))
            self.assertFalse(any(item == "-to" for item in command))
            rendered = " ".join(command)
            self.assertIn("scale=1920:1080", rendered)
            self.assertIn("fps=60.0", rendered)
            self.assertIn("format=yuv420p", rendered)
            self.assertIn("aresample=48000", rendered)

    def test_run_command_disables_shell(self):
        with mock.patch.object(module.subprocess, "run") as run:
            run.return_value = object()
            module.run_command(["ffmpeg", "-version"])
            self.assertFalse(run.call_args.kwargs["shell"])

    def test_rendered_version_records_expected_duration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = manifest_fixture(root)
            with mock.patch.object(module, "run_command"):
                result = module.render_project(manifest, "draft", "ffmpeg")
            self.assertEqual(result["versions"][-1]["duration"], 3.0)

    def test_enhance_speed_only_applies_inside_approved_effect_range(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = manifest_fixture(root)
            manifest["effects"] = [
                {
                    "id": "effect-speed",
                    "segment_id": "segment-1",
                    "status": "approved",
                    "type": "speed",
                    "start": 3.0,
                    "end": 4.0,
                    "speed": 2.0,
                }
            ]
            command = module.build_enhance_commands(manifest, "ffmpeg", root / "v04-enhanced.mp4")[0]
            rendered = " ".join(command)
            self.assertIn("trim=start=2.0:end=3.0", rendered)
            self.assertIn("trim=start=3.0:end=4.0", rendered)
            self.assertIn("setpts=PTS/2.0", rendered)
            self.assertIn("atempo=2.0", rendered)

    def test_enhance_effects_use_minimal_stable_semantics(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rendered = {}
            for name in ("fade", "flash", "hard"):
                manifest = manifest_fixture(root)
                manifest["effects"] = [
                    {
                        "id": f"effect-{name}",
                        "segment_id": "segment-1",
                        "status": "approved",
                        "type": name,
                        "parameters": {"start": 3.0, "duration": 0.5},
                    }
                ]
                rendered[name] = " ".join(
                    module.build_enhance_commands(manifest, "ffmpeg", root / f"v04-{name}.mp4")[0]
                )
            self.assertIn("fade=", rendered["fade"])
            self.assertIn("eq=", rendered["flash"])
            self.assertNotIn("drawbox=", rendered["hard"])
            self.assertNotIn("fade=", rendered["hard"])

    def test_command_builders_require_new_version_paths_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = manifest_fixture(root)
            (root / "track.wav").touch()
            (root / "authorization.txt").touch()
            builders = (
                lambda output: module.build_draft_commands(manifest, "ffmpeg", output)[0],
                lambda output: module.build_music_command(manifest, "ffmpeg", output),
                lambda output: module.build_enhance_commands(manifest, "ffmpeg", output)[0],
            )
            for builder in builders:
                with self.subTest(builder=builder):
                    with self.assertRaises(ValueError):
                        builder(root / "draft.mp4")
                    existing = root / "v04-draft.mp4"
                    existing.touch()
                    with self.assertRaises(ValueError):
                        builder(existing)
                    existing.unlink()
                    command = builder(root / "v04-draft.mp4")
                    self.assertIn("-n", command)
                    self.assertNotIn("-y", command)


if __name__ == "__main__":
    unittest.main()
