# @module: IronFrame.Dev.scripts.tests.test_nes_unpack_and_asm
# @purpose: Offline unit tests for asm6502_d5, nes_6502_cfg, and nes_unrom_unpack
# @depends-on: json, subprocess, sys, tempfile, unittest, pathlib
# @exports: TestAsm6502D5, TestNes6502Cfg, TestNesUnromUnpack

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SCRIPTS_DIR.parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import asm6502_d5  # noqa: E402
import nes_6502_cfg as cfg  # noqa: E402
import nes_unrom_unpack as unpack  # noqa: E402


class TestAsm6502D5(unittest.TestCase):
    def test_opcode_table_counts(self) -> None:
        self.assertEqual(len(asm6502_d5.OPCODES), 56)
        self.assertEqual(sum(len(modes) for modes in asm6502_d5.OPCODES.values()), 151)

    def test_assemble_text_and_round_trip(self) -> None:
        src = (
            "ZP_TEMP = $10\n"
            "    .org $C000\n"
            "entry:\n"
            "    LDA #$42\n"
            "    STA ZP_TEMP\n"
            "    BEQ entry\n"
            "    JMP a:entry\n"
            "    RTS\n"
            "    .byte $DE, $AD\n"
            "    .word entry\n"
        )
        raw, origin, syms = asm6502_d5.assemble_text(src)
        self.assertEqual(origin, 0xC000)
        self.assertEqual(syms["entry"], 0xC000)
        expected = bytes([0xA9, 0x42, 0x85, 0x10, 0xF0, 0xFA, 0x4C, 0x00, 0xC0, 0x60, 0xDE, 0xAD, 0x00, 0xC0])
        self.assertEqual(raw, expected)


class TestNes6502Cfg(unittest.TestCase):
    def test_parse_ines_and_reject_invalid(self) -> None:
        rom = unpack.build_synthetic_unrom_rom()
        parsed = cfg.parse_ines(rom)
        self.assertEqual(parsed["mapper"], 2)
        self.assertEqual(parsed["prg_banks"], 8)
        self.assertTrue(parsed["is_nes2"])
        self.assertEqual(len(parsed["prg_data"]), 8 * cfg.BANK_SIZE)
        with self.assertRaises(ValueError):
            cfg.parse_ines(b"BAD!" + b"\x00" * 32)

    def test_trace_smart_and_bank_propagation(self) -> None:
        rom = unpack.build_synthetic_unrom_rom()
        prg = cfg.parse_ines(rom)["prg_data"]
        fixed = prg[7 * cfg.BANK_SIZE :]
        mem_fixed = prg[: cfg.BANK_SIZE] + fixed
        insns, code_bytes, funcs = cfg.trace_smart(mem_fixed, [0xC000, 0xC010], 0xC000, 0xFFFA)
        self.assertIn(0xC010, insns)
        self.assertIn(0xC932, funcs)
        self.assertTrue(code_bytes)
        ivs = cfg.to_intervals(code_bytes, 0xC000, 0xFFFA)
        self.assertTrue(ivs)
        cross = cfg.propagate_bank_calls(mem_fixed, {0xC010})
        self.assertIn(0x8001, cross[0])


class TestNesUnromUnpack(unittest.TestCase):
    def _run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPTS_DIR / "nes_unrom_unpack.py"), *args],
            capture_output=True, text=True, check=False,
        )

    def test_unpack_and_sealed_corpus_guard(self) -> None:
        with tempfile.TemporaryDirectory(prefix="t_unrom_") as tmp:
            troot = Path(tmp)
            rom_bytes = unpack.build_synthetic_unrom_rom(troot / "synth.nes")
            out_dir = troot / "extracted"
            res = unpack.unpack_unrom_bytes(rom_bytes, "synth.nes", out_dir, write_files=True)
            self.assertEqual(len(res["written_files"]), 17)
            layout = json.loads((out_dir / "nes_bank_layout.json").read_text(encoding="utf-8"))
            self.assertEqual(layout["prg_banks"], 8)
            self.assertEqual(len(layout["programs"]), 8)
        with self.assertRaises(ValueError):
            unpack._assert_safe_out_dir(REPO_ROOT / "Corpus" / "standalone" / "extracted", REPO_ROOT)

    def test_cli_synthetic_verify_mismatch_and_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="t_unrom_cli_") as tmp:
            troot = Path(tmp)
            synth_out = troot / "synth_out"
            log_dir = troot / "logs"
            p_synth = self._run_cli("--offline-synthetic", "--out-dir", str(synth_out), "--log-dir", str(log_dir))
            self.assertEqual(p_synth.returncode, 0, p_synth.stderr)
            d_synth = json.loads(p_synth.stdout)
            self.assertTrue(d_synth["isPassed"])
            self.assertEqual(d_synth["extractedFileCount"], 17)
            self.assertTrue((log_dir / "nes_unrom_unpack.log").is_file())

            v_out = troot / "verify_only_out"
            p_vo = self._run_cli("--offline-synthetic", "--verify-only", "--out-dir", str(v_out))
            self.assertEqual(p_vo.returncode, 0)
            self.assertFalse(v_out.exists())

            bad_rom = troot / "bad.nes"
            bad_rom.write_bytes(b"NES\x1a" + b"\x00" * 1024)
            p_bad = self._run_cli("--rom", str(bad_rom))
            self.assertEqual(p_bad.returncode, 1)
            self.assertEqual(json.loads(p_bad.stdout)["errorCode"], "CHECKSUM_MISMATCH")

            empty_dir = troot / "empty_data"
            empty_dir.mkdir()
            p_miss = self._run_cli("--data-dir", str(empty_dir))
            self.assertEqual(p_miss.returncode, 2)
            self.assertEqual(json.loads(p_miss.stdout)["errorCode"], "MISSING_CORPUS_MEDIA")


if __name__ == "__main__":
    unittest.main()
