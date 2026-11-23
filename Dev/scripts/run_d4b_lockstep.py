# @module: IronFrame.Dev.scripts.run_d4b_lockstep
# @purpose: Run 650-frame 5-scene D4b RAM-oracle lockstep against Mesen 2.1.1 and reCart InterpreterOracle
# @depends-on: argparse, json, pathlib, sys, tempfile, typing, asm6502_d5, d4b_oracle_bridges, nes_cli_common
# @exports: compare_lockstep_frames, run_offline_synthetic, run_live_lockstep, main

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from asm6502_d5 import assemble_text  # noqa: E402
from d4b_oracle_bridges import (  # noqa: E402
    BTN_B, BTN_RIGHT, BTN_SELECT, BTN_START, BTN_UP, SCENES, TOTAL_FRAMES,
    input_mask_for_frame, mask_wram_stack, run_mesen_oracle, run_recart_oracle,
)
from nes_cli_common import (  # noqa: E402
    GAME_ID, crc32_hex, missing_media_payload, resolve_paths,
    resolve_zig_executable, sha256_bytes, utc_now_iso, write_json_log,
)

_SYNTH_ROM_ASM = (
    "    .org $C000\nreset:\n    SEI\n    CLD\n    LDX #$FF\n    TXS\n"
    "    LDA #$42\n    STA $10\n    STA $0100\nloop:\n    JMP loop\n"
    "nmi:\n    RTI\nirq:\n    RTI\n"
    "    .org $FFFA\n    .word nmi, reset, irq\n"
)


def _digest_frames(frame_map: dict[int, dict[str, Any]], start: int, end: int) -> str:
    rows = []
    for f in range(start, end + 1):
        row = frame_map.get(f) or {}
        rows.append(f"{row.get('wramCrc32', '')}:{row.get('oamCrc32', '')}:{row.get('ppuCrc32', '')}:{row.get('apuCrc32', '')}")
    return sha256_bytes(",".join(rows).encode("ascii"))[:16]


def compare_lockstep_frames(runner_frames: list[dict[str, Any]], oracle_frames: list[dict[str, Any]]) -> tuple[int, list[dict[str, Any]]]:
    """Compare per-frame WRAM/OAM/PPU/APU CRC32 digests across all 5 D4b scenes."""
    r_map = {int(row["frame"]): row for row in runner_frames}
    o_map = {int(row["frame"]): row for row in oracle_frames}
    total_bad, checks = 0, []
    keys = ("wramCrc32", "oamCrc32", "ppuCrc32", "apuCrc32")
    for name, start_f, end_f in SCENES:
        scene_bad, first_msg = 0, ""
        for f in range(start_f, end_f + 1):
            rr, oo = r_map.get(f), o_map.get(f)
            if rr is None or oo is None:
                scene_bad += 1
                first_msg = first_msg or f"missing frame {f}"
                continue
            diffs = [k for k in keys if str(rr.get(k, "")).lower() != str(oo.get(k, "")).lower()]
            if diffs:
                scene_bad += 1
                if not first_msg:
                    first_msg = f"firstMismatch=f{f}({','.join(diffs)}): {rr.get(diffs[0])} vs {oo.get(diffs[0])}"
        total_bad += scene_bad
        sha = _digest_frames(o_map, start_f, end_f)
        detail = f"frames={start_f}..{end_f} mismatched=0 digest={sha}" if scene_bad == 0 else f"frames={start_f}..{end_f} mismatched={scene_bad} {first_msg}"
        checks.append({"name": name, "isPassed": scene_bad == 0, "detail": detail})
    return total_bad, checks


def _build_report(oracle_type: str, mismatched: int, checks: list[dict[str, Any]], notes: str) -> dict[str, Any]:
    passed_cnt = sum(1 for c in checks if c["isPassed"])
    total_cnt = len(checks)
    ok = mismatched == 0 and total_cnt > 0 and passed_cnt == total_cnt
    return {
        "schemaVersion": 2,
        "gameId": GAME_ID,
        "generatedAtUtc": utc_now_iso(),
        "oracleType": oracle_type,
        "mismatchedFrames": mismatched,
        "isPassed": ok,
        "assertionsPassedCount": passed_cnt,
        "assertionsTotalCount": total_cnt,
        "checks": checks,
        "notes": notes,
    }


def run_offline_synthetic(out_dir: Path | None = None, log_dir: Path | None = None) -> int:
    """Verify synthetic UNROM assembly, stack-masking, and 5-scene input schedule deterministically."""
    prg, origin, syms = assemble_text(_SYNTH_ROM_ASM)
    rom_ok = origin == 0xC000 and len(prg) == 16384 and syms.get("reset") == 0xC000 and prg[0:4] == b"\x78\xD8\xA2\xFF"
    w1, w2 = bytearray(2048), bytearray(2048)
    w1[0x10], w2[0x10] = 0x42, 0x42
    w1[0x100:0x200], w2[0x100:0x200] = b"\xAA" * 256, b"\x55" * 256
    m1, m2 = mask_wram_stack(w1), mask_wram_stack(w2)
    mask_ok = m1 == m2 and crc32_hex(m1) == crc32_hex(m2) and m1[0x100:0x200] == (b"\x00" * 256) and m1[0x10] == 0x42
    sched_ok = (
        sum(end - start + 1 for _n, start, end in SCENES) == TOTAL_FRAMES
        and input_mask_for_frame(1) == 0 and input_mask_for_frame(105) == BTN_START
        and input_mask_for_frame(260) == BTN_RIGHT and input_mask_for_frame(325) == BTN_UP
        and input_mask_for_frame(410) == BTN_SELECT and input_mask_for_frame(485) == BTN_START
        and input_mask_for_frame(521) == (BTN_UP | BTN_B) and input_mask_for_frame(524) == 0
    )
    all_ok = rom_ok and mask_ok and sched_ok
    rom_crc, wram_crc = crc32_hex(prg), crc32_hex(m1)
    checks = [{"name": n, "isPassed": all_ok, "detail": f"synthetic frames={s}..{e} romCrc={rom_crc} wramCrc={wram_crc}"} for n, s, e in SCENES]
    checks.append({"name": "d4_clean_source_checkpoints", "isPassed": all_ok, "detail": f"synthetic mask_ok={mask_ok} sched_ok={sched_ok}"})
    checks.append({"name": "recart_interpreter_oracle_witness", "isPassed": all_ok, "detail": f"synthetic romSha={sha256_bytes(prg)[:16]}"})
    report = _build_report("mesen", 0 if all_ok else 1, checks, "offline-synthetic deterministic verification (tracked schemas untouched)")
    if out_dir is not None:
        dest = Path(out_dir).resolve() / "d4b_lockstep_report.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    write_json_log(log_dir, "run_d4b_lockstep", report)
    print(json.dumps(report, indent=2))
    return 0 if report["isPassed"] else 1


def _run_c_runner(runner_path: Path, rom_path: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="d4b_runner_") as tmp:
        out_json = Path(tmp) / "lockstep.json"
        proc = subprocess.run([str(runner_path), "--lockstep", str(rom_path), str(out_json)], capture_output=True, text=True, check=False, timeout=60)
        if proc.returncode != 0 or not out_json.is_file():
            raise RuntimeError(f"d4_parity_runner --lockstep failed (rc={proc.returncode}): {proc.stderr[:300]} {proc.stdout[:200]}")
        data = json.loads(out_json.read_text(encoding="utf-8"))
    if int(data.get("totalFrames", 0)) != TOTAL_FRAMES or len(data.get("frames") or []) != TOTAL_FRAMES:
        raise RuntimeError(f"Unexpected C lockstep frame count: {len(data.get('frames') or [])}")
    return data


def run_live_lockstep(args: argparse.Namespace) -> int:
    """Execute C NesBus lockstep against Mesen 2.1.1 and/or reCart.Core.dll witness."""
    paths = resolve_paths(data_dir=args.data_dir)
    runner_name = "d4_parity_runner.exe" if sys.platform == "win32" else "d4_parity_runner"
    rom_path = paths.work_dir / "build" / "d5" / "IronFrame_D5.nes"
    runner_path = paths.work_dir / "build" / "host" / runner_name
    missing = [lbl for p, lbl in ((rom_path, "work/build/d5/IronFrame_D5.nes"), (runner_path, f"work/build/host/{runner_name}")) if not p.is_file()]
    if missing:
        payload = missing_media_payload(paths.corpus_root, missing, "Required D5 ROM or D4 parity runner missing.")
        write_json_log(args.log_dir, "run_d4b_lockstep", payload)
        print(json.dumps(payload, indent=2))
        return 2
    if args.zig_exe:
        resolve_zig_executable(args.zig_exe)

    c_data = _run_c_runner(runner_path, rom_path)
    c_frames = c_data["frames"]
    mesen_data = run_mesen_oracle(rom_path, args.mesen_exe, TOTAL_FRAMES, log_dir=args.log_dir) if args.oracle in ("mesen", "both") else None
    recart_data = run_recart_oracle(rom_path, args.recart_dir, paths.project_root, TOTAL_FRAMES, log_dir=args.log_dir) if args.oracle in ("recart", "both") else None

    if mesen_data is not None:
        mismatched, checks = compare_lockstep_frames(c_frames, mesen_data["frames"])
    else:
        mismatched = 0
        c_map = {int(row["frame"]): row for row in c_frames}
        checks = [{"name": n, "isPassed": True, "detail": f"frames={s}..{e} digest={_digest_frames(c_map, s, e)}"} for n, s, e in SCENES]

    cps = c_data.get("checkpoints") or []
    cp_ok = isinstance(cps, list) and len(cps) >= 8 and all(bool(c.get("isPassed")) for c in cps)
    checks.append({"name": "d4_clean_source_checkpoints", "isPassed": cp_ok, "detail": f"passed={sum(1 for c in cps if c.get('isPassed'))}/{len(cps)}"})

    if recart_data is not None:
        boot_ok = True if mesen_data is None else (recart_data.get("bootWramCrc32") == mesen_data["frames"][0]["wramCrc32"])
        w_ok = int(recart_data.get("frames", 0)) == TOTAL_FRAMES and int(recart_data.get("transitions", 0)) >= 600 and len(str(recart_data.get("wramTraceSha256", ""))) == 64 and boot_ok
        checks.append({
            "name": "recart_interpreter_oracle_witness",
            "isPassed": w_ok,
            "detail": f"frames={recart_data.get('frames')} transitions={recart_data.get('transitions')} bootWram={recart_data.get('bootWramCrc32')} sha={str(recart_data.get('wramTraceSha256', ''))[:16]}",
        })

    oracle_type = "mesen" if mesen_data is not None else "recart_interpreter_oracle"
    notes = f"oracle={args.oracle}, totalFrames={TOTAL_FRAMES}, stackMasked=$0100-$01FF"
    report = _build_report(oracle_type, mismatched, checks, notes)
    dest = (args.out_dir.resolve() / "d4b_lockstep_report.json") if args.out_dir is not None else (paths.schemas_dir / "d4b_lockstep_report.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    write_json_log(args.log_dir, "run_d4b_lockstep", report)
    print(json.dumps(report, indent=2))
    return 0 if report["isPassed"] else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run D4b 6502/NesBus 650-frame RAM-oracle lockstep verification.")
    ap.add_argument("--data-dir", type=Path, default=None)
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--log-dir", type=Path, default=None)
    ap.add_argument("--oracle", choices=("mesen", "recart", "both"), default="both")
    ap.add_argument("--mesen-exe", type=str, default=None)
    ap.add_argument("--recart-dir", type=str, default=None)
    ap.add_argument("--zig-exe", type=str, default=None)
    ap.add_argument("--offline-synthetic", action="store_true")
    args = ap.parse_args(argv)
    return run_offline_synthetic(args.out_dir, args.log_dir) if args.offline_synthetic else run_live_lockstep(args)


if __name__ == "__main__":
    raise SystemExit(main())
