# @module: IronFrame.Dev.scripts.materialize_decomp_tiers
# @purpose: Materialize Corpus/tiers/{D1_Raw,D2_Structured,D3_Mapped} and sync cohesive Corpus/readable/
# @depends-on: argparse, importlib, json, os, re, shutil, stat, sys, tempfile, time, pathlib, typing, nes_cli_common, coalesce_d4_modules
# @exports: TIER_NAMES, materialize_tiers, main

from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile
import time
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import coalesce_d4_modules as coal  # noqa: E402
import nes_cli_common as ncc  # noqa: E402

TIER_NAMES = ("D1_Raw", "D2_Structured", "D3_Mapped")
_EXPECTED_BANKS = ("BANK_00.prg", "BANK_01.prg", "BANK_02.prg", "BANK_03.prg", "BANK_04.prg", "BANK_05.prg", "BANK_06.prg", "PRG_FIXED_07.prg")
_FRAGMENT_RE = re.compile(r"_\d{2}\.c$")


def _heartbeat(last_ts: float, msg: str, force: bool = False) -> float:
    now = time.monotonic()
    if force or (now - last_ts) >= 12.0:
        sys.stderr.write(f"\r\x1b[K[materialize_decomp_tiers] {msg}")
        sys.stderr.flush()
        return now
    return last_ts


def _rmtree_force(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, onexc=lambda fn, p, _: (os.chmod(p, stat.S_IWRITE | stat.S_IREAD), fn(p)))


def _clear_readonly_tree(root: Path) -> int:
    cnt = 0
    for fp in root.rglob("*"):
        if fp.is_file():
            os.chmod(fp, stat.S_IWRITE | stat.S_IREAD)
            cnt += 1
    return cnt


def _rewrite_tree_paths(tree_dir: Path) -> None:
    inc, compat = (tree_dir / "include").as_posix(), (tree_dir / "include" / "ghidra_compat.h").as_posix()
    if (cl_p := tree_dir / ".clangd").is_file():
        txt = re.sub(r"(?m)^(\s*- -I).*$", rf"\1{inc}", cl_p.read_text(encoding="utf-8", errors="replace"))
        cl_p.write_text(re.sub(r"(?m)^(\s*- ).*/include/ghidra_compat\.h$", rf"\1{compat}", txt), encoding="utf-8", newline="\n")
    args = ["clang", "-target", "msp430-unknown-none-elf", "-ffreestanding", "-std=gnu11", f"-I{inc}", "-include", compat, "-c"]
    cdb = [{"directory": tree_dir.as_posix(), "file": p.as_posix(), "arguments": [*args, p.as_posix()]} for p in sorted(tree_dir.rglob("*.c"))]
    (tree_dir / "compile_commands.json").write_text(json.dumps(cdb, indent=2) + "\n", encoding="utf-8", newline="\n")


def _materialize_d1_raw(paths: ncc.TrackPaths, dst: Path) -> dict[str, Any]:
    src = paths.standalone_dir / "ghidra_export"
    if not src.is_dir() or not all((src / b / "functions.json").is_file() for b in _EXPECTED_BANKS):
        raise FileNotFoundError(str(src))
    ts = _heartbeat(0.0, "Materializing D1_Raw from standalone/ghidra_export...", force=True)
    _rmtree_force(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst)
    files = _clear_readonly_tree(dst)
    _heartbeat(ts, f"D1_Raw complete (8 binaries, {files} files)\n", force=True)
    return {"path": str(dst), "binaryCount": 8, "fileCount": files}


def _materialize_d2_structured(paths: ncc.TrackPaths, dst: Path, tools_dir: Path | None) -> dict[str, Any]:
    if dst.is_dir() and sum(1 for _ in dst.rglob("*.c")) == 68 and (dst / "include" / "metalgear_globals.h").is_file():
        _rewrite_tree_paths(dst)
        return {"path": str(dst), "cFileCount": 68, "preserved": True}
    ts = _heartbeat(0.0, "Materializing D2_Structured...", force=True)
    if paths.readable_dir.is_dir() and sum(1 for _ in paths.readable_dir.rglob("*.c")) == 68:
        _rmtree_force(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(paths.readable_dir, dst, ignore=shutil.ignore_patterns(".cache", "__pycache__"))
        _clear_readonly_tree(dst)
        _rewrite_tree_paths(dst)
        _heartbeat(ts, "D2_Structured captured 68 slices from readable/\n", force=True)
        return {"path": str(dst), "cFileCount": 68, "preserved": False}
    reexp = paths.work_dir / "ghidra_reexport"
    rd_tools = ncc.resolve_optional_rd_tools(tools_dir, paths.project_root)
    if not reexp.is_dir() or not any(reexp.glob("*/functions.json")) or rd_tools is None:
        raise FileNotFoundError(str(paths.readable_dir))
    if str(rd_tools) not in sys.path:
        sys.path.insert(0, str(rd_tools))
    s4 = importlib.import_module("decomp.stage4_assembler")
    with tempfile.TemporaryDirectory(prefix="d2_stage4_") as tmp:
        stage = Path(tmp) / "track"
        (stage / "Dev").mkdir(parents=True)
        shutil.copy2(paths.manifest_path, stage / "Dev" / "research.manifest.json")
        shutil.copytree(paths.schemas_dir, stage / "Dev" / "schemas")
        s4.run_stage4_assemble(stage, export_dir=reexp)
        _rmtree_force(dst)
        shutil.copytree(stage / "Corpus" / "readable", dst)
        _rewrite_tree_paths(dst)
    c_cnt = sum(1 for _ in dst.rglob("*.c"))
    _heartbeat(ts, f"D2_Structured assembled ({c_cnt} .c slices)\n", force=True)
    return {"path": str(dst), "cFileCount": c_cnt}


def _materialize_d3_mapped(paths: ncc.TrackPaths, d2_dir: Path, d3_dir: Path) -> dict[str, Any]:
    if not d2_dir.is_dir() or not any(d2_dir.rglob("*.c")):
        raise FileNotFoundError(str(d2_dir))
    ts = _heartbeat(0.0, "Coalescing D2_Structured -> D3_Mapped (26 cohesive modules)...", force=True)
    res = coal.coalesce_tier_dir(d2_dir, d3_dir, paths.schemas_dir)
    c_files = sorted(d3_dir.rglob("*.c"))
    frags = [p.name for p in c_files if _FRAGMENT_RE.search(p.name)]
    if len(c_files) != 26 or frags or coal.scan_raw_symbols(d3_dir):
        raise ValueError(f"D3 validation failed: c={len(c_files)}, frags={frags}")
    _rmtree_force(paths.readable_dir)
    shutil.copytree(d3_dir, paths.readable_dir, ignore=shutil.ignore_patterns(".cache", "__pycache__"))
    _rewrite_tree_paths(paths.readable_dir)
    _heartbeat(ts, f"D3_Mapped complete ({len(c_files)} cohesive modules, 0 raw tokens)\n", force=True)
    return {"path": str(d3_dir), "cFileCount": len(c_files), "functionCount": res["functionCount"], "readableSynced": True}


def _materialize_synthetic(paths: ncc.TrackPaths, selected: list[str]) -> dict[str, Any]:
    tiers_root, out = paths.corpus_root / "tiers", {}
    if "D1_Raw" in selected:
        d1 = tiers_root / "D1_Raw"
        _rmtree_force(d1)
        for b in _EXPECTED_BANKS:
            (d1 / b / "funcs").mkdir(parents=True, exist_ok=True)
            (d1 / b / "functions.json").write_text("[]\n", encoding="utf-8")
            (d1 / b / "funcs" / "syn.c").write_text("void syn_fn(void) {}\n", encoding="utf-8")
        out["D1_Raw"] = {"path": str(d1), "binaryCount": 8, "synthetic": True}
    d2 = tiers_root / "D2_Structured"
    if any(t in selected for t in ("D2_Structured", "D3_Mapped")):
        _rmtree_force(d2)
        (d2 / "include").mkdir(parents=True)
        (d2 / "src" / "core").mkdir(parents=True)
        (d2 / "overlays" / "BANK_03.prg").mkdir(parents=True)
        (d2 / "include" / "ghidra_compat.h").write_text("#pragma once\n#include <stdint.h>\ntypedef uint8_t byte;\n", encoding="utf-8")
        (d2 / "include" / "metalgear_types.h").write_text('#pragma once\n#include "ghidra_compat.h"\n', encoding="utf-8")
        (d2 / "include" / "metalgear_functions.h").write_text('#pragma once\n#include "metalgear_types.h"\nvoid unrom_select_bank_0(void);\nvoid FUN_99a8(byte sound_id);\n', encoding="utf-8")
        (d2 / "include" / "metalgear_globals.h").write_text('#pragma once\n#include "metalgear_types.h"\n', encoding="utf-8")
        (d2 / "src" / "core" / "core_01.c").write_text(
            '/** @address 0x0000c932 */\n// Function: unrom_select_bank_0 @ 0x0000c932\nvoid unrom_select_bank_0(void) {\n'
            '  BYTE_ARRAY_ff99[0x37] = 0; DAT_0740 = 1; (&DAT_0740)[1] = DAT_0741; FUN_99a8(1); func_0x8120();\n}\n'
            '/** @address 0x0000d647 */\n// Function: mg_fxb_tick_demo_mode_state @ 0x0000d647\nvoid mg_fxb_tick_demo_mode_state(void) {\n'
            'BYTE_ARRAY_8000_6486_: _DAT_00db = 1; bRAM07e1 = uRAM00b9; _g_oam_cycle_flag = 0; register0x22 = 0;\n'
            '  if (FUN_b622[0]) goto BYTE_ARRAY_8000_6486_; FUN_f5ac(1); func_0xc68b(0);\n}\n', encoding="utf-8",
        )
        (d2 / "overlays" / "BANK_03.prg" / "bank_03_01.c").write_text(
            '/** @address 0x0000be73 */\n// Function: mg_b034_bank03_check_room_radio_triggers @ 0x0000be73\n'
            'void mg_b034_bank03_check_room_radio_triggers(void) { g_ppu_ctrl = BYTE_ARRAY_bf00[0]; }\n', encoding="utf-8",
        )
        out["D2_Structured"] = {"path": str(d2), "cFileCount": 2, "synthetic": True}
    if "D3_Mapped" in selected:
        d3 = tiers_root / "D3_Mapped"
        res = coal.coalesce_tier_dir(d2, d3, paths.schemas_dir)
        out["D3_Mapped"] = {"path": str(d3), "cFileCount": res["moduleCount"], "functionCount": res["functionCount"], "synthetic": True}
    return out


def materialize_tiers(
    data_dir: Path | None = None, tools_dir: Path | None = None, tier: str = "all",
    offline_synthetic: bool = False, log_dir: Path | None = None,
) -> dict[str, Any]:
    """Populate Corpus/tiers/{D1_Raw,D2_Structured,D3_Mapped} and sync cohesive Corpus/readable/."""
    base_data = data_dir.resolve() if data_dir is not None else (Path(tempfile.mkdtemp(prefix="mgnes_tiers_syn_")) if offline_synthetic else None)
    paths = ncc.resolve_paths(data_dir=base_data)
    selected = list(TIER_NAMES) if tier == "all" else [tier]
    tiers_root = paths.corpus_root / "tiers"
    if offline_synthetic:
        tiers = _materialize_synthetic(paths, selected)
        rep = {"schemaVersion": 2, "gameId": ncc.GAME_ID, "isPassed": True, "mode": "offline-synthetic", "dataDir": str(paths.corpus_root), "tiers": tiers, "generatedAtUtc": ncc.utc_now_iso()}
        ncc.write_json_log(log_dir, "materialize_decomp_tiers", rep)
        return rep
    out: dict[str, Any] = {}
    if "D1_Raw" in selected:
        out["D1_Raw"] = _materialize_d1_raw(paths, tiers_root / "D1_Raw")
    if "D2_Structured" in selected or "D3_Mapped" in selected:
        out["D2_Structured"] = _materialize_d2_structured(paths, tiers_root / "D2_Structured", tools_dir)
    if "D3_Mapped" in selected:
        out["D3_Mapped"] = _materialize_d3_mapped(paths, tiers_root / "D2_Structured", tiers_root / "D3_Mapped")
    rep = {"schemaVersion": 2, "gameId": ncc.GAME_ID, "isPassed": True, "mode": "live", "dataDir": str(paths.corpus_root), "tiers": out, "generatedAtUtc": ncc.utc_now_iso()}
    ncc.write_json_log(log_dir, "materialize_decomp_tiers", rep)
    return rep


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Materialize D1_Raw..D3_Mapped tier snapshots and sync Corpus/readable/.")
    ap.add_argument("--data-dir", type=Path, default=None); ap.add_argument("--tools-dir", type=Path, default=None)
    ap.add_argument("--log-dir", type=Path, default=None); ap.add_argument("--tier", choices=["all", *TIER_NAMES], default="all")
    ap.add_argument("--offline-synthetic", action="store_true")
    args = ap.parse_args(argv)
    try:
        print(json.dumps(materialize_tiers(args.data_dir, args.tools_dir, args.tier, args.offline_synthetic, args.log_dir), indent=2))
        return 0
    except FileNotFoundError as exc:
        paths = ncc.resolve_paths(data_dir=args.data_dir)
        payload = ncc.missing_media_payload(paths.corpus_root, [str(exc)], "Required Corpus standalone/readable tree missing.")
        ncc.write_json_log(args.log_dir, "materialize_decomp_tiers", payload)
        print(json.dumps(payload, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
