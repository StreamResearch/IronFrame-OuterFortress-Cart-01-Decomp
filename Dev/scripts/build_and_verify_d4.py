# @module: IronFrame.Dev.scripts.build_and_verify_d4
# @purpose: Stage D4 Zig freestanding archive builder and native host parity harness verifier
# @depends-on: argparse, json, os, pathlib, re, subprocess, sys, tempfile, nes_cli_common
# @exports: PASS1_FLAGS, TARGET_LINK_FUNCS, generate_globals_defs, generate_host_stubs, run_pass1_archive, run_pass2_host, main

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from nes_cli_common import (  # noqa: E402
    GAME_ID, detect_host_zig_target, missing_media_payload, resolve_paths,
    resolve_zig_executable, utc_now_iso, write_json_log,
)

FUNC_DECL_RE = re.compile(r"^\s*([A-Za-z_][\w\s\*]*?)\s+([A-Za-z_]\w*)\s*\(([^;]*)\)\s*;")
EXTERN_DECL_RE = re.compile(r"^\s*extern\s+(.+?);\s*(?:/\*.*?\*/\s*)?$")
UNBOUNDED_ARR_RE = re.compile(r"\[\s*\]\s*$")
_GHIDRA_CRAFT_RE = re.compile(
    r"/\*\s*WARNING:|//\s*Function:|\(void\s*\*\)\s*0x0\b|\(\*\(code\s*\*\)\s*\(uintptr_t\)"
    r"|\b(?:uVar|iVar|puVar|piVar|pcVar|pbVar|psVar|pvVar|lVar|fVar|dVar|local_|unaff_|in_|extraout_)[0-9A-Za-z_]*\b"
)
PASS1_FLAGS = ["-std=gnu11", "-fsigned-char", "-O1", "-ffreestanding", "-fno-builtin"]
TARGET_LINK_FUNCS = frozenset(
    "mg_fxa_enter_game_mode mg_fxa_advance_game_mode mg_fxa_tick_state_timer inline_jump_table_dispatch "
    "unrom_select_bank_0 unrom_restore_active_bank read_joypads_edge_triggered mg_b034_hud_write_bcd_digit_tile "
    "mg_b034_update_bridge_platforms_and_fall_check mg_b034_tick_countdown_timer_and_hud "
    "mg_b034_set_timer_state_67 mg_b56_transceiver_update_freq_hud mg_b56_audio_update_channel "
    "mg_b56_audio_parse_seq_event mg_b56_audio_exec_control_opcode mg_b56_audio_sync_pause_mute "
    "mg_b56_audio_backup_pause_state mg_b56_audio_ramp_dmc_dac".split()
)
_SYNTH_U8 = (
    "g_game_mode g_game_submode g_frame_counter g_title_exit_flag g_pause_flag g_state_timer_lo "
    "g_state_timer_hi g_apu_pulse1_ctrl g_apu_pulse1_sweep g_apu_pulse2_ctrl g_apu_pulse2_sweep "
    "g_apu_noise_ctrl g_apu_dmc_dac DAT_0067 DAT_0071 DAT_00ea DAT_00eb DAT_0384 DAT_0388 DAT_038a "
    "DAT_0390 DAT_0396 DAT_039c DAT_03a2 DAT_03ae DAT_03cc DAT_03d8 DAT_03f8 DAT_03ff DAT_0740 DAT_0741"
).split()
_SYNTH_FUNCS = (
    "void unrom_select_bank_0(void); void unrom_select_bank_6(void); void mg_b034_hud_init_vram_queue_header(void); "
    "void mg_b034_set_timer_state_67(byte v); void mg_b034_tick_countdown_timer_and_hud(void); "
    "byte mg_fxa_tick_state_timer(void); byte mg_fxa_enter_game_mode(byte m); void mg_fxa_advance_game_mode(void); "
    "void mg_b56_audio_sync_pause_mute(void); void mg_b56_audio_ramp_dmc_dac(void);"
)


def _zig_env(work_dir: Path) -> dict[str, str]:
    cache_dir = work_dir / "zig-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return {**os.environ, "ZIG_LOCAL_CACHE_DIR": str(cache_dir), "ZIG_GLOBAL_CACHE_DIR": str(cache_dir)}


def _run_zig(zig: Path, env: dict[str, str], args: list[str]) -> tuple[int, int, int, str]:
    res = subprocess.run([str(zig), *args], capture_output=True, text=True, env=env)
    errs = sum(1 for ln in res.stderr.splitlines() if ": error:" in ln or ln.startswith("error:"))
    wrns = sum(1 for ln in res.stderr.splitlines() if ": warning:" in ln or ln.startswith("warning:"))
    return res.returncode, errs + (1 if res.returncode != 0 and errs == 0 else 0), wrns, res.stderr


def _probe_target(zig: Path, env: dict[str, str], work_dir: Path) -> str:
    probe_c, probe_o = work_dir / "build" / "le16" / "_target_probe.c", work_dir / "build" / "le16" / "_target_probe.o"
    probe_c.parent.mkdir(parents=True, exist_ok=True)
    probe_c.write_text("int mg_d4_probe(int x) { return x + 1; }\n", encoding="utf-8")
    try:
        for target in ("msp430-freestanding-none", "x86-freestanding-none"):
            if _run_zig(zig, env, ["cc", "-target", target, *PASS1_FLAGS, "-c", str(probe_c), "-o", str(probe_o)])[0] == 0:
                return target
    finally:
        probe_c.unlink(missing_ok=True)
        probe_o.unlink(missing_ok=True)
    return "x86-freestanding-none"


def generate_globals_defs(globals_h: Path, dst_c: Path) -> int:
    """Emit zero-initialized definitions for every extern declaration in metalgear_globals.h."""
    lines = ['#include "metalgear_globals.h"\n']
    for raw in globals_h.read_text(encoding="utf-8").splitlines():
        if m := EXTERN_DECL_RE.match(raw):
            lines.append(f"{UNBOUNDED_ARR_RE.sub('[256]', m.group(1).strip())} = {{0}};")
    dst_c.parent.mkdir(parents=True, exist_ok=True)
    dst_c.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(lines) - 1


def _select_link_tus(c_files: list[Path]) -> tuple[list[Path], set[str]]:
    selected, defined = [], set()
    def_re = re.compile(r"^[A-Za-z_][\w\s\*]*?\b([A-Za-z_]\w*)\s*\([^;]*\)\s*\{", re.MULTILINE)
    for cf in c_files:
        defs = set(def_re.findall(cf.read_text(encoding="utf-8", errors="replace")))
        if defs & TARGET_LINK_FUNCS:
            selected.append(cf)
            defined |= defs
    return selected, defined


def generate_host_stubs(functions_h: Path, compat_h: Path, defined_syms: set[str], dst_c: Path) -> int:
    """Generate host-safe stubs for all unlinked declarations in metalgear_functions.h."""
    lines = ['#include "metalgear_functions.h"\n']
    if "halt_baddata" not in defined_syms and compat_h.is_file() and "halt_baddata" in compat_h.read_text(encoding="utf-8", errors="replace"):
        lines.append("void halt_baddata(void) {}\n")
    count = 0
    for raw in functions_h.read_text(encoding="utf-8").splitlines():
        m = FUNC_DECL_RE.match(raw)
        if not m or m.group(2).strip() in defined_syms:
            continue
        ret_t, name, params = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
        defined_syms.add(name)
        args = [re.sub(r"\[.*\]", "", p.strip().split()[-1].lstrip("*")) or f"a{i}" for i, p in enumerate(params.split(","))] if params and params != "void" else []
        silencers = " ".join(f"(void){a};" for a in args)
        ret_stmt = "" if ret_t == "void" else f" return ({ret_t})0;"
        lines.append(f"{ret_t} {name}({params}) {{ {silencers}{ret_stmt} }}")
        count += 1
    dst_c.parent.mkdir(parents=True, exist_ok=True)
    dst_c.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return count


def run_pass1_archive(zig: Path, env: dict[str, str], c_files: list[Path], readable_dir: Path, globals_c: Path, work_dir: Path) -> tuple[str, int, int, int, list[str]]:
    """Compile all readable/*.c translation units and archive libmetal_gear_d4.a."""
    target = _probe_target(zig, env, work_dir)
    obj_dir = work_dir / "build" / "le16" / "obj"
    obj_dir.mkdir(parents=True, exist_ok=True)
    flags = ["-target", target, *PASS1_FLAGS, "-I", str(readable_dir / "include")]
    objs, compiled_c, errors, warnings, diags = [], 0, 0, 0, []
    for tu in [*c_files, globals_c]:
        tag = tu.name if tu == globals_c else tu.relative_to(readable_dir).as_posix().replace("/", "__")
        obj = obj_dir / f"{tag}.o"
        rc, e, w, err = _run_zig(zig, env, ["cc", *flags, "-c", str(tu), "-o", str(obj)])
        errors, warnings = errors + e, warnings + w
        if err.strip() and len(diags) < 25:
            diags.extend(err.strip().splitlines()[:6])
        if rc == 0:
            objs.append(obj)
            compiled_c += int(tu != globals_c)
    arch = work_dir / "build" / "le16" / "libmetal_gear_d4.a"
    arch.unlink(missing_ok=True)
    if objs and errors == 0:
        rc_a, _, _, err_a = _run_zig(zig, env, ["ar", "rcs", str(arch), *(str(o) for o in objs)])
        if rc_a != 0:
            errors += 1
            diags.append(err_a.strip())
    return target, compiled_c, errors, warnings, diags


def run_pass2_host(zig: Path, env: dict[str, str], host_target: str, c_files: list[Path], readable_dir: Path, globals_c: Path, extracted_dir: Path, work_dir: Path) -> tuple[bool, int, int, list[dict[str, Any]], int, int, list[str]]:
    """Link selected readable TUs against d4_harness/*.c and run host parity assertions."""
    host_dir = work_dir / "build" / "host"
    host_dir.mkdir(parents=True, exist_ok=True)
    linked_tus, defined_syms = _select_link_tus(c_files)
    stubs_c, inc_dir, harness_dir = host_dir / "host_stubs.c", readable_dir / "include", SCRIPT_DIR / "d4_harness"
    harness_c = sorted(harness_dir.glob("*.c"))
    generate_host_stubs(inc_dir / "metalgear_functions.h", inc_dir / "ghidra_compat.h", defined_syms, stubs_c)
    runner = host_dir / ("d4_parity_runner.exe" if "windows" in host_target else "d4_parity_runner")
    rc, errs, wrns, err = _run_zig(zig, env, [
        "cc", "-target", host_target, "-std=gnu11", "-fsigned-char", "-O1", "-I", str(inc_dir), "-I", str(harness_dir),
        "-Wno-int-to-pointer-cast", "-Wno-pointer-to-int-cast", *(str(p) for p in [*linked_tus, globals_c, stubs_c, *harness_c]), "-o", str(runner),
    ])
    if rc != 0:
        return False, 0, 0, [{"name": "host_link", "isPassed": False, "detail": err[:800]}], errs, wrns, err.splitlines()[:15]
    run = subprocess.run([str(runner), str(extracted_dir)], capture_output=True, text=True, env=env)
    if run.returncode != 0 and not run.stdout.strip():
        return False, 0, 0, [{"name": "host_exec", "isPassed": False, "detail": f"rc={run.returncode} {run.stderr[:400]}"}], errs + 1, wrns, []
    payload = json.loads(run.stdout)
    tests = payload.get("tests", [])
    p_cnt, t_cnt = int(payload.get("assertionsPassedCount", 0)), int(payload.get("assertionsTotalCount", len(tests)))
    return bool(payload.get("isPassed", False)) and p_cnt == t_cnt and t_cnt >= 10 and errs == 0, p_cnt, t_cnt, tests, errs, wrns, []


def _build_d4_report(
    target: str, host_target: str, zig_ver: str, compiler_flags: list[str], total_c: int, compiled_c: int, arch_path: str,
    errs: int, wrns: int, tells: int, is_passed: bool, p_cnt: int, t_cnt: int, tests: list[dict[str, Any]],
) -> dict[str, Any]:
    strict_flags = {"-Wall", "-Wextra", "-Wno-unused-parameter"}.issubset(compiler_flags) and "-Wno-everything" not in compiler_flags
    return {
        "schemaVersion": 2, "gameId": GAME_ID, "generatedAtUtc": utc_now_iso(), "tierMode": "tier_r",
        "target": target, "hostParityTarget": host_target, "compiler": f"zig cc {zig_ver}", "compilerFlags": compiler_flags,
        "totalReadableFiles": total_c, "compiledFileCount": compiled_c, "archivePath": arch_path,
        "compilerErrorCount": errs, "compilerWarningCount": wrns, "craftsmanshipTellCount": tells,
        "isZeroWarningsVerified": errs == 0 and wrns == 0 and compiled_c > 0 and strict_flags,
        "isZeroDecompilerTellsVerified": tells == 0,
        "isPassed": is_passed, "assertionsPassedCount": p_cnt, "assertionsTotalCount": t_cnt, "tests": tests,
    }


def _run_offline_synthetic(zig: Path, zig_ver: str, host_target: str, out_dir: Path | None, log_dir: Path | None) -> int:
    harness_dir, synth_flags = SCRIPT_DIR / "d4_harness", ["-std=gnu11", "-fsigned-char", "-Wall", "-Wextra", "-Wno-unused-parameter", "-Werror"]
    harness_c = sorted(harness_dir.glob("*.c"))
    with tempfile.TemporaryDirectory(prefix="d4_synth_") as tmp:
        work = out_dir.resolve() if out_dir else Path(tmp)
        env, inc = _zig_env(work), work / "synth_inc"
        target = _probe_target(zig, env, work)
        inc.mkdir(parents=True, exist_ok=True)
        (inc / "metalgear_globals.h").write_text("#pragma once\n#include <stdint.h>\nextern uint8_t BYTE_ARRAY_ff99[];\n" + "\n".join(f"extern uint8_t {g};" for g in _SYNTH_U8) + "\n", encoding="utf-8")
        (inc / "metalgear_functions.h").write_text("#pragma once\n#include <stdint.h>\ntypedef uint8_t byte;\n" + _SYNTH_FUNCS.replace("; ", ";\n") + "\n", encoding="utf-8")
        globals_c, stubs_c = work / "synth_globals.c", work / "synth_stubs.c"
        generate_globals_defs(inc / "metalgear_globals.h", globals_c)
        generate_host_stubs(inc / "metalgear_functions.h", inc / "none.h", set(), stubs_c)
        errs, wrns, checks, tus = 0, 0, [], [*harness_c, globals_c, stubs_c]
        for src in tus:
            rc, e, w, err = _run_zig(zig, env, ["cc", "-target", host_target, *synth_flags, "-I", str(inc), "-I", str(harness_dir), "-c", str(src), "-o", str(work / f"{src.stem}.o")])
            errs, wrns = errs + e, wrns + w
            checks.append({"name": f"compile_{src.name}", "isPassed": rc == 0 and w == 0, "detail": err.strip()[:240] or "ok"})
        exe = work / ("d4_synth_runner.exe" if "windows" in host_target else "d4_synth_runner")
        rc_l, e_l, w_l, err_l = _run_zig(zig, env, ["cc", "-target", host_target, *(str(work / f"{s.stem}.o") for s in tus), "-o", str(exe)])
        errs, wrns = errs + e_l, wrns + w_l
        checks.append({"name": "link_synthetic_harness", "isPassed": rc_l == 0 and w_l == 0, "detail": err_l.strip()[:240] or "ok"})
    p_cnt = sum(1 for c in checks if c["isPassed"])
    report = _build_d4_report(target, host_target, zig_ver, synth_flags, 0, len(harness_c), "", errs, wrns, 0, errs == 0 and wrns == 0 and p_cnt == len(checks), p_cnt, len(checks), checks)
    report["mode"] = "offline-synthetic"
    if out_dir is not None:
        out_dir.resolve().mkdir(parents=True, exist_ok=True)
        (out_dir.resolve() / "d4_build_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    write_json_log(log_dir, "build_and_verify_d4", report)
    print(json.dumps(report, indent=2))
    return 0 if report["isPassed"] else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Build & verify IronFrame Cart 01 D4/S4 artifacts.")
    ap.add_argument("--data-dir", type=Path, default=None); ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--log-dir", type=Path, default=None); ap.add_argument("--zig-exe", type=str, default=None)
    ap.add_argument("--host-target", type=str, default=None); ap.add_argument("--skip-host-parity", action="store_true")
    ap.add_argument("--offline-synthetic", action="store_true"); ap.add_argument("--update-manifest", action="store_true")
    args = ap.parse_args()
    paths = resolve_paths(data_dir=args.data_dir)
    extracted_dir = paths.standalone_dir / "extracted"
    if not args.offline_synthetic:
        missing = [lbl for p, lbl in ((paths.readable_dir / "include" / "metalgear_globals.h", "readable/include/metalgear_globals.h"), (extracted_dir / "PRG_FIXED_07.prg", "standalone/extracted/PRG_FIXED_07.prg")) if not p.is_file()]
        if missing:
            payload = missing_media_payload(paths.corpus_root, missing, "Required readable C tree or extracted PRGs missing.")
            write_json_log(args.log_dir, "build_and_verify_d4", payload)
            print(json.dumps(payload, indent=2))
            return 2
    zig = resolve_zig_executable(args.zig_exe)
    zig_ver, host_target = subprocess.check_output([str(zig), "version"], text=True).strip(), detect_host_zig_target(args.host_target)
    if args.offline_synthetic:
        return _run_offline_synthetic(zig, zig_ver, host_target, args.out_dir, args.log_dir)
    work_dir = args.out_dir.resolve() if args.out_dir else paths.work_dir
    report_dir = args.out_dir.resolve() if args.out_dir else paths.schemas_dir
    env, c_files = _zig_env(work_dir), sorted(paths.readable_dir.rglob("*.c"))
    tell_count = sum(len(_GHIDRA_CRAFT_RE.findall(p.read_text(encoding="utf-8", errors="replace"))) for p in c_files)
    globals_c = work_dir / "build" / "le16" / "globals_defs.c"
    generate_globals_defs(paths.readable_dir / "include" / "metalgear_globals.h", globals_c)
    target, compiled_c, p1_errs, p1_wrns, p1_diags = run_pass1_archive(zig, env, c_files, paths.readable_dir, globals_c, work_dir)
    if args.skip_host_parity or p1_errs > 0:
        parity_ok, t_pass, t_tot, tests, p2_errs, p2_wrns, p2_diags = False, 0, 0, [{"name": "skipped", "isPassed": False, "detail": "Pass 1 errors or skipped"}], 0, 0, []
    else:
        parity_ok, t_pass, t_tot, tests, p2_errs, p2_wrns, p2_diags = run_pass2_host(zig, env, host_target, c_files, paths.readable_dir, globals_c, extracted_dir, work_dir)
    tot_errs, tot_wrns = p1_errs + p2_errs, p1_wrns + p2_wrns
    s4_ok = tot_errs == 0 and tot_wrns == 0 and parity_ok and compiled_c == len(c_files) and len(c_files) > 0
    d4_report = _build_d4_report(target, host_target, zig_ver, PASS1_FLAGS, len(c_files), compiled_c, "work/build/le16/libmetal_gear_d4.a", tot_errs, tot_wrns, tell_count, s4_ok, t_pass, t_tot, tests)
    s4_report = {"schemaVersion": 2, "gameId": GAME_ID, "generatedAtUtc": d4_report["generatedAtUtc"], "isPassed": s4_ok, "compilerErrorCount": tot_errs, "compilerWarningCount": tot_wrns, "assertionsPassedCount": t_pass, "assertionsTotalCount": t_tot, "checks": tests}
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "d4_build_report.json").write_text(json.dumps(d4_report, indent=2) + "\n", encoding="utf-8")
    (report_dir / "s4_verify_report.json").write_text(json.dumps(s4_report, indent=2) + "\n", encoding="utf-8")
    if args.update_manifest and args.out_dir is None and s4_ok and paths.manifest_path.is_file():
        m = json.loads(paths.manifest_path.read_text(encoding="utf-8"))
        m.setdefault("builds", {})["d4Report"], m["updatedAtUtc"] = "schemas/d4_build_report.json", utc_now_iso()
        paths.manifest_path.write_text(json.dumps(m, indent=2) + "\n", encoding="utf-8")
    write_json_log(args.log_dir, "build_and_verify_d4", d4_report)
    print(json.dumps(d4_report, indent=2))
    for ln in (p1_diags + p2_diags)[:20]:
        print("DIAG:", ln, file=sys.stderr)
    return 0 if s4_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
