# @module: IronFrame.Dev.scripts.tests.test_decomp_cleanroom_and_release
# @purpose: Offline clean-room validator, deterministic .decomp exporter, and Tier R release packager unit tests
# @depends-on: json, shutil, sys, tempfile, unittest, zipfile, pathlib
# @exports: TestDecompBundleCleanroom, TestPackageRelease

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SCRIPTS_DIR.parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import export_decomp_bundle as edb  # noqa: E402
import package_release as pkg_rel  # noqa: E402


def _stage_temp_repo_copy(dst_root: Path) -> None:
    dst_root.mkdir(parents=True, exist_ok=True)
    root_files = (
        "README.md", "FEATURES.md", "ROADMAP.md", "CHANGELOG.md", "SECURITY.md",
        "CONTRIBUTING.md", "LICENSE", ".gitignore", ".gitattributes", "active.state",
    )
    for name in root_files:
        src = REPO_ROOT / name
        if src.is_file():
            shutil.copy2(src, dst_root / name)
    for rel_dir in (".github", "Dev/assets", "Dev/docs/specifications", "Dev/docs/findings", "Dev/docs/stages", "Dev/schemas", "Dev/scripts"):
        src_d = REPO_ROOT / rel_dir
        if src_d.is_dir():
            shutil.copytree(src_d, dst_root / rel_dir, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.tmp*"))
    for doc_md in ("ARCHITECTURE.md", "SPECIFICATIONS.md", "FINDINGS.md", "OPERATIONS.md"):
        src_f = REPO_ROOT / "Dev" / "docs" / doc_md
        if src_f.is_file():
            (dst_root / "Dev" / "docs").mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_f, dst_root / "Dev" / "docs" / doc_md)
    shutil.copy2(REPO_ROOT / "Dev" / "research.manifest.json", dst_root / "Dev" / "research.manifest.json")


class TestDecompBundleCleanroom(unittest.TestCase):
    def test_recipe_and_deterministic_strict_export(self) -> None:
        recipe = edb.load_decomp_recipe()
        manifest = edb.build_module_decomp_manifest(recipe)
        self.assertEqual(manifest["moduleId"], "ironframe-outerfortress-cart-01")
        self.assertEqual(manifest["engineId"], "reCart")
        self.assertEqual(manifest["upstreamResearchPath"], "IronFrame-OuterFortress-Cart-01-Decomp")
        self.assertEqual(manifest["packageVersion"], "0.3.0")
        self.assertEqual(manifest["targetDecompTier"], "D4")
        self.assertEqual(manifest["decompSchemaVersion"], "1.0.0")

        with tempfile.TemporaryDirectory(prefix="t_decomp_exp_") as tmp:
            troot = Path(tmp)
            out1, out2 = troot / "one.decomp", troot / "two.decomp"
            r1 = edb.export_decomp_bundle(out_path=out1, verify_cleanroom=True, strict=True, log_dir=troot / "logs")
            r2 = edb.export_decomp_bundle(out_path=out2, verify_cleanroom=True, strict=True)
            self.assertTrue(r1["isPassed"])
            self.assertEqual(r1["sha256Hex"], r2["sha256Hex"])
            self.assertEqual(out1.read_bytes(), out2.read_bytes())
            self.assertEqual(edb.validate_cleanroom_archive(out1, strict=True), [])
            with zipfile.ZipFile(out1, "r") as zf:
                names = set(zf.namelist())
            self.assertIn("module.decomp.json", names)
            self.assertIn("Dev/schemas/d3_module_map.json", names)
            self.assertIn("Dev/schemas/d3_symbol_overrides.json", names)
            self.assertIn("Dev/schemas/d4_build_report.json", names)
            self.assertIn("Dev/schemas/d4_rewrites/core_runtime.json", names)
            self.assertIn("Dev/schemas/d4_rewrites/overlays_b05_b06.json", names)
            self.assertFalse(any(n.startswith(("Dev/scripts/d4_harness/", "Dev/scripts/tests/")) for n in names))

    def test_cleanroom_rejects_forbidden_inputs(self) -> None:
        self.assertTrue(edb.validate_cleanroom_bytes("Dev/x.bin", b"NES\x1a\x08\x00"))
        self.assertTrue(edb.validate_cleanroom_bytes("Dev/x.h", b"void retail_fn(void) { return; }"))
        self.assertTrue(edb.validate_cleanroom_bytes("Dev/x.json", ('{"c' + 'Body": "int x() {}"}').encode("utf-8")))
        self.assertTrue(edb.validate_cleanroom_bytes("Dev/schemas/call_graph.json", b'{"functions": {}, "strings": ["s"]}'))
        self.assertTrue(edb.validate_cleanroom_bytes("Dev/x.md", ("C:\\Users\\ja" + "nov\\x").encode("utf-8"), strict=True))
        self.assertTrue(edb.validate_cleanroom_bytes("Dev/x.md", ("brand " + "kon" + "ami").encode("utf-8"), strict=True))
        self.assertTrue(edb.validate_cleanroom_bytes("Dev/x.g.cs", b"// generated"))

        with tempfile.TemporaryDirectory(prefix="t_decomp_bad_") as tmp:
            bad_zip = Path(tmp) / "bad.decomp"
            with zipfile.ZipFile(bad_zip, "w") as zf:
                zf.writestr("Dev/schemas/d4_build_report.json", json.dumps({
                    "isZeroDecompilerTellsVerified": False,
                    "isZeroWarningsVerified": True,
                }))
            errs = edb.validate_cleanroom_archive(bad_zip)
            self.assertTrue(any(e.startswith("missing_root_manifest:") for e in errs))
            self.assertTrue(any(e.startswith("rejected_d4_build_report:") for e in errs))


class TestPackageRelease(unittest.TestCase):
    def test_stage_and_audit_release_invariants(self) -> None:
        with tempfile.TemporaryDirectory(prefix="t_pkg_rel_") as tmp:
            troot = Path(tmp)
            fake_repo = troot / "repo"
            stage_dir = troot / "stage"
            _stage_temp_repo_copy(fake_repo)
            st_p = fake_repo / "active.state"
            st_d = json.loads(st_p.read_text(encoding="utf-8"))
            st_d["version"] = json.loads((fake_repo / "Dev/research.manifest.json").read_text(encoding="utf-8"))["version"]
            st_p.write_text(json.dumps(st_d, indent=2) + "\n", encoding="utf-8")
            has_7z = pkg_rel._find_7z() is not None
            rep = pkg_rel.package_release(out_dir=stage_dir, repo_root=fake_repo, log_dir=troot / "logs", make_7z=has_7z)
            self.assertTrue(rep["isPassed"])
            latest = stage_dir / "Latest"
            self.assertEqual(len(list(latest.iterdir())), 7)
            sums = (latest / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(sums), 6)
            zip_path = latest / rep["zipName"]
            with zipfile.ZipFile(zip_path, "r") as zf:
                names = set(zf.namelist())
            self.assertFalse(any(n.lower().endswith("agents.md") for n in names))
            self.assertEqual(len([n for n in names if n.lower().endswith(".decomp")]), 1)
            vo = pkg_rel.package_release(out_dir=stage_dir, repo_root=fake_repo, make_7z=has_7z, verify_only=True)
            self.assertTrue(vo["isPassed"])

            (latest / "README.md").write_text("tampered\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                pkg_rel.package_release(out_dir=stage_dir, repo_root=fake_repo, make_7z=has_7z, verify_only=True)


if __name__ == "__main__":
    unittest.main()
