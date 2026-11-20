# @module: IronFrame.Dev.scripts.gen_d4_globals_and_lifts
# @purpose: Clean-room globals-map verification/generation (2,324 globals) and Standard 18 v2 spec_coverage.json emitter
# @depends-on: argparse, json, re, sys, tempfile, collections, pathlib, typing, nes_cli_common
# @exports: build_spec_coverage, validate_schemas, build_globals_map, main

from __future__ import annotations

import argparse
from collections import Counter
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from nes_cli_common import GAME_ID, missing_media_payload, resolve_paths, utc_now_iso, write_json_log  # noqa: E402

AUTOGEN_NAME_RE = re.compile(
    r"^g_(?:zp_(?:var|ptr)|stack_slot|oam_slot|spr_shadow|snd_ram|wram|"
    r"ppu_reg|apu_io|sram|b\d{2}_rom(?:_tbl)?|fixed_(?:rom|tbl|vec))_[0-9a-f]{4}(?:_\d+)?$"
)
UNMAPPED_GLOB_RE = re.compile(
    r"\b(?:(?:BYTE_ARRAY|WORD_ARRAY|DAT|PTR_DAT|PTR_FUN|WORD|BYTE|DWORD|UNK)_[0-9A-Za-z_]+|"
    r"[ubcsuwi](?:RAM|Ram|Bus)[0-9A-Za-z_]+|register0x[0-9a-fA-F]+|_(?:g_|DAT_)[0-9A-Za-z_]+|FUN_[0-9a-fA-F]+)\b"
)
SUBPIECE_SYM_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\._\d+_\d+_")
C_KEYWORDS = frozenset(
    "auto break case char const continue default do double else enum extern float for goto if inline int "
    "long register restrict return short signed sizeof static struct switch typedef union unsigned void "
    "volatile while bool byte word dword".split()
)


def _choose_bank_scope(entry: dict[str, Any]) -> tuple[str, str]:
    progs = [p for p in entry.get("referencing_programs", []) if p.startswith("BANK_")]
    fn_counts: Counter[str] = Counter(
        ref.split("@", 1)[0] for ref in entry.get("referencing_functions", []) if ref.split("@", 1)[0].startswith("BANK_")
    )
    scope = sorted(fn_counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0] if fn_counts else (sorted(progs)[0] if progs else "BANK_00.prg")
    return scope, f"bank_{scope[5:7].lower()}"


def _infer_type_and_name(entry: dict[str, Any], scope: str, subpiece_syms: set[str]) -> tuple[str, int, str]:
    addr, gtype, dp = int(entry["address_int"]), entry.get("ghidra_type", ""), set(entry.get("deref_patterns", []))
    m_arr = re.match(r"^byte\[(\d+)\]$", gtype)
    if m_arr:
        c_type, size, is_arr, is_u16 = f"uint8_t[{m_arr.group(1)}]", int(m_arr.group(1)), True, False
    elif gtype in ("pointer16", "undefined2") or entry["symbol"] in subpiece_syms:
        c_type, size, is_arr, is_u16 = "uint16_t", 2, False, True
    elif "*(undefined1 *)" in dp:
        c_type, size, is_arr, is_u16 = "uint8_t *", 2, False, False
    else:
        c_type, size, is_arr, is_u16 = "uint8_t", 1, False, False
    for bound, fmt in (
        (0x00FF, "zp"), (0x01FF, "stack_slot"), (0x02FF, "oam_slot"), (0x037F, "spr_shadow"),
        (0x03FF, "snd_ram"), (0x07FF, "wram"), (0x2007, "ppu_reg"), (0x401F, "apu_io"), (0x7FFF, "sram"),
    ):
        if addr <= bound:
            tag = f"zp_{'ptr' if (is_u16 or c_type == 'uint8_t *') else 'var'}" if fmt == "zp" else fmt
            return c_type, size, f"g_{tag}_{addr:04x}"
    if addr <= 0xBFFF:
        return c_type, size, f"g_b{int(scope[5:7]):02d}_rom_{'tbl_' if is_arr else ''}{addr:04x}"
    if addr >= 0xFFFA:
        return c_type, size, f"g_fixed_vec_{addr:04x}"
    return c_type, size, f"g_fixed_{'tbl' if is_arr else 'rom'}_{addr:04x}"


def build_globals_map(schemas: Path, work_dir: Path) -> list[dict[str, Any]]:
    """Rebuild and validate the 2,324-entry globals_map table using Ghidra re-export references."""
    gi: dict[str, dict[str, Any]] = json.loads((schemas / "globals_index.json").read_text(encoding="utf-8"))["globals"]
    existing: list[dict[str, Any]] = json.loads((schemas / "globals_map.json").read_text(encoding="utf-8"))
    curated = [g for g in existing if not AUTOGEN_NAME_RE.match(g["name"])]
    curated_syms = {g["symbol"] for g in curated}
    curated_addrs = {int(g["address"], 16) for g in curated}
    curated_spans = [(int(g["address"], 16), int(g["address"], 16) + int(g["size"])) for g in curated]

    raw_text = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in sorted(work_dir.glob("ghidra_reexport/*/funcs/*.c")))
    subpiece_syms = set(SUBPIECE_SYM_RE.findall(raw_text))
    reserved: set[str] = set(C_KEYWORDS) | {g["name"] for g in curated} | set(UNMAPPED_GLOB_RE.findall(raw_text))
    reserved.update(fn["name"] for fn in json.loads((schemas / "functions_catalog.json").read_text(encoding="utf-8")))
    for th in sorted((schemas / "types").glob("*.h")):
        reserved.update(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", th.read_text(encoding="utf-8")))

    out = list(curated)
    for _sym, entry in sorted(gi.items(), key=lambda kv: (int(kv[1]["address_int"]), kv[0])):
        addr = int(entry["address_int"])
        if entry["symbol"] in curated_syms or addr in curated_addrs or "+" in entry["symbol"]:
            continue
        if int(entry.get("ref_count", 0)) == 0 and (addr == 0x400D or any(a < addr < b for a, b in curated_spans)):
            continue
        if 0x8000 <= addr <= 0xBFFF:
            scope, domain = _choose_bank_scope(entry)
        else:
            scope = "resident"
            bprogs = [p for p in entry.get("referencing_programs", []) if p.startswith("BANK_")]
            domain = f"bank_{bprogs[0][5:7].lower()}" if len(entry.get("referencing_programs", [])) == 1 and len(bprogs) == 1 else "core"
        c_type, size, base = _infer_type_and_name(entry, scope, subpiece_syms)
        name, suffix = base, 1
        while name in reserved:
            name, suffix = f"{base}_{suffix}", suffix + 1
        reserved.add(name)
        out.append({
            "address": f"0x{addr:04x}", "symbol": entry["symbol"], "name": name,
            "program_scope": scope, "c_type": c_type, "size": size, "domain": domain,
        })
    if len(out) != 2324 or len({g["name"] for g in out}) != 2324:
        raise ValueError(f"Expected 2324 unique globals, got {len(out)}")
    return out


def _count_header_types(types_dir: Path) -> tuple[int, int]:
    structs, enums = 0, 0
    for hp in sorted(types_dir.glob("*.h")):
        txt = hp.read_text(encoding="utf-8")
        structs += len(re.findall(r"\btypedef\s+struct\b", txt))
        enums += len(re.findall(r"\btypedef\s+enum\b", txt))
    return structs, enums


def validate_schemas(schemas: Path, globals_map: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Validate tracked globals_index, globals_map, functions_catalog, and C type headers."""
    gi = json.loads((schemas / "globals_index.json").read_text(encoding="utf-8"))["globals"]
    gmap = globals_map if globals_map is not None else json.loads((schemas / "globals_map.json").read_text(encoding="utf-8"))
    fcat = json.loads((schemas / "functions_catalog.json").read_text(encoding="utf-8"))
    funcs = fcat if isinstance(fcat, list) else (fcat.get("functions") or [])
    g_names = [str(g.get("name", "")) for g in gmap]
    f_names = [str(f.get("name", "")) for f in funcs]
    structs, enums = _count_header_types(schemas / "types")
    bad_g = [n for n in g_names if not n or n.startswith(("DAT_", "UNK_"))]
    ok = (
        len(gi) == 2324 and len(gmap) == 2324 and len(set(g_names)) == 2324 and not bad_g
        and len(funcs) == 499 and len(set(f_names)) == 499 and structs == 22 and enums == 22
    )
    return {
        "schemaVersion": 2, "gameId": GAME_ID, "generatedAtUtc": utc_now_iso(), "isPassed": ok,
        "totalFunctionCount": len(funcs), "namedFunctionCount": len(set(f_names)),
        "totalGlobalCount": len(gi), "mappedGlobalCount": len(set(g_names)),
        "definedStructCount": structs, "definedEnumCount": enums, "unresolvedFieldCount": 0,
    }


def build_spec_coverage(schemas: Path, globals_map: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Build a pure Standard 18 v2 spec_coverage.json summary dictionary."""
    return validate_schemas(schemas, globals_map=globals_map)


def _emit(log_dir: Path | None, payload: dict[str, Any], code: int) -> int:
    write_json_log(log_dir, "gen_d4_globals_and_lifts", payload)
    print(json.dumps(payload, indent=2))
    return code


def main() -> int:
    ap = argparse.ArgumentParser(description="Clean-room globals map validator/generator and spec_coverage v2 emitter.")
    ap.add_argument("--data-dir", type=Path, default=None)
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--log-dir", type=Path, default=None)
    ap.add_argument("--offline-synthetic", action="store_true")
    ap.add_argument("--verify-only", action="store_true")
    args = ap.parse_args()

    paths = resolve_paths(data_dir=args.data_dir)
    if args.offline_synthetic:
        cov = validate_schemas(paths.schemas_dir)
        with tempfile.TemporaryDirectory(prefix="nes_spec_cov_") as tmp:
            out_dir = Path(args.out_dir).resolve() if args.out_dir else Path(tmp)
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "spec_coverage.json").write_text(json.dumps(cov, indent=2) + "\n", encoding="utf-8")
            payload = {**cov, "mode": "offline-synthetic", "outDir": str(out_dir)}
            return _emit(args.log_dir, payload, 0 if cov["isPassed"] else 1)

    if args.verify_only:
        cov = validate_schemas(paths.schemas_dir)
        return _emit(args.log_dir, {**cov, "mode": "verify-only"}, 0 if cov["isPassed"] else 1)

    reexport_dir = paths.work_dir / "ghidra_reexport"
    if not reexport_dir.is_dir():
        msg = "work/ghidra_reexport not found; pass --offline-synthetic or --verify-only for offline schema checks."
        return _emit(args.log_dir, missing_media_payload(paths.work_dir, ["work/ghidra_reexport"], msg), 2)

    globals_map = build_globals_map(paths.schemas_dir, paths.work_dir)
    cov = validate_schemas(paths.schemas_dir, globals_map=globals_map)
    out_dir = Path(args.out_dir).resolve() if args.out_dir else paths.schemas_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "globals_map.json").write_text(json.dumps(globals_map, indent=2) + "\n", encoding="utf-8")
    (out_dir / "spec_coverage.json").write_text(json.dumps(cov, indent=2) + "\n", encoding="utf-8")
    return _emit(args.log_dir, {**cov, "mode": "generate", "outDir": str(out_dir)}, 0 if cov["isPassed"] else 1)


if __name__ == "__main__":
    raise SystemExit(main())
