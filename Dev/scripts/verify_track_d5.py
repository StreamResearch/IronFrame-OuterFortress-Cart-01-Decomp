# @module: IronFrame.Dev.scripts.verify_track_d5
# @purpose: Unified Tier R Stage D0-D5 / S0-S4 integrity, schemas, SLOC, and hygiene verifier
# @depends-on: argparse, hashlib, json, pathlib, re, subprocess, sys, zlib, asm6502_d5, nes_cli_common
# @exports: main

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import zlib
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from asm6502_d5 import OPCODES, assemble_text  # noqa: E402
from nes_cli_common import (  # noqa: E402
    GAME_ID,
    crc32_hex,
    iter_integrity_entries,
    missing_media_payload,
    resolve_optional_rd_tools,
    resolve_paths,
    sha256_file,
    utc_now_iso,
    write_json_log,
)

_EXPECTED_ROM_BYTES = 131088
_EXPECTED_ROM_CRC32 = "25ba3d04"
_EXPECTED_ROM_SHA1 = "9f7448fddaedc1801e2970e50722ac3cfacd19b8"
_EXPECTED_ROM_SHA256 = "79095355436222161cb3841ff9b5c7a572e77af11461935e433bd6e8dfd0f164"
_RAW_COL_RE = re.compile(r"^\$[0-9A-Fa-f]{4}:\s+[0-9A-Fa-f]{2}\b", re.M)
_BANNED_NAME_RE = re.compile(r"^(FUN_|fn_[0-9a-fA-F]+|func_[0-9a-fA-F]+|sub_[0-9a-fA-F]+|unk_|todo_|helper_[0-9]+$)")
_PARAM_PH_RE = re.compile(r"^param_[0-9]+$")
_LEGACY_V1_KEYS = frozenset({
    "generatedAt", "passed", "errors", "warnings", "compilerErrors", "compilerWarnings",
    "compiledFiles", "parityPassed", "parityTestsPassed", "parityTestsTotal", "assertionsPassed", "assertionsTotal",
    "matchedBinaries", "romBytes", "romMatched", "romCrc32", "romMd5", "romSha1", "relpath", "bytes", "sha256",
})
_SELFTEST_ASM = (
    'ZP_VAL = $10\nABS_VAL = $1234\n    .org $8000\nstart:\n    BRK\n    CLC\n    ASL\n    ASL A\n'
    '    LDA #$42\n    LDA ZP_VAL\n    LDA ZP_VAL,X\n    LDX ZP_VAL,Y\n    STX $20,Y\n'
    '    LDA ($30,X)\n    LDA ($30),Y\n    LDA a:$0013\n    LDA ABS_VAL\n    LDA ABS_VAL,X\n'
    '    LDA ABS_VAL,Y\n    JMP (ABS_VAL)\n    BVC start\n    SED\n    .byte "OK", $00\n'
    '    .word start, end_lbl\nend_lbl:\n'
)
_SELFTEST_HEX = "00180A0AA942A510B510B6109620A130B130AD1300AD3412BD3412B934126C341250DDF84F4B0000802B80"


def _rec(checks: list[dict[str, Any]], name: str, ok: bool, detail: str) -> None:
    checks.append({"name": name, "isPassed": bool(ok), "detail": detail})


def _load_json(path: Path) -> dict[str, Any] | list[Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _check_manifest(paths: Any, checks: list[dict[str, Any]]) -> dict[str, Any]:
    m = _load_json(paths.manifest_path)
    if not isinstance(m, dict):
        _rec(checks, "manifest_honest_state", False, "Missing or invalid Dev/research.manifest.json")
        return {}
    gates = m.get("gates") or {}
    d_ok = all((gates.get(t) or {}).get("passed") is True for t in ("D0", "D1", "D2"))
    s_ok = all((gates.get(t) or {}).get("passed") is True for t in ("S0", "S1", "S2", "S3", "S4"))
    met = m.get("metrics") or {}
    ws_ok = (paths.dev_dir / str(m.get("workspaceFile") or "")).is_file()
    ok = (
        m.get("schemaVersion") == 2 and m.get("gameId") == GAME_ID
        and m.get("currentDecompTier") in ("D2", "D3", "D4", "D5") and m.get("goalDecompTier") == "D5"
        and m.get("currentStudyTier") == "S4" and m.get("goalStudyTier") == "S5"
        and met.get("failedFunctions") == 0 and met.get("functionsTotal") == 499 and met.get("functionsNamed") == 499
        and met.get("globalsTotal") == 2324 and met.get("globalsMapped") == 2324 and d_ok and s_ok and ws_ok
    )
    _rec(checks, "manifest_honest_state", ok, f"D={m.get('currentDecompTier')}/{m.get('goalDecompTier')}, S={m.get('currentStudyTier')}/{m.get('goalStudyTier')}, fn={met.get('functionsNamed')}, g={met.get('globalsMapped')}, ws={ws_ok}")
    return m


def _has_legacy_v1(obj: Any) -> bool:
    if isinstance(obj, dict):
        return bool(_LEGACY_V1_KEYS & set(obj)) or any(_has_legacy_v1(v) for v in obj.values())
    if isinstance(obj, list):
        return any(_has_legacy_v1(v) for v in obj)
    return False


def _check_schemas(paths: Any, checks: list[dict[str, Any]]) -> list[tuple[str, int | None, str, str]]:
    sc = paths.schemas_dir
    integ = _load_json(sc / "standalone_integrity.json")
    entries = iter_integrity_entries(integ) if isinstance(integ, dict) else []
    req_blob = json.dumps(integ.get("requiredRomChecksums", "")).lower() if isinstance(integ, dict) else ""
    integ_ok = (
        isinstance(integ, dict) and integ.get("schemaVersion") == 2 and integ.get("gameId") == GAME_ID
        and isinstance(integ.get("entries"), list) and len(entries) == 17
        and _EXPECTED_ROM_SHA256 in req_blob and _EXPECTED_ROM_CRC32 in req_blob
    )
    _rec(checks, "standalone_integrity_v2", integ_ok, f"entries={len(entries)}/17, schema={integ.get('schemaVersion') if isinstance(integ, dict) else None}")

    cg, gi, cl = _load_json(sc / "call_graph.json"), _load_json(sc / "globals_index.json"), _load_json(sc / "clusters.json")
    gmap, sp = _load_json(sc / "globals_map.json"), _load_json(sc / "spec_coverage.json")
    cat = _load_json(sc / "functions_catalog.json")
    g_names = [str(r.get("name", "")) for r in gmap] if isinstance(gmap, list) else []
    bad_g = [n for n in g_names if not n or _BANNED_NAME_RE.match(n) or n.startswith(("DAT_", "UNK_"))]
    f_list = cat if isinstance(cat, list) else (cat.get("functions") or [] if isinstance(cat, dict) else [])
    f_names = [str(e.get("name", "")) for e in f_list if isinstance(e, dict)]
    bad_f = [n for n in f_names if _BANNED_NAME_RE.match(n)]
    bad_p = [p.get("name") for e in f_list if isinstance(e, dict) for p in (e.get("params") or []) if _PARAM_PH_RE.match(str(p.get("name", "")))]
    types_ok = (sc / "metalgear_types.h").is_file() and len(list((sc / "types").glob("*.h"))) >= 4
    s13_ok = (
        isinstance(cg, dict) and len(cg.get("functions") or {}) == 499 and not cg.get("strings")
        and isinstance(gi, dict) and len(gi.get("globals") or {}) == 2324 and isinstance(cl, dict) and bool(cl.get("function_to_domain"))
        and len(gmap) == 2324 and len(set(g_names)) == 2324 and not bad_g and types_ok
        and isinstance(sp, dict) and sp.get("schemaVersion") == 2 and sp.get("unresolvedFieldCount") == 0 and sp.get("mappedGlobalCount") == 2324
        and len(f_list) == 499 and len(set(f_names)) == 499 and not bad_f and not bad_p
    )
    _rec(checks, "stage1_to_3_schemas", s13_ok, f"funcs={len(set(f_names))}/499, globals={len(set(g_names))}/2324, specUnres={sp.get('unresolvedFieldCount') if isinstance(sp, dict) else None}")

    d4, s4, d5 = _load_json(sc / "d4_build_report.json"), _load_json(sc / "s4_verify_report.json"), _load_json(sc / "d5_byte_match.json")
    v2_clean = all(isinstance(r, dict) and r.get("schemaVersion") == 2 and r.get("gameId") == GAME_ID and not _has_legacy_v1(r) for r in (d4, s4, d5))
    rep_ok = (
        v2_clean and d4.get("isPassed") is True and d4.get("compilerErrorCount") == 0 and d4.get("compilerWarningCount") == 0
        and int(d4.get("assertionsPassedCount", 0)) >= 10 and int(d4.get("compiledFileCount", 0)) >= 68
        and s4.get("isPassed") is True and s4.get("compilerErrorCount") == 0 and s4.get("compilerWarningCount") == 0
        and int(s4.get("assertionsPassedCount", 0)) >= 10 and d5.get("isPassed") is True
        and d5.get("matchedBinaryCount") == 8 and d5.get("mismatchedBytes") == 0 and str(d5.get("crc32Hex", "")).lower() == _EXPECTED_ROM_CRC32
    )
    _rec(checks, "d4_s4_d5_reports_v2", rep_ok, f"v2Clean={v2_clean}, d4Pass={d4.get('isPassed') if isinstance(d4, dict) else None}, d5Crc={d5.get('crc32Hex') if isinstance(d5, dict) else None}")
    return entries


def _check_sloc_and_git(paths: Any, checks: list[dict[str, Any]]) -> None:
    over: list[str] = []
    for fp in sorted(paths.scripts_dir.rglob("*.py")):
        if "tests" in fp.parts or "__pycache__" in fp.parts:
            continue
        lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
        sloc = sum(1 for ln in lines if ln.strip() and not ln.lstrip().startswith("#"))
        cap = 265 if fp.name == "asm6502_d5.py" else 250
        if sloc > cap or (fp.name == "asm6502_d5.py" and len(lines) > 300):
            over.append(f"{fp.name}:{sloc}>{cap}")
    for fp in sorted((paths.scripts_dir / "d4_harness").glob("*")):
        if fp.is_file() and fp.suffix.lower() in (".c", ".h"):
            cnt = len(fp.read_text(encoding="utf-8", errors="replace").splitlines())
            if cnt > 250:
                over.append(f"{fp.name}:{cnt}>250")
    _rec(checks, "sloc_and_harness_limits", not over, f"overCap={over}")

    banned_dirs, banned_exts, leaks = ("Corpus/", "standalone/", "work/", "readable/"), (".nes", ".fds", ".prg", ".s", ".7z", ".zip", ".exe", ".dll", ".o", ".a"), []
    for cmd in (["git", "-C", str(paths.project_root), "status", "--short"], ["git", "-C", str(paths.project_root), "ls-files"]):
        gp = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=15)
        for raw in gp.stdout.splitlines():
            p = (raw[3:].strip() if cmd[-1] == "--short" else raw.strip()).strip('"').replace("\\", "/")
            if any(seg in p for seg in banned_dirs) or p.lower().endswith(banned_exts):
                leaks.append(p)
    _rec(checks, "git_cleanroom_hygiene", not leaks, f"leaks={sorted(set(leaks))[:5]}")


def _check_corpus_artifacts(paths: Any, entries: list[tuple[str, int | None, str, str]], tools_dir: Path | None, checks: list[dict[str, Any]]) -> None:
    bad_ent = [
        rel for rel, sz, sha, crc in entries
        if not (fp := paths.standalone_dir / rel).is_file() or (sz is not None and fp.stat().st_size != sz)
        or (sha and sha256_file(fp) != sha) or (crc and crc32_hex(fp.read_bytes()) != crc)
    ]
    _rec(checks, "corpus_standalone_files", len(entries) == 17 and not bad_ent, f"entries={len(entries)}, bad={bad_ent[:3]}")
    c_files = sorted(paths.readable_dir.rglob("*.c"))
    failed_m = sum(1 for p in c_files if "DECOMPILE FAILED" in p.read_text(encoding="utf-8", errors="replace"))
    compat = paths.readable_dir / "include" / "ghidra_compat.h"
    rec_inc = compat.is_file() and bool(re.search(r'^\s*#include\s+"[^"]*_types\.h"', compat.read_text(encoding="utf-8"), re.M))
    _rec(checks, "corpus_readable_c_tree", len(c_files) >= 68 and failed_m == 0 and compat.is_file() and not rec_inc and (paths.readable_dir / "compile_commands.json").is_file(), f"cFiles={len(c_files)}, failedMarkers={failed_m}")

    arch = paths.work_dir / "build" / "le16" / "libmetal_gear_d4.a"
    runner = paths.work_dir / "build" / "host" / ("d4_parity_runner.exe" if sys.platform == "win32" else "d4_parity_runner")
    if runner.is_file() and arch.is_file() and arch.stat().st_size > 0:
        proc = subprocess.run([str(runner), str(paths.standalone_dir / "extracted")], capture_output=True, text=True, encoding="utf-8", timeout=20)
        live = json.loads(proc.stdout) if proc.returncode == 0 and proc.stdout.strip() else {}
        _rec(checks, "d4_live_parity_runner", proc.returncode == 0 and live.get("isPassed") is True and int(live.get("assertionsPassedCount", 0)) >= 10, f"rc={proc.returncode}, passed={live.get('assertionsPassedCount')}/{live.get('assertionsTotalCount')}")
    else:
        _rec(checks, "d4_live_parity_runner", False, f"Missing {runner} or {arch}")

    asm_dir = paths.work_dir / "asm_d5"
    asm_names = [f"BANK_{b:02d}.asm" for b in range(7)] + ["PRG_FIXED_07.asm"]
    raw_leaks = [n for n in asm_names if not (asm_dir / n).is_file() or _RAW_COL_RE.search((asm_dir / n).read_text(encoding="utf-8"))]
    rom_dir = paths.work_dir / "build" / "d5"
    rom_p = rom_dir / "IronFrame_D5.nes"
    rom_b = rom_p.read_bytes() if rom_p.is_file() else b""
    rom_ok = len(rom_b) == _EXPECTED_ROM_BYTES and crc32_hex(rom_b) == _EXPECTED_ROM_CRC32 and hashlib.sha1(rom_b).hexdigest().lower() == _EXPECTED_ROM_SHA1
    exp_sha = {rel: sha for rel, _sz, sha, _crc in entries}
    prg_ok = all((p := paths.work_dir / "build" / "d5" / rel).is_file() and sha256_file(p) == exp_sha.get(rel, "") for rel in [f"extracted/BANK_{b:02d}.prg" for b in range(7)] + ["extracted/PRG_FIXED_07.prg"])
    _rec(checks, "d5_asm_and_rom_match", not raw_leaks and rom_ok and prg_ok, f"asmIssues={raw_leaks}, romOk={rom_ok}, prgOk={prg_ok}")

    rd_tools = resolve_optional_rd_tools(tools_dir, paths.project_root)
    if rd_tools is not None and (paths.project_root / "Corpus").is_dir():
        if str(rd_tools) not in sys.path:
            sys.path.insert(0, str(rd_tools))
        from decomp.tier_verifier import verify_track
        cli_res = verify_track(paths.project_root, run_clangd_check=False)
        _rec(checks, "rd_optional_tier_verifier", bool(cli_res.get("passed")), f"errors={cli_res.get('errors')}")
    else:
        _rec(checks, "rd_optional_tier_verifier", True, "optional R&D tools or repo Corpus absent; skipped")


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify Tier R IronFrame Cart 01 schemas, SLOC, hygiene, and D4/D5 artifacts.")
    ap.add_argument("--data-dir", type=Path, default=None)
    ap.add_argument("--log-dir", type=Path, default=None)
    ap.add_argument("--tools-dir", type=Path, default=None)
    ap.add_argument("--offline-synthetic", action="store_true")
    args = ap.parse_args()

    paths = resolve_paths(data_dir=args.data_dir)
    if not args.offline_synthetic and (not (paths.standalone_dir / "extracted").is_dir() or not paths.readable_dir.is_dir()):
        payload = missing_media_payload(paths.corpus_root, ["standalone/extracted", "readable"], "Corpus media missing; pass --data-dir or --offline-synthetic.")
        write_json_log(args.log_dir, "verify_track_d5", payload)
        print(json.dumps(payload, indent=2))
        return 2

    checks: list[dict[str, Any]] = []
    raw_st, orig_st, syms_st = assemble_text(_SELFTEST_ASM)
    st_ok = len(OPCODES) == 56 and sum(len(m) for m in OPCODES.values()) == 151 and orig_st == 0x8000 and raw_st.hex().upper() == _SELFTEST_HEX and syms_st.get("end_lbl") == 0x802B
    _rec(checks, "d5_asm6502_selftest", st_ok, f"mnem={len(OPCODES)}/56, bytes={len(raw_st)}, end=${syms_st.get('end_lbl', 0):04X}")
    _check_manifest(paths, checks)
    entries = _check_schemas(paths, checks)
    _check_sloc_and_git(paths, checks)
    if not args.offline_synthetic:
        _check_corpus_artifacts(paths, entries, args.tools_dir, checks)

    passed_n = sum(1 for c in checks if c["isPassed"])
    summary = {
        "schemaVersion": 2, "gameId": GAME_ID, "mode": "offline-synthetic" if args.offline_synthetic else "full",
        "isPassed": passed_n == len(checks), "checksPassedCount": passed_n, "checksTotalCount": len(checks),
        "checks": checks, "generatedAtUtc": utc_now_iso(),
    }
    write_json_log(args.log_dir, "verify_track_d5", summary)
    print(json.dumps(summary, indent=2))
    return 0 if summary["isPassed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
