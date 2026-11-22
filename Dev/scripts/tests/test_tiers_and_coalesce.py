# @module: IronFrame.Dev.scripts.tests.test_tiers_and_coalesce
# @purpose: Offline unit tests for D3/D4 symbol overrides, AST craftsmanship rules, rewrite shards, and tier materialization
# @depends-on: json, pathlib, shutil, subprocess, sys, tempfile, unittest, coalesce_d4_modules, craftsmanship_d4_ast_cleaner, craftsmanship_d4_helpers, export_decomp_bundle, materialize_decomp_tiers
# @exports: TestTiersAndCoalesce, TestD4Craftsmanship

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

TESTS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = TESTS_DIR.parent
PROJECT_ROOT = SCRIPTS_DIR.parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import coalesce_d4_modules as coal  # noqa: E402
import craftsmanship_d4_ast_cleaner as ast_cl  # noqa: E402
import craftsmanship_d4_helpers as cd4h  # noqa: E402
import export_decomp_bundle as edb  # noqa: E402
import materialize_decomp_tiers as mdt  # noqa: E402

BANKS = ("BANK_00.prg", "BANK_01.prg", "BANK_02.prg", "BANK_03.prg", "BANK_04.prg", "BANK_05.prg", "BANK_06.prg", "PRG_FIXED_07.prg")


class TestTiersAndCoalesce(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schemas = coal.load_d3_schemas(PROJECT_ROOT / "Dev" / "schemas")
        cls.rewriter = coal.build_symbol_rewriter(cls.schemas)

    def test_rewrite_raw_patterns_and_override_precedence(self) -> None:
        sample = "\n".join([
            "BYTE_ARRAY_8000_6486_:",
            "  BYTE_ARRAY_bf00[0] = FUN_b622[1];",
            "  DAT_0740 = (&DAT_0740)[2] + DAT_0741;",
            "  _DAT_00db = (uint16_t)(bRAM07e1 + uRAM00b9 + _g_oam_cycle_flag + _g_zp_scratch_91 + register0x22);",
            "  FUN_99a8(1); FUN_f5ac(2); func_0x8120(); func_0xc68b(0);",
            "  if (BYTE_ARRAY_ff99[0]) goto BYTE_ARRAY_8000_6486_;",
            "  val = (g_frame_counter & BYTE_ARRAY_b995[0]) + (uint8_t)(&DAT_0740)[1];",
        ])
        rewritten = coal.rewrite_c_text(sample, self.rewriter)
        self.assertEqual(coal.RAW_SYMBOL_RE.findall(rewritten), [], rewritten)
        self.assertIn("lbl_demo_input_loop:", rewritten)
        self.assertIn("g_b03_rom_tbl_bf00[0] = g_b01_rom_tbl_b622[1];", rewritten)
        self.assertNotIn("g_b02_rom_bf00", rewritten)
        self.assertIn("g_vram_transfer_queue[0] = g_vram_transfer_queue[2] + g_wram_0741;", rewritten)
        self.assertIn("g_audio_seq_ptr_00db", rewritten)
        self.assertIn("g_fixed_tbl_ff99[0]", rewritten)
        self.assertIn("(g_frame_counter & g_b00_rom_tbl_b995[0])", rewritten)

    def test_coalesce_synthetic_tree_headers_and_trampolines(self) -> None:
        with tempfile.TemporaryDirectory(prefix="d3_unit_") as tmp:
            root = Path(tmp)
            src, dst = root / "D2_Structured", root / "D3_Mapped"
            for sub in ("include", "src/core", "overlays/BANK_03.prg"):
                (src / sub).mkdir(parents=True, exist_ok=True)
            (src / "include" / "ghidra_compat.h").write_text("#pragma once\n#include <stdint.h>\ntypedef uint8_t byte;\n", encoding="utf-8")
            (src / "include" / "metalgear_types.h").write_text('#pragma once\n#include "ghidra_compat.h"\n', encoding="utf-8")
            (src / "include" / "metalgear_globals.h").write_text('#pragma once\nextern uint8_t DAT_0740;\n', encoding="utf-8")
            (src / "include" / "metalgear_functions.h").write_text(
                '#pragma once\nvoid unrom_restore_active_bank(void);\n/* Cross-bank / raw */\nvoid FUN_99a8(byte s);\n',
                encoding="utf-8",
            )
            (src / "src/core/core_01.c").write_text(
                '/** @address 0x0000c9b0 */\n// Function: unrom_restore_active_bank @ 0x0000c9b0\n'
                'void unrom_restore_active_bank(void) { DAT_0740 = BYTE_ARRAY_bf00[0]; }\n',
                encoding="utf-8",
            )
            (src / "overlays/BANK_03.prg/bank_03_01.c").write_text(
                '/** @address 0x0000be73 */\n// Function: mg_b034_bank03_check_room_radio_triggers @ 0x0000be73\n'
                'void mg_b034_bank03_check_room_radio_triggers(void) { FUN_99a8(1); FUN_f5ac(0); }\n',
                encoding="utf-8",
            )
            res = coal.coalesce_tier_dir(src, dst, PROJECT_ROOT / "Dev" / "schemas")
            self.assertTrue(res["isPassed"])
            self.assertEqual(res["moduleCount"], 2)
            self.assertEqual(coal.scan_raw_symbols(dst), [])
            core_u = (dst / "src/core/core_unrom_and_math.c").read_text(encoding="utf-8")
            for tramp in self.schemas["overrides"]["trampolineDeclarations"]:
                self.assertIn(tramp["name"], core_u)
            fh = (dst / "include/metalgear_functions.h").read_text(encoding="utf-8")
            self.assertNotIn("FUN_99a8", fh)
            gh = (dst / "include/metalgear_globals.h").read_text(encoding="utf-8")
            self.assertIn("g_b03_rom_tbl_bf00", gh)

    def test_materialize_offline_synthetic_and_missing_media(self) -> None:
        with tempfile.TemporaryDirectory(prefix="mdt_unit_") as tmp:
            tpath = Path(tmp)
            rep = mdt.materialize_tiers(data_dir=tpath / "syn", offline_synthetic=True)
            self.assertTrue(rep["isPassed"])
            self.assertEqual(rep["tiers"]["D1_Raw"]["binaryCount"], 8)
            self.assertEqual(rep["tiers"]["D2_Structured"]["cFileCount"], 2)
            self.assertEqual(rep["tiers"]["D3_Mapped"]["cFileCount"], 3)
            self.assertEqual(rep["tiers"]["D4_CleanSource"]["cFileCount"], 3)
            self.assertEqual(rep["tiers"]["D4_CleanSource"]["tellCount"], 0)
            self.assertEqual(coal.scan_raw_symbols(tpath / "syn" / "tiers" / "D3_Mapped"), [])

            empty_dir = tpath / "empty_data"
            empty_dir.mkdir()
            proc = subprocess.run(
                [sys.executable, "-B", str(SCRIPTS_DIR / "materialize_decomp_tiers.py"), "--data-dir", str(empty_dir)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(proc.returncode, 2)
            self.assertEqual(json.loads(proc.stdout)["errorCode"], "MISSING_CORPUS_MEDIA")

    def test_materialize_d2_idempotent_preserve(self) -> None:
        with tempfile.TemporaryDirectory(prefix="mdt_idem_") as tmp:
            corpus = Path(tmp)
            d1_src, r_dir, d2_dir = corpus / "standalone/ghidra_export", corpus / "readable", corpus / "tiers/D2_Structured"
            for b in BANKS:
                (d1_src / b).mkdir(parents=True, exist_ok=True)
                (d1_src / b / "functions.json").write_text("[]\n", encoding="utf-8")
            for tree in (r_dir, d2_dir):
                (tree / "include").mkdir(parents=True, exist_ok=True)
                (tree / "src/core").mkdir(parents=True, exist_ok=True)
                (tree / "include/metalgear_globals.h").write_text("#pragma once\n", encoding="utf-8")
                (tree / "include/ghidra_compat.h").write_text("#pragma once\n", encoding="utf-8")
                for i in range(68):
                    (tree / "src/core" / f"core_{i:02d}.c").write_text("/* D2_KEEP_MARKER */\nvoid f(void) {}\n", encoding="utf-8")
            rep = mdt.materialize_tiers(data_dir=corpus, tier="D2_Structured")
            self.assertTrue(rep["tiers"]["D2_Structured"]["preserved"])
            self.assertIn("D2_KEEP_MARKER", (d2_dir / "src/core/core_00.c").read_text(encoding="utf-8"))
            self.assertTrue((d2_dir / "compile_commands.json").is_file())


class TestD4Craftsmanship(unittest.TestCase):
    def test_ast_cleaner_clears_all_six_tell_classes(self) -> None:
        raw = "\n".join([
            "/**\n * Steps one actor frame.\n * @address 0x00008000 (PRG_FIXED_07.prg)\n * @callers none\n */",
            "// Function: mg_fxa_sample_tick @ 0x00008000",
            "/* WARNING: Unknown calling convention */",
            "byte mg_fxa_sample_tick(byte slot) {",
            "  undefined1 bStack0000;",
            "  byte in_A; byte bVar1; sbyte cVar1; byte unaff_retaddr_00;",
            "  bStack0000 = slot;",
            "  cVar1 = (sbyte)in_A;",
            "  if ((bVar1 = (&g_wram_0741)[slot], -1 < (char)cVar1 && bVar1 < 4)) {",
            "    g_zp_ptr0 = CONCAT11(bVar1, unaff_retaddr_00);",
            "    (*((uint8_t *)&(g_zp_ptr0) + 1)) = (byte)(CARRY1(bVar1, 1) | in_A & 3 ^ cVar1 & 7);",
            "    in_A = (byte)(short)(&g_zp_ptr0 + slot);",
            "    in_A = in_A + 1;",
            "    while (true) { if (bVar1) goto joined_r0xe733; halt_baddata(); }",
            "  }",
            "joined_r0xe733:",
            "  return (byte)in_A;",
            "}",
        ])
        cleaned, info = ast_cl.clean_function_block(raw, {"g_zp_ptr0": 0x0080}, {"g_vram_transfer_queue"})
        src = "/* @module: IronFrame.NES.Test */\n" + cleaned + "\n"
        self.assertEqual(cd4h.find_d4_craftsmanship_tells(src), {}, cleaned)
        self.assertEqual(len(cd4h.extract_d4_func_blocks(src)), 1)
        self.assertIn("* @symbol mg_fxa_sample_tick", src)
        self.assertIn("g_vram_transfer_queue[(u8)((slot) + 0x01u)]", src)
        self.assertIn("0x0080u", src)
        self.assertNotIn("bStack0000", src)
        self.assertNotIn("joined_r0x", src)
        self.assertEqual(info["symbol"], "mg_fxa_sample_tick")

    def test_rewrites_shards_cleanroom_and_normalizer_cli(self) -> None:
        rdir = PROJECT_ROOT / "Dev" / "schemas" / "d4_rewrites"
        ok, meta = cd4h.validate_d4_rewrites_dir(rdir)
        self.assertTrue(ok, meta)
        for shard in rdir.glob("*.json"):
            self.assertEqual(edb.validate_cleanroom_bytes(f"Dev/schemas/d4_rewrites/{shard.name}", shard.read_bytes(), strict=True), [], shard.name)
            txt = shard.read_text(encoding="utf-8")
            self.assertNotIn('"cBody"', txt)
            self.assertNotIn('"functionBody"', txt)
        with tempfile.TemporaryDirectory(prefix="norm_cli_") as tmp:
            tpath = Path(tmp)
            self.assertFalse(cd4h.is_clangd_clean(tpath))
            res = subprocess.run([sys.executable, "-B", str(SCRIPTS_DIR / "craftsmanship_d4_normalizer.py"), "--offline-synthetic", "--out-dir", str(tpath / "syn_d4"), "--rewrites-dir", str(tpath / "syn_rew"), "--log-dir", str(tpath / "logs")], capture_output=True, text=True, check=False)
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertEqual(json.loads(res.stdout)["tellCount"], 0)
            self.assertEqual(cd4h.count_d4_craftsmanship_tells(tpath / "syn_d4")[0], 0)
            miss = subprocess.run([sys.executable, "-B", str(SCRIPTS_DIR / "craftsmanship_d4_normalizer.py"), "--data-dir", str(tpath / "empty"), "--log-dir", str(tpath / "logs")], capture_output=True, text=True, check=False)
            self.assertEqual(miss.returncode, 2)
            self.assertEqual(json.loads(miss.stdout)["errorCode"], "MISSING_CORPUS_MEDIA")
        syn_log = PROJECT_ROOT / "Dev" / "logs" / "craftsmanship_d4_normalizer_synthetic.log"
        before_mtime = syn_log.stat().st_mtime_ns if syn_log.is_file() else None
        no_out = subprocess.run([sys.executable, "-B", str(SCRIPTS_DIR / "craftsmanship_d4_normalizer.py"), "--offline-synthetic"], capture_output=True, text=True, check=False)
        self.assertEqual(no_out.returncode, 0, no_out.stderr)
        no_out_data = json.loads(no_out.stdout)
        syn_dir = Path(no_out_data["outDir"]).resolve()
        try:
            self.assertTrue(str(syn_dir).startswith(str(Path(tempfile.gettempdir()).resolve())), syn_dir)
            self.assertEqual(no_out_data["tellCount"], 0)
            self.assertEqual(syn_log.stat().st_mtime_ns if syn_log.is_file() else None, before_mtime)
        finally:
            shutil.rmtree(syn_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
