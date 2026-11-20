# @module: IronFrame.Dev.scripts.build_and_verify_d5
# @purpose: Clean-room 6502 .asm generator, 8-bank assembler driver, and byte-exact PRG/NES verifier
# @depends-on: argparse, hashlib, json, re, sys, tempfile, pathlib, typing, asm6502_d5, nes_cli_common, nes_unrom_unpack
# @exports: build_and_verify, main

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from asm6502_d5 import OPCODES, assemble_file  # noqa: E402
from nes_cli_common import (  # noqa: E402
    GAME_ID, crc32_hex, iter_integrity_entries, missing_media_payload, resolve_paths, sha256_bytes, utc_now_iso, write_json_log,
)
from nes_unrom_unpack import INES2_HEADER, build_synthetic_unrom_rom, load_required_rom_spec, unpack_unrom_bytes  # noqa: E402

BANK_SIZE = 16384
EXPECTED_ROM_MD5 = "0e514c68eb8d82342a71a74c6d52499b"
EXPECTED_ROM_SHA1 = "9f7448fddaedc1801e2970e50722ac3cfacd19b8"

_S_LINE_RE = re.compile(r"^\$([0-9A-Fa-f]{4}):\s+(?:[0-9A-Fa-f]{2}\s+)+(.+)$")
_ADDR_OP_RE = re.compile(r"(?<!#)\$([0-9A-Fa-f]{2,4})\b")
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_BRANCH_OPS = frozenset({"BCC", "BCS", "BEQ", "BMI", "BNE", "BPL", "BVC", "BVS"})


def _valid_sym(name: str, used: set[str]) -> bool:
    return bool(_IDENT_RE.fullmatch(name) and name.upper() not in OPCODES and name.upper() not in {"A", "X", "Y"} and name not in used)


def _load_symbol_tables(schemas_dir: Path) -> tuple[dict[str, dict[int, str]], dict[str, dict[int, str]]]:
    funcs_by_prog: dict[str, dict[int, str]] = {}
    fcat_path = schemas_dir / "functions_catalog.json"
    if fcat_path.is_file():
        cat_raw = json.loads(fcat_path.read_text(encoding="utf-8"))
        entries = cat_raw if isinstance(cat_raw, list) else (cat_raw.get("functions") or [])
        for row in entries:
            prog, name = str(row.get("program", "")), str(row.get("name", ""))
            if prog and name:
                funcs_by_prog.setdefault(prog, {})[int(str(row["address"]), 16)] = name
    globals_by_scope: dict[str, dict[int, str]] = {}
    gmap_path = schemas_dir / "globals_map.json"
    if gmap_path.is_file():
        g_raw = json.loads(gmap_path.read_text(encoding="utf-8"))
        g_list = g_raw if isinstance(g_raw, list) else (g_raw.get("globals") or [])
        for row in g_list:
            name = str(row.get("name", ""))
            if name:
                globals_by_scope.setdefault(str(row.get("program_scope", "resident")), {})[int(str(row["address"]), 16)] = name
    return funcs_by_prog, globals_by_scope


def _parse_s_statements(s_path: Path) -> list[tuple[int, str, str]]:
    """Extract ONLY (address, mnemonic_or_directive, operand) from .s without reading raw machine bytes."""
    rows: list[tuple[int, str, str]] = []
    for raw in s_path.read_text(encoding="utf-8").splitlines():
        if m := _S_LINE_RE.match(raw):
            stmt = m.group(2).split(";", 1)[0].strip()
            parts = stmt.split(None, 1)
            rows.append((int(m.group(1), 16), parts[0], parts[1].strip() if len(parts) > 1 else ""))
    return rows


def _generate_clean_asm(
    s_path: Path, asm_path: Path, prog_name: str, win_lo: int, win_hi: int,
    funcs_by_prog: dict[str, dict[int, str]], globals_by_scope: dict[str, dict[int, str]], vectors: dict[str, str] | None = None,
) -> None:
    rows = _parse_s_statements(s_path)
    starts = {addr for addr, _op, _arg in rows}
    prog_funcs, fixed_funcs = funcs_by_prog.get(prog_name, {}), funcs_by_prog.get("PRG_FIXED_07.prg", {})
    res_globs, prog_globs = globals_by_scope.get("resident", {}), globals_by_scope.get(prog_name, {})
    used_names: set[str] = set()
    labels: dict[int, str] = {}
    for addr in sorted(starts):
        cand = prog_funcs.get(addr) or prog_globs.get(addr) or (res_globs.get(addr) if addr >= 0xC000 else None)
        if cand and _valid_sym(cand, used_names):
            labels[addr] = cand
            used_names.add(cand)
    ext_consts: dict[int, str] = {}
    for scope_map in (prog_globs, res_globs, fixed_funcs if prog_name != "PRG_FIXED_07.prg" else {}):
        for addr, cand in sorted(scope_map.items()):
            if addr not in labels and not (win_lo <= addr < win_hi and addr in starts) and addr not in ext_consts and _valid_sym(cand, used_names):
                ext_consts[addr] = cand
                used_names.add(cand)

    def ensure_label(target: int) -> None:
        if target not in labels and win_lo <= target < win_hi and target in starts:
            nm = f"loc_{target:04x}"
            while nm in used_names:
                nm += "_"
            labels[target] = nm
            used_names.add(nm)

    for _addr, op, arg in rows:
        if op != ".byte" and arg:
            for m in _ADDR_OP_RE.finditer(arg):
                tgt = int(m.group(1), 16)
                if win_lo <= tgt < win_hi:
                    if tgt in starts:
                        ensure_label(tgt)
                    elif (tgt - 1) in starts and op.upper() in _BRANCH_OPS:
                        ensure_label(tgt - 1)
    vec_addrs = [int(str(vectors[k]), 16) for k in ("nmi", "reset", "irq")] if vectors else []
    for v in vec_addrs:
        ensure_label(v)

    used_consts: dict[str, int] = {}

    def rewrite_arg(op: str, arg: str) -> str:
        if op == ".byte" or not arg:
            return arg

        def repl(m: re.Match[str]) -> str:
            tok = m.group(1)
            val = int(tok, 16)
            if win_lo <= val < win_hi:
                if val in labels:
                    return labels[val]
                if (val - 1) in labels and op.upper() in _BRANCH_OPS:
                    return f"{labels[val - 1]} + 1"
                return m.group(0)
            if prog_name == "PRG_FIXED_07.prg" and 0x8000 <= val < 0xC000:
                return m.group(0)
            if val in ext_consts:
                sym = ext_consts[val]
                used_consts[sym] = val
                return f"a:{sym}" if (len(tok) == 4 and val < 0x100) else sym
            return m.group(0)

        return _ADDR_OP_RE.sub(repl, arg)

    body_lines: list[str] = []
    byte_run: list[str] = []

    def flush_bytes() -> None:
        if byte_run:
            body_lines.append(f"    .byte {', '.join(byte_run)}")
            byte_run.clear()

    for addr, op, arg in rows:
        if addr in labels:
            flush_bytes()
            body_lines.append(f"{labels[addr]}:")
        if op == ".byte":
            byte_run.append(arg)
            if len(byte_run) >= 16:
                flush_bytes()
        else:
            flush_bytes()
            body_lines.append(f"    {op.upper()} {rewrite_arg(op, arg)}".rstrip())
    flush_bytes()
    if vec_addrs:
        body_lines.extend(["", "    .org $FFFA", f"    .word {', '.join(labels.get(v, f'${v:04X}') for v in vec_addrs)}"])
    header = [f"; Clean-room 6502 assembly for {prog_name} [${win_lo:04X}, ${win_hi:04X})", ""]
    header.extend(f"{sym} = {'$' + f'{val:02X}' if val < 0x100 else '$' + f'{val:04X}'}" for sym, val in sorted(used_consts.items(), key=lambda kv: (kv[1], kv[0])))
    if used_consts:
        header.append("")
    header.append(f"    .org ${win_lo:04X}")
    asm_path.parent.mkdir(parents=True, exist_ok=True)
    asm_path.write_text("\n".join(header + body_lines) + "\n", encoding="utf-8")


def _diff_count(a: bytes, b: bytes) -> int:
    return abs(len(a) - len(b)) + sum(1 for x, y in zip(a, b) if x != y)


def _assemble_and_verify(
    ext_src: Path, schemas_dir: Path, work_out: Path, exp_prg_shas: dict[str, str], exp_rom: dict[str, Any],
) -> dict[str, Any]:
    bank_layout = json.loads((ext_src / "nes_bank_layout.json").read_text(encoding="utf-8"))
    funcs_by_prog, globals_by_scope = _load_symbol_tables(schemas_dir)
    asm_dir, build_dir = work_out / "asm_d5", work_out / "build" / "d5"
    build_ext = build_dir / "extracted"
    build_ext.mkdir(parents=True, exist_ok=True)

    specs = [(f"BANK_{b:02d}.prg", f"BANK_{b:02d}.s", f"BANK_{b:02d}.asm", 0x8000, 0xC000, None) for b in range(7)]
    specs.append(("PRG_FIXED_07.prg", "PRG_FIXED_07.s", "PRG_FIXED_07.asm", 0xC000, 0xFFFA, bank_layout["vectors"]))
    banks_16k: dict[str, bytes] = {}
    for prog, s_name, asm_name, lo, hi, vecs in specs:
        asm_path = asm_dir / asm_name
        _generate_clean_asm(ext_src / s_name, asm_path, prog, lo, hi, funcs_by_prog, globals_by_scope, vecs)
        raw, origin, _ = assemble_file(asm_path)
        if len(raw) != BANK_SIZE or origin != lo:
            raise RuntimeError(f"{asm_name} assembled to {len(raw)} bytes @ ${origin:04X}, expected {BANK_SIZE}")
        banks_16k[prog] = raw

    fixed = banks_16k["PRG_FIXED_07.prg"]
    prg_outputs = {f"BANK_{b:02d}.prg": banks_16k[f"BANK_{b:02d}.prg"] + fixed for b in range(7)}
    prg_outputs["PRG_FIXED_07.prg"] = banks_16k["BANK_00.prg"] + fixed

    binaries, matched_bins, total_diff = [], 0, 0
    for prog in sorted(prg_outputs):
        built = prg_outputs[prog]
        (build_ext / prog).write_bytes(built)
        rel = f"extracted/{prog}"
        sha = sha256_bytes(built)
        diff = _diff_count(built, (ext_src / prog).read_bytes())
        total_diff += diff
        if diff == 0 and sha == exp_prg_shas.get(rel, ""):
            matched_bins += 1
        binaries.append({"relativePath": rel, "fileSizeBytes": len(built), "sha256Hex": sha, "mismatchedBytes": diff})

    rom_bytes = INES2_HEADER + b"".join(banks_16k[f"BANK_{b:02d}.prg"] for b in range(7)) + fixed
    (build_dir / "IronFrame_D5.nes").write_bytes(rom_bytes)
    crc, md5, sha1, sha256 = crc32_hex(rom_bytes), hashlib.md5(rom_bytes).hexdigest().lower(), hashlib.sha1(rom_bytes).hexdigest().lower(), sha256_bytes(rom_bytes)
    rom_ok = (
        len(rom_bytes) == exp_rom["size"] and crc == exp_rom["crc32"]
        and md5 == exp_rom["md5"] and sha1 == exp_rom["sha1"] and sha256 == exp_rom["sha256"]
    )
    ok = matched_bins == 8 and total_diff == 0 and rom_ok
    return {
        "schemaVersion": 2, "gameId": GAME_ID, "generatedAtUtc": utc_now_iso(), "isPassed": ok, "isVerified": ok,
        "matchedBinaryCount": matched_bins, "mismatchedBytes": total_diff, "fileSizeBytes": len(rom_bytes),
        "crc32Hex": crc, "md5Hex": md5, "sha1Hex": sha1, "sha256Hex": sha256, "binaries": binaries,
    }


def build_and_verify(data_dir: Path | None = None, out_dir: Path | None = None, offline_synthetic: bool = False, write_report: bool = False) -> tuple[dict[str, Any], int]:
    """Run clean-room 6502 D5 assembly and byte-exact verification in normal or synthetic mode."""
    paths = resolve_paths(data_dir=data_dir)
    if offline_synthetic:
        with tempfile.TemporaryDirectory(prefix="nes_d5_synth_") as tmp:
            troot = Path(tmp)
            work_out = Path(out_dir).resolve() if out_dir else (troot / "work")
            synth_rom = build_synthetic_unrom_rom(troot / "synthetic.nes")
            ext_src = troot / "extracted"
            unpack_unrom_bytes(synth_rom, "synthetic.nes", ext_src, write_files=True)
            exp_prgs = {f"extracted/{p.name}": sha256_bytes(p.read_bytes()) for p in ext_src.glob("*.prg")}
            exp_rom = {
                "size": len(synth_rom), "crc32": crc32_hex(synth_rom), "sha256": sha256_bytes(synth_rom),
                "md5": hashlib.md5(synth_rom).hexdigest().lower(), "sha1": hashlib.sha1(synth_rom).hexdigest().lower(),
            }
            rep = _assemble_and_verify(ext_src, paths.schemas_dir, work_out, exp_prgs, exp_rom)
            if write_report:
                (paths.schemas_dir / "d5_byte_match.json").write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")
            return rep, (0 if rep["isPassed"] else 1)

    ext_src = paths.standalone_dir / "extracted"
    if not ext_src.is_dir() or not (ext_src / "nes_bank_layout.json").is_file():
        return missing_media_payload(paths.standalone_dir, ["standalone/extracted/nes_bank_layout.json"], "Standalone extracted UNROM banks missing."), 2

    integ = json.loads((paths.schemas_dir / "standalone_integrity.json").read_text(encoding="utf-8"))
    exp_prgs = {rel: sha for rel, _sz, sha, _crc in iter_integrity_entries(integ) if rel.endswith(".prg")}
    rom_sz, rom_sha, rom_crc = load_required_rom_spec(paths.schemas_dir)
    exp_rom = {"size": rom_sz, "crc32": rom_crc, "md5": EXPECTED_ROM_MD5, "sha1": EXPECTED_ROM_SHA1, "sha256": rom_sha}
    work_out = Path(out_dir).resolve() if out_dir else paths.work_dir
    rep = _assemble_and_verify(ext_src, paths.schemas_dir, work_out, exp_prgs, exp_rom)
    if out_dir is None or write_report:
        (paths.schemas_dir / "d5_byte_match.json").write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")
    if out_dir is not None:
        (work_out / "d5_byte_match.json").write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")
    return rep, (0 if rep["isPassed"] else 1)


def main() -> int:
    ap = argparse.ArgumentParser(description="Clean-room 6502 D5 build and byte-exact verification.")
    ap.add_argument("--data-dir", type=Path, default=None)
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--log-dir", type=Path, default=None)
    ap.add_argument("--offline-synthetic", action="store_true")
    ap.add_argument("--write-report", action="store_true")
    args = ap.parse_args()
    rep, code = build_and_verify(args.data_dir, args.out_dir, args.offline_synthetic, args.write_report)
    write_json_log(args.log_dir, "build_and_verify_d5", rep)
    print(json.dumps(rep, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
