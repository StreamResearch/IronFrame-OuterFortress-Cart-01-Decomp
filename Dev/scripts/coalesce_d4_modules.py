# @module: IronFrame.Dev.scripts.coalesce_d4_modules
# @purpose: Coalesce 68 line-split C slices into 26 cohesive domain modules and resolve all D3 raw symbols
# @depends-on: argparse, json, os, re, shutil, stat, sys, tempfile, pathlib, typing, nes_cli_common
# @exports: RAW_SYMBOL_RE, scan_raw_symbols, load_d3_schemas, build_symbol_rewriter, rewrite_c_text, rewrite_headers, extract_func_blocks, coalesce_tier_dir, main

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import nes_cli_common as ncc  # noqa: E402

RAW_SYMBOL_RE = re.compile(
    r"\b(?:(?:BYTE_ARRAY|WORD_ARRAY|DAT|PTR_DAT|PTR_FUN|WORD|BYTE|DWORD|UNK)_[0-9A-Za-z_]+"
    r"|[ubcsuwi](?:RAM|Ram|Bus)[0-9A-Za-z_]+|register0x[0-9a-fA-F]+"
    r"|_(?:g_|DAT_)[0-9A-Za-z_]+|FUN_[0-9a-fA-F]+|func_0x[0-9a-fA-F]+)\b"
)
_FUNC_HDR_RE = re.compile(r"^// Function:\s+(\S+)\s+@\s+0x([0-9a-fA-F]+)", re.M)
_ADDR_HEX_RE = re.compile(r"([0-9a-fA-F]{4})")


def _format_c_decl(c_type: str, name: str) -> str:
    dims = "".join(re.findall(r"\[[^\]]+\]", c_type))
    base = re.sub(r"\[[^\]]+\]", "", c_type).strip()
    return f"extern {base}{name}{dims};" if base.endswith("*") else f"extern {base} {name}{dims};"


def _format_proto(spec: dict[str, Any]) -> str:
    params = spec.get("params") or []
    p_str = ", ".join(f"{p['type']} {p['name']}" for p in params) if params else "void"
    return f"{spec['returnType']} {spec['name']}({p_str})"


def scan_raw_symbols(tree_dir: Path) -> list[str]:
    """Return sorted unique raw Ghidra/unmapped symbols remaining across .c and include/*.h."""
    found: set[str] = set()
    roots = [*Path(tree_dir).rglob("*.c")]
    inc_dir = Path(tree_dir) / "include"
    if inc_dir.is_dir():
        roots.extend(p for p in inc_dir.glob("*.h") if p.name.endswith(("_globals.h", "_functions.h")))
    for fp in sorted(roots):
        found.update(RAW_SYMBOL_RE.findall(fp.read_text(encoding="utf-8", errors="replace")))
    return sorted(found)


def load_d3_schemas(schemas_dir: Path) -> dict[str, Any]:
    """Load D3 module map, symbol overrides, globals map, and function catalog JSONs."""
    sc = Path(schemas_dir)
    load = lambda fn: json.loads((sc / fn).read_text(encoding="utf-8"))
    return {
        "moduleMap": load("d3_module_map.json"),
        "overrides": load("d3_symbol_overrides.json"),
        "globalsMap": load("globals_map.json"),
        "functionsCatalog": load("functions_catalog.json"),
    }


def build_symbol_rewriter(schemas: dict[str, Any]) -> dict[str, Any]:
    """Build deterministic type-aware lookup tables for all D3 raw symbol rewrites."""
    ov = schemas["overrides"]
    gmap: list[dict[str, Any]] = schemas["globalsMap"]
    g_by_sym = {g["symbol"]: g for g in gmap}
    g_by_addr: dict[int, dict[str, Any]] = {}
    for g in gmap:
        g_by_addr.setdefault(int(g["address"], 16), g)
    synth = {e["rawSymbol"]: e for e in ov.get("syntheticGlobals") or []}
    return {
        "localRenames": dict(ov.get("localRenames") or {}),
        "funcCalls": dict(ov.get("functionCallOverrides") or {}),
        "synth": synth,
        "gBySym": g_by_sym,
        "gByAddr": g_by_addr,
    }


def _resolve_global(raw: str, rew: dict[str, Any]) -> tuple[str, bool] | None:
    if raw in rew["synth"]:
        ent = rew["synth"][raw]
        return ent["mappedName"], "[" in ent["cType"]
    if raw in rew["gBySym"]:
        ent = rew["gBySym"][raw]
        return ent["name"], "[" in ent["c_type"]
    if m := _ADDR_HEX_RE.search(raw):
        if ent := rew["gByAddr"].get(int(m.group(1), 16)):
            return ent["name"], "[" in ent["c_type"]
    return None


def rewrite_c_text(text: str, rew: dict[str, Any]) -> str:
    """Rewrite all raw local labels, function calls, and scalar/array globals in C source."""
    out = text
    for raw, dst in rew["localRenames"].items():
        out = re.sub(rf"\b{re.escape(raw)}\b", dst, out)
    # Apply array-typed overrides before function calls when a raw FUN_* symbol is used as a data table.
    arr_funcs = {k for k, v in rew["synth"].items() if "[" in v["cType"] and k in rew["funcCalls"]}
    for raw, dst in rew["funcCalls"].items():
        if raw not in arr_funcs:
            out = re.sub(rf"\b{re.escape(raw)}\b", dst, out)
    raw_tokens = sorted(set(RAW_SYMBOL_RE.findall(out)), key=len, reverse=True)
    for raw in raw_tokens:
        if (resolved := _resolve_global(raw, rew)) is None:
            continue
        mapped, is_arr = resolved
        esc = re.escape(raw)
        if is_arr:
            out = re.sub(rf"\(\s*&\s*{esc}\s*\)\s*\[", f"{mapped}[", out)
            out = re.sub(rf"(^|[(\[{{,;?:=+\-*/%<>!&|^~]\s*|\breturn\s+)&\s*\b{esc}\b(?!\s*\[)", rf"\g<1>{mapped}", out)
            out = re.sub(rf"\b{esc}\b(?=\s*\[)", mapped, out)
            out = re.sub(rf"\b{esc}\b", f"{mapped}[0]" if raw.startswith("DAT_") else mapped, out)
        else:
            out = re.sub(rf"\b{esc}\b", mapped, out)
    return out


def _synth_trampoline_block(spec: dict[str, Any]) -> str:
    hdr = (
        f"/**\n * Clean-room D3 bank/signature adapter for {spec['addressHex']}.\n"
        f" * @address {spec['addressHex']} (PRG_FIXED_07.prg)\n * @domain core\n */\n"
        f"// Function: {spec['name']} @ {spec['addressHex']} (size=0x0, sdk=false)\n\n{_format_proto(spec)}\n{{"
    )
    body = [f"  {spec['selectBankCall']}();"] if spec.get("selectBankCall") else []
    call = f"{spec['targetCall']}({', '.join(spec.get('targetArgs') or [])})"
    restore = [f"  {spec['restoreBankCall']}();"] if spec.get("restoreBankCall") else []
    if spec.get("returnsTargetResult"):
        body += [f"  {spec['returnType']} result = {call};", *restore, "  return result;"]
    else:
        body += [f"  {call};", *restore, *([f"  return {spec['defaultReturnExpr']};"] if spec.get("defaultReturnExpr") is not None else [])]
    return "\n".join([hdr, *body, "}"])


def rewrite_headers(inc_dir: Path, schemas: dict[str, Any]) -> None:
    """Regenerate metalgear_globals.h and metalgear_functions.h with zero raw Ghidra aliases."""
    ov, gmap = schemas["overrides"], schemas["globalsMap"]
    seen = {g["name"] for g in gmap}
    g_lines = [
        '#pragma once\n#include "metalgear_types.h"\n', "/* D3 mapped globals (2324 mapped + deduplicated synthetic entries) */",
        *[f"{_format_c_decl(g['c_type'], g['name'])} /* {g['address']} [{g['program_scope']}] */" for g in gmap],
    ]
    for ent in ov.get("syntheticGlobals") or []:
        if (nm := ent["mappedName"]) not in seen:
            seen.add(nm)
            g_lines.append(f"{_format_c_decl(ent['cType'], nm)} /* {ent['addressHex']} [{ent['programScope']}] */")
    (inc_dir / "metalgear_globals.h").write_text("\n".join(g_lines) + "\n", encoding="utf-8", newline="\n")
    fh_path, kept = inc_dir / "metalgear_functions.h", []
    for ln in fh_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "Cross-bank / raw" in ln or "D3 trampoline" in ln:
            break
        if ln.strip() and not RAW_SYMBOL_RE.search(ln):
            kept.append(ln)
    decls = [*(ov.get("trampolineDeclarations") or []), *(ov.get("subEntryDeclarations") or [])]
    kept += ["/* D3 trampoline and sub-entry declarations */", *[f"{_format_proto(s)}; /* {s['addressHex']} */" for s in decls]]
    fh_path.write_text("\n".join(kept) + "\n", encoding="utf-8", newline="\n")


def extract_func_blocks(text: str) -> list[tuple[int, str, str]]:
    pos, starts, blocks = [m.start() for m in _FUNC_HDR_RE.finditer(text)], [], []
    for i, idx in enumerate(pos):
        prev = pos[i - 1] if i > 0 else 0
        doc = text.rfind("\n/**", prev, idx)
        if doc >= 0 and "*/" in text[doc:idx]:
            starts.append(doc + 1)
        else:
            starts.append(text.find("/**") if (i == 0 and text.lstrip().startswith("/**") and "*/" in text[:idx]) else idx)
    for i, st in enumerate(starts):
        blk = text[st:(starts[i + 1] if i + 1 < len(starts) else len(text))].strip()
        if m := _FUNC_HDR_RE.search(blk):
            blocks.append((int(m.group(2), 16), m.group(1), blk))
    return blocks


def _update_docs_and_cdb(dst_dir: Path, schemas: dict[str, Any], sym_to_rel: dict[str, str]) -> None:
    if (sym_p := dst_dir / "SYMBOL_MAP.md").is_file():
        row_re = re.compile(r"^(\| `0x[0-9a-fA-F]+` \| `[^`]+` \| `[^`]+` \| \d+ \| `)([^`]+)(` \| )\[`[^`]+`\]\([^)]+\)( \| .*)$")
        rows = [f"{m.group(1)}{m.group(2)}{m.group(3)}[`{sym_to_rel[m.group(2)]}`]({sym_to_rel[m.group(2)]}){m.group(4)}" if (m := row_re.match(ln)) and m.group(2) in sym_to_rel else ln for ln in sym_p.read_text(encoding="utf-8").splitlines()]
        sym_p.write_text("\n".join(rows) + "\n", encoding="utf-8", newline="\n")
    mods = schemas["moduleMap"]["modules"]
    mod_rows = [f"| `{m['relativePath']}` | `{m['domain']}` | {m['functionCount']} | {m['role']} |" for m in mods]
    (dst_dir / "ARCHITECTURE_WALKTHROUGH.md").write_text("\n".join([
        "# IronFrame OuterFortress (Cart) 01 — Cohesive Architecture Walkthrough", "",
        "- **Game ID:** `ironframe-outerfortress-cart-01` (`nes` / `retro_banked_asm_c`, ABI `nes-ines-6502`)",
        f"- **Coverage:** `{schemas['moduleMap']['functionCount']}` functions across `{len(mods)}` cohesive modules", "",
        "| Module | Domain | Functions | Role |", "| --- | --- | ---: | --- |", *mod_rows, "",
    ]), encoding="utf-8", newline="\n")
    inc, compat = (dst_dir / "include").as_posix(), (dst_dir / "include" / "ghidra_compat.h").as_posix()
    if (cl_p := dst_dir / ".clangd").is_file():
        txt = re.sub(r"(?m)^(\s*- -I).*$", rf"\1{inc}", cl_p.read_text(encoding="utf-8", errors="replace"))
        cl_p.write_text(re.sub(r"(?m)^(\s*- ).*/include/ghidra_compat\.h$", rf"\1{compat}", txt), encoding="utf-8", newline="\n")
    args = ["clang", "-target", "msp430-unknown-none-elf", "-ffreestanding", "-std=gnu11", f"-I{inc}", "-include", compat, "-c"]
    cdb = [{"directory": dst_dir.as_posix(), "file": p.as_posix(), "arguments": [*args, p.as_posix()]} for p in sorted(dst_dir.rglob("*.c"))]
    (dst_dir / "compile_commands.json").write_text(json.dumps(cdb, indent=2) + "\n", encoding="utf-8", newline="\n")


def coalesce_tier_dir(src_dir: Path, dst_dir: Path, schemas_dir: Path) -> dict[str, Any]:
    """Coalesce .c slices from src_dir into 26 clean D3 modules inside dst_dir."""
    src, dst, schemas = Path(src_dir).resolve(), Path(dst_dir).resolve(), load_d3_schemas(schemas_dir)
    rew = build_symbol_rewriter(schemas)
    fn_to_mod = {fn: mod["relativePath"] for mod in schemas["moduleMap"]["modules"] for fn in mod["functions"]}
    grouped: dict[str, list[tuple[int, str, str]]] = {m["relativePath"]: [] for m in schemas["moduleMap"]["modules"]}
    for cf in sorted(src.rglob("*.c")):
        for addr, name, blk in extract_func_blocks(cf.read_text(encoding="utf-8", errors="replace")):
            target = fn_to_mod.get(name)
            if target is None:
                raise ValueError(f"Unmapped catalog function '{name}' in {cf.name}")
            grouped[target].append((addr, name, rewrite_c_text(blk, rew)))
    if dst != src:
        if dst.exists():
            shutil.rmtree(dst, onexc=lambda fn, p, _: (os.chmod(p, stat.S_IWRITE | stat.S_IREAD), fn(p)))
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".cache", "__pycache__", "src", "overlays"), dirs_exist_ok=True)
    else:
        for old_c in sorted(dst.rglob("*.c")):
            old_c.unlink()
    tramps = [t for t in (schemas["overrides"].get("trampolineDeclarations") or [])]
    sym_to_rel: dict[str, str] = {}
    hdr = '#include "../../include/metalgear_types.h"\n#include "../../include/metalgear_globals.h"\n#include "../../include/metalgear_functions.h"\n\n'
    for rel, blocks in sorted(grouped.items()):
        if not blocks:
            continue
        blocks.sort(key=lambda t: (t[0], t[1]))
        parts = [b for _, _, b in blocks] + [_synth_trampoline_block(t) for t in tramps if t.get("targetModule") == rel]
        out_p = dst / rel
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(hdr + "\n\n".join(parts) + "\n", encoding="utf-8", newline="\n")
        for _, name, _ in blocks:
            sym_to_rel[name] = rel
    rewrite_headers(dst / "include", schemas)
    _update_docs_and_cdb(dst, schemas, sym_to_rel)
    if remaining := scan_raw_symbols(dst):
        raise ValueError(f"Unresolved raw symbols remain after D3 coalesce ({len(remaining)}): {remaining[:10]}")
    emitted_count = sum(1 for _ in dst.rglob("*.c"))
    return {"schemaVersion": 2, "gameId": ncc.GAME_ID, "isPassed": True, "moduleCount": emitted_count, "functionCount": len(sym_to_rel), "outDir": str(dst)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Coalesce D2 slices into 26 cohesive D3 domain C modules.")
    ap.add_argument("--data-dir", type=Path, default=None); ap.add_argument("--src-dir", type=Path, default=None)
    ap.add_argument("--out-dir", type=Path, default=None); ap.add_argument("--log-dir", type=Path, default=None)
    ap.add_argument("--offline-synthetic", action="store_true")
    args = ap.parse_args(argv)
    paths = ncc.resolve_paths(data_dir=args.data_dir)
    if args.offline_synthetic:
        with tempfile.TemporaryDirectory(prefix="d3_coal_syn_") as tmp:
            out_dir = Path(args.out_dir).resolve() if args.out_dir else (Path(tmp) / "D3_Mapped")
            out_dir.mkdir(parents=True, exist_ok=True)
            res = {"schemaVersion": 2, "gameId": ncc.GAME_ID, "isPassed": True, "mode": "offline-synthetic", "moduleCount": len(load_d3_schemas(paths.schemas_dir)["moduleMap"]["modules"]), "outDir": str(out_dir), "generatedAtUtc": ncc.utc_now_iso()}
            ncc.write_json_log(args.log_dir, "coalesce_d4_modules", res)
            print(json.dumps(res, indent=2))
            return 0
    src_dir = args.src_dir.resolve() if args.src_dir else paths.readable_dir
    if not (src_dir / "include" / "metalgear_globals.h").is_file() or not any(src_dir.rglob("*.c")):
        payload = ncc.missing_media_payload(src_dir, ["readable/*.c", "readable/include/metalgear_globals.h"], "Source readable C tree missing.")
        ncc.write_json_log(args.log_dir, "coalesce_d4_modules", payload)
        print(json.dumps(payload, indent=2))
        return 2
    out_dir = args.out_dir.resolve() if args.out_dir else (paths.corpus_root / "tiers" / "D3_Mapped")
    rep = {**coalesce_tier_dir(src_dir, out_dir, paths.schemas_dir), "generatedAtUtc": ncc.utc_now_iso()}
    ncc.write_json_log(args.log_dir, "coalesce_d4_modules", rep)
    print(json.dumps(rep, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
