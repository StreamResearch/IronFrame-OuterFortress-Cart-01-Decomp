# @module: IronFrame.Dev.scripts.tests.test_d4b_and_decoders
# @purpose: Unit tests for D4b lockstep/spoke validators and unconditional D4b/decoder CLI gates
# @depends-on: json, pathlib, subprocess, sys, tempfile, unittest, d4b_validation_helpers, export_decomp_bundle, nes_cli_common
# @exports: TestD4bValidationHelpers, TestD4bLockstepAndDecoderClis

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import d4b_validation_helpers as d4bh  # noqa: E402
import export_decomp_bundle as edb  # noqa: E402
from nes_cli_common import GAME_ID  # noqa: E402

_D4B_CLI_SCRIPTS = (
    "run_d4b_lockstep.py",
    "decode_rooms_and_metatiles.py",
    "decode_guards_and_weapons.py",
    "decode_codec_and_audio.py",
    "decode_all_bank_tables.py",
)


def _valid_lockstep_payload() -> dict[str, Any]:
    return {
        "schemaVersion": 2,
        "gameId": GAME_ID,
        "generatedAtUtc": "2026-11-23T01:00:00.000Z",
        "oracleType": "mesen",
        "mismatchedFrames": 0,
        "isPassed": True,
        "assertionsPassedCount": 7,
        "assertionsTotalCount": 7,
        "checks": [
            {"name": name, "isPassed": True, "detail": f"{name} crc=1234abcd sha256={'a' * 64}"}
            for name in d4bh.REQUIRED_D4B_CHECKS
        ],
        "notes": f"digest_summary={'0' * 64}",
    }


def _valid_spec_coverage(with_checks: bool = True) -> dict[str, Any]:
    base: dict[str, Any] = {
        "schemaVersion": 2,
        "gameId": GAME_ID,
        "generatedAtUtc": "2026-11-23T01:00:00.000Z",
        "isPassed": True,
        "totalFunctionCount": 499,
        "namedFunctionCount": 499,
        "totalGlobalCount": 2324,
        "mappedGlobalCount": 2324,
        "definedStructCount": 22,
        "definedEnumCount": 22,
        "unresolvedFieldCount": 0,
    }
    if with_checks:
        base.update({
            "assertionsPassedCount": 4,
            "assertionsTotalCount": 4,
            "checks": [
                {"name": f"decoder_check_{i}", "isPassed": True, "detail": "resolved=100%"}
                for i in range(4)
            ],
            "notes": "All ROM tables resolved cleanly.",
        })
    return base


def _seed_dev_spokes(dev_dir: Path, spokes: tuple[str, ...] = d4bh.REQUIRED_SPEC_SPOKES, line_count: int = 24) -> None:
    (dev_dir / "schemas").mkdir(parents=True, exist_ok=True)
    sp_dir = dev_dir / "docs" / "specifications"
    sp_dir.mkdir(parents=True, exist_ok=True)
    for old in sp_dir.glob("*.md"):
        old.unlink()
    (dev_dir / "schemas" / "spec_coverage.json").write_text(json.dumps(_valid_spec_coverage(), indent=2), encoding="utf-8")
    body = "\n".join(["# Clean-Room Structural Specification", ""] + [f"- Entry {i:02d}: bank offset metadata" for i in range(line_count)])
    for name in spokes:
        (sp_dir / name).write_text(body + "\n", encoding="utf-8")


class TestD4bValidationHelpers(unittest.TestCase):
    def test_helpers_lockstep_valid_and_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="t_d4b_ok_") as tmp:
            sc = Path(tmp) / "schemas"
            sc.mkdir()
            ok_opt, msg_opt = d4bh.validate_d4b_lockstep_report(sc, require_exists=False)
            self.assertTrue(ok_opt, msg_opt)
            ok_req, _ = d4bh.validate_d4b_lockstep_report(sc, require_exists=True)
            self.assertFalse(ok_req)

            (sc / "d4b_lockstep_report.json").write_text(json.dumps(_valid_lockstep_payload(), indent=2), encoding="utf-8")
            ok_val, msg_val = d4bh.validate_d4b_lockstep_report(sc, require_exists=True)
            self.assertTrue(ok_val, msg_val)

    def test_helpers_lockstep_rejects_invalid_and_raw_dumps(self) -> None:
        with tempfile.TemporaryDirectory(prefix="t_d4b_bad_") as tmp:
            sc = Path(tmp) / "schemas"
            sc.mkdir()
            rp = sc / "d4b_lockstep_report.json"

            bad_cases: list[tuple[str, dict[str, Any]]] = []
            p1 = _valid_lockstep_payload(); p1["oracleType"] = "recart_interpreter_oracle"
            bad_cases.append(("bad_oracle", p1))
            p2 = _valid_lockstep_payload(); p2["mismatchedFrames"] = 2
            bad_cases.append(("mismatched_frames", p2))
            p3 = _valid_lockstep_payload(); p3["isPassed"] = False
            bad_cases.append(("failed_flag", p3))
            p4 = _valid_lockstep_payload(); p4["assertionsPassedCount"] = 6
            bad_cases.append(("short_assertions", p4))
            p5 = _valid_lockstep_payload(); p5["checks"] = p5["checks"][:-1]; p5["assertionsPassedCount"] = 6; p5["assertionsTotalCount"] = 6
            bad_cases.append(("missing_witness", p5))
            p6 = _valid_lockstep_payload(); p6["checks"][-1]["isPassed"] = False
            bad_cases.append(("failing_witness", p6))
            p7 = _valid_lockstep_payload(); p7["secondaryOracles"] = ["recart"]
            bad_cases.append(("unregistered_secondary", p7))
            p8 = _valid_lockstep_payload(); p8["passed"] = True
            bad_cases.append(("legacy_v1_key", p8))
            p9 = _valid_lockstep_payload(); p9["rawRam"] = "00"
            bad_cases.append(("raw_ram_key", p9))
            p10 = _valid_lockstep_payload(); p10["wramDump"] = "00"
            bad_cases.append(("wram_dump_key", p10))
            p11 = _valid_lockstep_payload(); p11["checks"][0]["detail"] = "dump=" + ("ab" * 65)
            bad_cases.append(("large_hex_blob", p11))
            p12 = _valid_lockstep_payload(); p12["notes"] = "brand " + "kon" + "ami leak"
            bad_cases.append(("trademark_leak", p12))

            for label, payload in bad_cases:
                rp.write_text(json.dumps(payload), encoding="utf-8")
                ok, msg = d4bh.validate_d4b_lockstep_report(sc, require_exists=True)
                self.assertFalse(ok, f"Expected failure for {label}, got pass: {msg}")

    def test_helpers_spec_spokes_and_coverage(self) -> None:
        with tempfile.TemporaryDirectory(prefix="t_spokes_") as tmp:
            dev = Path(tmp) / "Dev"
            _seed_dev_spokes(dev)
            ok, msg = d4bh.validate_spec_spokes_and_coverage(dev)
            self.assertTrue(ok, msg)

            (dev / "schemas" / "spec_coverage.json").write_text(json.dumps(_valid_spec_coverage(with_checks=False)), encoding="utf-8")
            self.assertTrue(d4bh.validate_spec_spokes_and_coverage(dev)[0])

            for key, bad_val in (("unresolvedFieldCount", 1), ("isPassed", False), ("mappedGlobalCount", 2300), ("extraBadKey", 1)):
                bad_cov = _valid_spec_coverage()
                bad_cov[key] = bad_val
                (dev / "schemas" / "spec_coverage.json").write_text(json.dumps(bad_cov), encoding="utf-8")
                self.assertFalse(d4bh.validate_spec_spokes_and_coverage(dev)[0], f"Missed bad spec_coverage {key}")
            (dev / "schemas" / "spec_coverage.json").unlink()
            self.assertFalse(d4bh.validate_spec_spokes_and_coverage(dev)[0])

            _seed_dev_spokes(dev, spokes=d4bh.REQUIRED_SPEC_SPOKES[:1])
            self.assertFalse(d4bh.validate_spec_spokes_and_coverage(dev, require_all_spokes=True)[0])
            self.assertTrue(d4bh.validate_spec_spokes_and_coverage(dev, require_all_spokes=False)[0])

            _seed_dev_spokes(dev, line_count=5)
            self.assertFalse(d4bh.validate_spec_spokes_and_coverage(dev)[0])

            for leak in ("kon" + "ami", "ja" + "nov", "fi" + "le:///tmp", "C:\\Use" + "rs\\foo"):
                _seed_dev_spokes(dev)
                spoke = dev / "docs" / "specifications" / d4bh.REQUIRED_SPEC_SPOKES[1]
                spoke.write_text(spoke.read_text(encoding="utf-8") + f"\n{leak}\n", encoding="utf-8")
                self.assertFalse(d4bh.validate_spec_spokes_and_coverage(dev)[0], f"Missed leak: {leak}")
                self.assertEqual(edb.validate_cleanroom_bytes("Dev/scripts/tests/test_d4b_and_decoders.py", Path(__file__).read_bytes(), strict=True), [])


class TestD4bLockstepAndDecoderClis(unittest.TestCase):
    def test_lockstep_and_decoders_synthetic_and_missing_media(self) -> None:
        with tempfile.TemporaryDirectory(prefix="t_d4b_clis_") as tmp:
            troot = Path(tmp)
            empty_data, log_dir = troot / "empty_data", troot / "logs"
            empty_data.mkdir()
            for idx, script in enumerate(_D4B_CLI_SCRIPTS):
                out_dir = troot / f"syn_{idx}"
                syn = subprocess.run(
                    [sys.executable, "-B", str(SCRIPTS_DIR / script), "--offline-synthetic", "--out-dir", str(out_dir), "--log-dir", str(log_dir)],
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(syn.returncode, 0, f"{script} synthetic failed: {syn.stdout} {syn.stderr}")
                self.assertTrue(json.loads(syn.stdout)["isPassed"], f"{script} synthetic isPassed!=True")

                miss = subprocess.run(
                    [sys.executable, "-B", str(SCRIPTS_DIR / script), "--data-dir", str(empty_data)],
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(miss.returncode, 2, f"{script} missing-media expected rc=2, got {miss.returncode}: {miss.stdout} {miss.stderr}")
                self.assertEqual(json.loads(miss.stdout)["errorCode"], "MISSING_CORPUS_MEDIA")


if __name__ == "__main__":
    unittest.main()
