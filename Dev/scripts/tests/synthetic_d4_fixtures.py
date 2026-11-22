# @module: IronFrame.Dev.scripts.tests.synthetic_d4_fixtures
# @purpose: Synthetic C fixtures isolated under Dev/scripts/tests for offline CLI self-checks
# @depends-on: pathlib
# @exports: write_synthetic_d1_d2, synthetic_d4_raw_block

from __future__ import annotations

from pathlib import Path


def write_synthetic_d1_d2(d1_dir: Path | None, d2_dir: Path | None, banks: tuple[str, ...]) -> None:
    """Populate clean synthetic D1_Raw and D2_Structured trees using generic/test inputs."""
    if d1_dir is not None:
        for bank in banks:
            (d1_dir / bank / "funcs").mkdir(parents=True, exist_ok=True)
            (d1_dir / bank / "functions.json").write_text("[]\n", encoding="utf-8")
            (d1_dir / bank / "funcs" / "syn.c").write_text("void syn_fn(void) {}\n", encoding="utf-8")
    if d2_dir is None:
        return
    (d2_dir / "include").mkdir(parents=True, exist_ok=True)
    (d2_dir / "src" / "core").mkdir(parents=True, exist_ok=True)
    (d2_dir / "overlays" / "BANK_03.prg").mkdir(parents=True, exist_ok=True)
    (d2_dir / "include" / "ghidra_compat.h").write_text("#pragma once\n#include <stdint.h>\ntypedef uint8_t byte;\n", encoding="utf-8")
    (d2_dir / "include" / "metalgear_types.h").write_text('#pragma once\n#include "ghidra_compat.h"\n', encoding="utf-8")
    (d2_dir / "include" / "metalgear_functions.h").write_text(
        '#pragma once\n#include "metalgear_types.h"\nvoid unrom_select_bank_0(void);\nvoid FUN_99a8(byte sound_id);\n',
        encoding="utf-8",
    )
    (d2_dir / "include" / "metalgear_globals.h").write_text('#pragma once\n#include "metalgear_types.h"\n', encoding="utf-8")
    (d2_dir / "src" / "core" / "core_01.c").write_text(
        '/** @address 0x0000c932 */\n// Function: unrom_select_bank_0 @ 0x0000c932\n'
        'void unrom_select_bank_0(void) {\n'
        '  BYTE_ARRAY_ff99[0x37] = 0; DAT_0740 = 1; (&DAT_0740)[1] = DAT_0741; FUN_99a8(1); func_0x8120();\n}\n'
        '/** @address 0x0000d647 */\n// Function: mg_fxb_tick_demo_mode_state @ 0x0000d647\n'
        'void mg_fxb_tick_demo_mode_state(void) {\n'
        'BYTE_ARRAY_8000_6486_: _DAT_00db = 1; bRAM07e1 = uRAM00b9; _g_oam_cycle_flag = 0; register0x22 = 0;\n'
        '  if (FUN_b622[0]) goto BYTE_ARRAY_8000_6486_; FUN_f5ac(1); func_0xc68b(0);\n}\n',
        encoding="utf-8",
    )
    (d2_dir / "overlays" / "BANK_03.prg" / "bank_03_01.c").write_text(
        '/** @address 0x0000be73 */\n// Function: mg_b034_bank03_check_room_radio_triggers @ 0x0000be73\n'
        'void mg_b034_bank03_check_room_radio_triggers(void) { g_ppu_ctrl = BYTE_ARRAY_bf00[0]; }\n',
        encoding="utf-8",
    )


def synthetic_d4_raw_block() -> str:
    """Return a single synthetic raw decompiled block for D4 AST normalizer self-checks."""
    return (
        "/**\n"
        " * Processes a synthetic queue update.\n"
        " * @address 0x00008000 (BANK_00.prg)\n"
        " * @callers none\n"
        " */\n"
        "// Function: synthetic_tick @ 0x00008000\n"
        "byte synthetic_tick(byte slot) {\n"
        "  undefined1 uStack0000;\n"
        "  byte in_A;\n"
        "  byte bVar1 = 0;\n"
        "  uStack0000 = 1;\n"
        "  if ((bVar1 = (&g_wram_0741)[slot], 0 < bVar1)) {\n"
        "    in_A = (byte)(bVar1 | in_A & 3);\n"
        "  }\n"
        "  return in_A;\n"
        "}\n"
    )
