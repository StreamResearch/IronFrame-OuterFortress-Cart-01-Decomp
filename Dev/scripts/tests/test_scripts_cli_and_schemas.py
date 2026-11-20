# @module: IronFrame.Dev.scripts.tests.test_scripts_cli_and_schemas
# @purpose: Offline unit tests for shared CLI helpers, synthetic/missing-media CLI gates, and Standard 18 v2 schemas
# @depends-on: json, re, subprocess, sys, tempfile, unittest, pathlib
# @exports: TestCliCommonAndScripts, TestSchemasAndSlocLimits

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SCRIPTS_DIR.parents[1]
SCHEMAS_DIR = REPO_ROOT / "Dev" / "schemas"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import nes_cli_common as ncc  # noqa: E402
import build_and_verify_d4 as d4  # noqa: E402

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_HEX8_RE = re.compile(r"^[0-9a-f]{8}$")
_TRADEMARK_WORDS = ("kon" + "ami", "metal " + "gear")


def _run_py(script_name: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPTS_DIR / script_name), *args],
        capture_output=True, text=True, check=False,
    )


class TestCliCommonAndScripts(unittest.TestCase):
    def test_common_helpers_and_log_writer(self) -> None:
        paths = ncc.resolve_paths()
        self.assertEqual(paths.project_root, REPO_ROOT)
        self.assertIn(ncc.detect_host_zig_target(), ("x86_64-windows-gnu", "x86-windows-gnu", "x86_64-linux-gnu", "x86-linux-gnu", "aarch64-linux-gnu", "aarch64-macos-none", "x86_64-macos-none"))
        entries = ncc.iter_integrity_entries({
            "entries": [{"relativePath": "extracted/A.prg", "fileSizeBytes": 4, "sha256Hex": "ab" * 32, "crc32Hex": "12345678"}]
        })
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0][0], "extracted/A.prg")
        with tempfile.TemporaryDirectory(prefix="t_ncc_log_") as tmp:
            ldir = Path(tmp) / "logs"
            ncc.write_json_log(ldir, "unit_probe", ncc.missing_media_payload(tmp, ["data/rom/*.nes"], "missing"))
            logged = json.loads((ldir / "unit_probe.log").read_text(encoding="utf-8"))
            self.assertEqual(logged["errorCode"], "MISSING_CORPUS_MEDIA")

    def test_offline_synthetic_and_missing_media_cli_gates(self) -> None:
        with tempfile.TemporaryDirectory(prefix="t_cli_gates_") as tmp:
            troot = Path(tmp)
            empty_data = troot / "empty_data"
            empty_data.mkdir()

            p_gen_v = _run_py("gen_d4_globals_and_lifts.py", "--verify-only")
            self.assertEqual(p_gen_v.returncode, 0, p_gen_v.stderr)
            self.assertTrue(json.loads(p_gen_v.stdout)["isPassed"])

            p_gen_s = _run_py("gen_d4_globals_and_lifts.py", "--offline-synthetic", "--out-dir", str(troot / "gen_out"))
            self.assertEqual(p_gen_s.returncode, 0, p_gen_s.stderr)
            self.assertEqual(json.loads((troot / "gen_out" / "spec_coverage.json").read_text(encoding="utf-8"))["unresolvedFieldCount"], 0)

            p_d5_s = _run_py("build_and_verify_d5.py", "--offline-synthetic", "--out-dir", str(troot / "d5_out"))
            self.assertEqual(p_d5_s.returncode, 0, p_d5_s.stderr)
            d5_rep = json.loads(p_d5_s.stdout)
            self.assertEqual((d5_rep["matchedBinaryCount"], d5_rep["mismatchedBytes"]), (8, 0))

            p_rx_s = _run_py("reexport_stage3.py", "--offline-synthetic", "--data-dir", str(empty_data))
            self.assertEqual(p_rx_s.returncode, 0, p_rx_s.stderr)
            self.assertTrue(json.loads(p_rx_s.stdout)["isPassed"])

            for script in ("gen_d4_globals_and_lifts.py", "build_and_verify_d5.py", "build_and_verify_d4.py", "reexport_stage3.py", "verify_track_d5.py"):
                res = _run_py(script, "--data-dir", str(empty_data))
                self.assertEqual(res.returncode, 2, f"{script} expected rc=2, got {res.returncode}: {res.stdout} {res.stderr}")
                self.assertEqual(json.loads(res.stdout)["errorCode"], "MISSING_CORPUS_MEDIA")

    def test_d4_generators_and_optional_zig_synthetic(self) -> None:
        with tempfile.TemporaryDirectory(prefix="t_d4_gen_") as tmp:
            troot = Path(tmp)
            gh, gd = troot / "g.h", troot / "g.c"
            gh.write_text("extern uint8_t g_test_arr[];\nextern uint8_t g_flag;\n", encoding="utf-8")
            self.assertEqual(d4.generate_globals_defs(gh, gd), 2)
            self.assertIn("g_test_arr[256] = {0};", gd.read_text(encoding="utf-8"))

            fh, sc = troot / "f.h", troot / "stubs.c"
            fh.write_text("byte sample_fn(byte x);\n", encoding="utf-8")
            self.assertEqual(d4.generate_host_stubs(fh, troot / "none.h", set(), sc), 1)
            self.assertIn("(void)x; return (byte)0;", sc.read_text(encoding="utf-8"))

            try:
                ncc.resolve_zig_executable()
            except FileNotFoundError:
                return
            p_d4_s = _run_py("build_and_verify_d4.py", "--offline-synthetic", "--out-dir", str(troot / "d4_out"))
            self.assertEqual(p_d4_s.returncode, 0, p_d4_s.stderr)
            self.assertTrue(json.loads(p_d4_s.stdout)["isPassed"])


class TestSchemasAndSlocLimits(unittest.TestCase):
    def test_standalone_integrity_and_core_schemas_v2(self) -> None:
        integ = json.loads((SCHEMAS_DIR / "standalone_integrity.json").read_text(encoding="utf-8"))
        self.assertEqual(integ["schemaVersion"], 2)
        self.assertEqual(len(integ["entries"]), 17)
        self.assertFalse(any("ghidra_" in e["relativePath"].lower() for e in integ["entries"]))
        rom = integ["requiredRomChecksums"][0]
        self.assertEqual(rom["expectedSizeBytes"], 131088)
        self.assertRegex(rom["expectedSha256"], _HEX64_RE)
        self.assertRegex(rom["crc32Hex"], _HEX8_RE)
        for item in integ["entries"]:
            self.assertRegex(item["sha256Hex"], _HEX64_RE)
            self.assertRegex(item["crc32Hex"], _HEX8_RE)

        cg = json.loads((SCHEMAS_DIR / "call_graph.json").read_text(encoding="utf-8"))
        self.assertEqual(cg.get("strings", []), [])
        cat = json.loads((SCHEMAS_DIR / "functions_catalog.json").read_text(encoding="utf-8"))
        funcs = cat if isinstance(cat, list) else cat.get("functions", [])
        self.assertEqual(len(funcs), 499)
        cat_low = json.dumps(cat).lower()
        self.assertFalse(any(t in cat_low for t in _TRADEMARK_WORDS))

    def test_script_and_harness_sloc_caps(self) -> None:
        for fp in sorted(SCRIPTS_DIR.rglob("*.py")):
            if "__pycache__" in fp.parts:
                continue
            lines = fp.read_text(encoding="utf-8").splitlines()
            sloc = sum(1 for ln in lines if ln.strip() and not ln.lstrip().startswith("#"))
            cap = 265 if fp.name == "asm6502_d5.py" else 250
            self.assertLessEqual(sloc, cap, f"{fp.name} SLOC {sloc} > {cap}")
        for fp in sorted((SCRIPTS_DIR / "d4_harness").glob("*")):
            if fp.is_file() and fp.suffix.lower() in (".c", ".h"):
                self.assertLessEqual(len(fp.read_text(encoding="utf-8").splitlines()), 250)


if __name__ == "__main__":
    unittest.main()
