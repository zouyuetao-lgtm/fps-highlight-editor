import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "fps-highlight-editor"
    / "scripts"
    / "cleanup_project.py"
)
SPEC = importlib.util.spec_from_file_location("cleanup_project", SCRIPT)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(module)


def project_fixture(root: Path) -> tuple[Path, Path, dict[str, Path]]:
    output = root / "output"
    output.mkdir()
    files = {
        "source": output / "capture.mp4",
        "proxy": output / "proxy.mp4",
        "waveform": output / "waveform.png",
        "draft": output / "v01-draft.mp4",
        "approved": output / "v02-approved.mp4",
        "final": output / "v03-final.mp4",
        "version_artifact": output / "version-artifact.mp4",
        "report": output / "v03-final-verification.json",
        "license": output / "license.pdf",
        "music": output / "track.wav",
    }
    for name, path in files.items():
        path.write_text(name, encoding="utf-8")
    manifest_path = output / "edit-project.json"
    manifest = {
        "output_dir": str(output),
        "source_files": [{"id": "source-1", "path": str(files["source"])}],
        "versions": [
            {"id": "v01-draft", "path": str(files["draft"]), "status": "candidate"},
            {"id": "v02-approved", "path": str(files["approved"]), "status": "approved"},
            {"id": "v03-final", "path": str(files["final"]), "status": "final"},
        ],
        "final_version": "v03-final",
        "music": {"mode": "none"},
        "artifacts": [
            {"id": "proxy-1", "path": str(files["proxy"]), "category": "proxy"},
            {"id": "waveform-1", "path": str(files["waveform"]), "category": "waveform"},
            {"id": "report-1", "path": str(files["report"]), "category": "report"},
            {"id": "license-1", "path": str(files["license"]), "category": "license"},
            {"id": "music-1", "path": str(files["music"]), "category": "music-copy", "status": "approved"},
            {"id": "version-artifact-1", "path": str(files["version_artifact"]), "category": "version"},
        ],
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path, output, files


def write_plan(path: Path, plan: dict) -> None:
    path.write_text(json.dumps(plan), encoding="utf-8")


class CleanupProjectTests(unittest.TestCase):
    def assert_fixture_files_exist(self, files: dict[str, Path]) -> None:
        for name, path in files.items():
            self.assertTrue(path.exists(), name)

    def test_source_is_never_in_ordinary_cleanup_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest_path, _output, files = project_fixture(Path(directory))
            plan = module.build_plan(manifest_path)

            self.assertEqual(
                [entry["path"] for entry in plan["entries"]],
                [str(files["proxy"].resolve()), str(files["draft"].resolve()), str(files["waveform"].resolve())],
            )
            self.assertNotIn(str(files["source"].resolve()), [entry["path"] for entry in plan["entries"]])

    def test_candidate_version_is_planned_after_final_version_is_set(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest_path, _output, files = project_fixture(Path(directory))

            planned = {entry["path"] for entry in module.build_plan(manifest_path)["entries"]}

            self.assertIn(str(files["draft"].resolve()), planned)
            for name in ("approved", "final", "version_artifact"):
                self.assertNotIn(str(files[name].resolve()), planned)

    def test_versions_are_not_planned_without_final_version(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest_path, _output, files = project_fixture(Path(directory))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["final_version"] = None
            manifest["versions"][2]["status"] = "approved"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            planned = {entry["path"] for entry in module.build_plan(manifest_path)["entries"]}

            for name in ("draft", "approved", "final", "version_artifact"):
                self.assertNotIn(str(files[name].resolve()), planned)

    def test_manifest_record_no_longer_disposable_aborts_before_any_delete(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path, _output, files = project_fixture(root)
            plan = module.build_plan(manifest_path)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["artifacts"][0].update({"category": "segment", "status": "candidate"})
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            plan_path = root / "cleanup-plan.json"
            write_plan(plan_path, plan)

            with self.assertRaises(ValueError):
                module.execute_plan(plan_path, module.plan_digest(plan))

            self.assert_fixture_files_exist(files)

    def test_build_plan_rejects_unmatched_final_version(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest_path, _output, _files = project_fixture(Path(directory))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["final_version"] = "missing-version"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaises(ValueError):
                module.build_plan(manifest_path)

    def test_build_plan_rejects_final_pointer_to_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest_path, _output, _files = project_fixture(Path(directory))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["final_version"] = "v01-draft"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaises(ValueError):
                module.build_plan(manifest_path)

    def test_build_plan_rejects_multiple_final_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest_path, _output, _files = project_fixture(Path(directory))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["versions"][1]["status"] = "final"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaises(ValueError):
                module.build_plan(manifest_path)

    def test_malformed_source_record_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest_path, _output, files = project_fixture(Path(directory))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["source_files"] = [str(files["source"])]
            manifest["artifacts"].append(
                {"id": "source-alias", "path": str(files["source"]), "category": "proxy"}
            )
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaises(ValueError):
                module.build_plan(manifest_path)
            self.assertTrue(files["source"].exists())

    @unittest.skipUnless(os.name == "nt", "Windows path aliases are Windows-specific")
    def test_extended_path_alias_of_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest_path, _output, files = project_fixture(Path(directory))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["source_files"][0]["path"] = "\\\\?\\" + str(files["source"].resolve())
            manifest["artifacts"].append(
                {"id": "source-alias", "path": str(files["source"]), "category": "proxy"}
            )
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaises(ValueError):
                module.build_plan(manifest_path)
            self.assertTrue(files["source"].exists())

    @unittest.skipUnless(os.name == "nt", "alternate data streams are Windows-specific")
    def test_alternate_data_stream_candidate_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest_path, _output, files = project_fixture(Path(directory))
            ads = Path(str(files["source"]) + ":cleanup")
            ads.write_text("stream", encoding="utf-8")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["artifacts"].append(
                {"id": "source-ads", "path": str(ads), "category": "proxy"}
            )
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaises(ValueError):
                module.build_plan(manifest_path)
            self.assertTrue(files["source"].exists())

    def test_hardlink_to_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest_path, output, files = project_fixture(Path(directory))
            alias = output / "source-hardlink.mp4"
            os.link(files["source"], alias)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["artifacts"].append(
                {"id": "source-hardlink", "path": str(alias), "category": "proxy"}
            )
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaises(ValueError):
                module.build_plan(manifest_path)
            self.assertTrue(files["source"].exists())
            self.assertTrue(alias.exists())

    def test_execute_rejects_manifest_with_unmatched_final_version(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path, _output, files = project_fixture(root)
            plan = module.build_plan(manifest_path)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["final_version"] = "missing-version"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            plan_path = root / "cleanup-plan.json"
            write_plan(plan_path, plan)

            with self.assertRaises(ValueError):
                module.execute_plan(plan_path, module.plan_digest(plan))

            self.assert_fixture_files_exist(files)

    def test_outside_output_dir_aborts_before_any_delete(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path, _output, files = project_fixture(root)
            outside = root / "outside-proxy.mp4"
            outside.write_text("outside", encoding="utf-8")
            plan = module.build_plan(manifest_path)
            plan["entries"][0].update(
                {"path": str(outside.resolve()), "size": outside.stat().st_size, "mtime_ns": outside.stat().st_mtime_ns}
            )
            plan_path = root / "cleanup-plan.json"
            write_plan(plan_path, plan)

            with self.assertRaises(ValueError):
                module.execute_plan(plan_path, module.plan_digest(plan))

            self.assertTrue(outside.exists())
            self.assert_fixture_files_exist(files)

    def test_missing_confirmation_deletes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path, _output, files = project_fixture(root)
            plan = module.build_plan(manifest_path)
            plan_path = root / "cleanup-plan.json"
            write_plan(plan_path, plan)

            with self.assertRaises(ValueError):
                module.execute_plan(plan_path, "")

            self.assert_fixture_files_exist(files)

    def test_wrong_digest_deletes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path, _output, files = project_fixture(root)
            plan = module.build_plan(manifest_path)
            plan_path = root / "cleanup-plan.json"
            write_plan(plan_path, plan)

            with self.assertRaises(ValueError):
                module.execute_plan(plan_path, "0" * 64)

            self.assert_fixture_files_exist(files)

    def test_same_size_and_mtime_content_change_in_later_entry_aborts_all_deletes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path, _output, files = project_fixture(root)
            plan = module.build_plan(manifest_path)
            plan_path = root / "cleanup-plan.json"
            write_plan(plan_path, plan)
            stat = files["waveform"].stat()
            files["waveform"].write_text("changed!", encoding="utf-8")
            os.utime(files["waveform"], ns=(stat.st_atime_ns, stat.st_mtime_ns))

            with self.assertRaises(ValueError):
                module.execute_plan(plan_path, module.plan_digest(plan))

            self.assert_fixture_files_exist(files)

    def test_replaced_later_entry_with_same_content_aborts_all_deletes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path, _output, files = project_fixture(root)
            plan = module.build_plan(manifest_path)
            plan_path = root / "cleanup-plan.json"
            write_plan(plan_path, plan)
            stat = files["waveform"].stat()
            content = files["waveform"].read_text(encoding="utf-8")
            files["waveform"].unlink()
            files["waveform"].write_text(content, encoding="utf-8")
            os.utime(files["waveform"], ns=(stat.st_atime_ns, stat.st_mtime_ns))
            self.assertNotEqual(stat.st_ino, files["waveform"].stat().st_ino)

            with self.assertRaises(ValueError):
                module.execute_plan(plan_path, module.plan_digest(plan))

            self.assert_fixture_files_exist(files)

    def test_missing_protected_report_aborts_before_any_delete(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path, _output, files = project_fixture(root)
            plan = module.build_plan(manifest_path)
            plan_path = root / "cleanup-plan.json"
            write_plan(plan_path, plan)
            files["report"].unlink()

            with self.assertRaises(ValueError):
                module.execute_plan(plan_path, module.plan_digest(plan))

            for name, path in files.items():
                if name != "report":
                    self.assertTrue(path.exists(), name)

    def test_output_dir_junction_component_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path, output, _files = project_fixture(root)
            linked_output = root / "linked-output"
            if os.name != "nt":
                self.skipTest("junctions are Windows-specific")
            result = subprocess.run(
                ["cmd.exe", "/d", "/c", f"mklink /J {linked_output} {output}"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["output_dir"] = str(linked_output)
            manifest["artifacts"][0]["path"] = str(linked_output / "proxy.mp4")
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaises(ValueError):
                module.build_plan(manifest_path)

    def test_changed_size_in_later_entry_aborts_all_deletes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path, _output, files = project_fixture(root)
            plan = module.build_plan(manifest_path)
            plan_path = root / "cleanup-plan.json"
            write_plan(plan_path, plan)
            files["waveform"].write_text("waveform size changed", encoding="utf-8")

            with self.assertRaises(ValueError):
                module.execute_plan(plan_path, module.plan_digest(plan))

            self.assert_fixture_files_exist(files)

    def test_changed_mtime_in_later_entry_aborts_all_deletes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path, _output, files = project_fixture(root)
            plan = module.build_plan(manifest_path)
            plan_path = root / "cleanup-plan.json"
            write_plan(plan_path, plan)
            stat = files["waveform"].stat()
            os.utime(files["waveform"], ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
            self.assertNotEqual(stat.st_mtime_ns, files["waveform"].stat().st_mtime_ns)

            with self.assertRaises(ValueError):
                module.execute_plan(plan_path, module.plan_digest(plan))

            self.assert_fixture_files_exist(files)

    def test_exact_digest_deletes_only_listed_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path, _output, files = project_fixture(root)
            plan = module.build_plan(manifest_path)
            plan_path = root / "cleanup-plan.json"
            write_plan(plan_path, plan)

            result = module.execute_plan(plan_path, module.plan_digest(plan))

            self.assertEqual(
                result["deleted"],
                [str(files["proxy"].resolve()), str(files["draft"].resolve()), str(files["waveform"].resolve())],
            )
            self.assertFalse(files["proxy"].exists())
            self.assertFalse(files["draft"].exists())
            self.assertFalse(files["waveform"].exists())
            for name in ("source", "approved", "final", "report", "license", "music", "version_artifact"):
                self.assertTrue(files[name].exists(), name)

    def test_final_version_manifest_license_and_report_are_protected(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest_path, _output, files = project_fixture(Path(directory))
            plan = module.build_plan(manifest_path)
            planned = {entry["path"] for entry in plan["entries"]}

            for name in ("approved", "final", "report", "license", "version_artifact"):
                self.assertNotIn(str(files[name].resolve()), planned)
            self.assertNotIn(str(manifest_path.resolve()), planned)


if __name__ == "__main__":
    unittest.main()
