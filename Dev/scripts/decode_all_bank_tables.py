# @module: IronFrame.Dev.scripts.decode_all_bank_tables
# @purpose: Shared PRG window helpers, all-bank table decoder orchestrator, and spec_coverage.json v2 writer
# @depends-on: argparse, json, struct, sys, tempfile, pathlib, typing, export_decomp_bundle, gen_d4_globals_and_lifts, nes_cli_common
# @exports: BANK_WINDOW_BYTES, SPEC_SPOKES, u16_le, u16_be, s8, slice_prg_window, load_prg_banks, make_blank_banks, in_bank, write_json, run_decoder_cli, check_spec_spokes, main

from __future__ import annotations

import argparse
import json
import struct
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from export_decomp_bundle import validate_cleanroom_bytes  # noqa: E402
from gen_d4_globals_and_lifts import validate_schemas  # noqa: E402
from nes_cli_common import (  # noqa: E402
    GAME_ID,
    TrackPaths,
    missing_media_payload,
    resolve_paths,
    utc_now_iso,
    write_json_log,
)

BANK_WINDOW_BYTES = 0x4000
ALL_BANK_NAMES = tuple(f"BANK_{b:02d}.prg" for b in range(7)) + ("PRG_FIXED_07.prg",)
SPEC_SPOKES = (
    "symbol-and-bank-reference.md",
    "rooms-metatiles-and-chr-format.md",
    "guards-weapons-and-password-format.md",
    "codec-and-bank06-audio-format.md",
)


def u16_le(buf: bytes | bytearray, base: int, addr: int) -> int:
    """Read little-endian 16-bit integer at CPU address inside a 16 KiB bank."""
    return int(struct.unpack_from("<H", buf, addr - base)[0])


def u16_be(buf: bytes | bytearray, base: int, addr: int) -> int:
    """Read big-endian 16-bit integer at CPU address inside a 16 KiB bank."""
    return int(struct.unpack_from(">H", buf, addr - base)[0])


def s8(val: int) -> int:
    """Convert unsigned byte 0..255 to signed 8-bit integer -128..127."""
    return val - 256 if val >= 128 else val


def in_bank(addr: int, is_fixed: bool = False) -> bool:
    """Return True if CPU address lies inside the 16 KiB switchable or fixed PRG window."""
    return (0xC000 <= addr < 0x10000) if is_fixed else (0x8000 <= addr < 0xC000)


def slice_prg_window(raw: bytes, is_fixed: bool) -> bytes:
    """Extract the 16 KiB $8000-$BFFF or $C000-$FFFF PRG window from a 32 KiB or 16 KiB .prg file."""
    if len(raw) >= 2 * BANK_WINDOW_BYTES:
        return raw[BANK_WINDOW_BYTES:2 * BANK_WINDOW_BYTES] if is_fixed else raw[:BANK_WINDOW_BYTES]
    if len(raw) == BANK_WINDOW_BYTES:
        return raw
    raise ValueError(f"Unexpected .prg byte length {len(raw)}; expected 16384 or 32768")


def load_prg_banks(paths: TrackPaths, bank_names: tuple[str, ...]) -> tuple[dict[str, bytes], list[str]]:
    """Load and slice required 16 KiB PRG windows from standalone/extracted/*.prg."""
    ext_dir = paths.standalone_dir / "extracted"
    missing: list[str] = []
    banks: dict[str, bytes] = {}
    for name in bank_names:
        fp = ext_dir / name
        if not fp.is_file():
            missing.append(f"standalone/extracted/{name}")
            continue
        banks[name] = slice_prg_window(fp.read_bytes(), "FIXED" in name)
    return banks, missing


def make_blank_banks() -> dict[str, bytearray]:
    """Create blank 16 KiB 0xFF-filled buffers for all 8 PRG banks."""
    return {name: bytearray([0xFF] * BANK_WINDOW_BYTES) for name in ALL_BANK_NAMES}


def write_json(path: Path, data: dict[str, Any]) -> None:
    """Write deterministic formatted JSON ending with a newline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def run_decoder_cli(
    stem: str,
    bank_names: tuple[str, ...],
    synth_fn: Callable[[], dict[str, bytes]],
    decode_fn: Callable[[dict[str, bytes]], dict[str, Any]],
    out_filename: str,
    description: str,
    argv: list[str] | None = None,
) -> int:
    """Execute standard decoder CLI with --data-dir, --out-dir, --log-dir, and --offline-synthetic."""
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument("--data-dir", type=Path, default=None)
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--log-dir", type=Path, default=None)
    ap.add_argument("--offline-synthetic", action="store_true")
    args = ap.parse_args(argv)

    paths = resolve_paths(data_dir=args.data_dir)
    if not args.offline_synthetic:
        banks, missing = load_prg_banks(paths, bank_names)
        if missing:
            payload = missing_media_payload(paths.corpus_root, missing, "Extracted .prg bank images missing; pass --data-dir or --offline-synthetic.")
            write_json_log(args.log_dir, stem, payload)
            print(json.dumps(payload, indent=2))
            return 2
        result = decode_fn(banks)
        out_dir = Path(args.out_dir).resolve() if args.out_dir else (paths.work_dir / "decoded_tables").resolve()
        out_path = out_dir / out_filename
        write_json(out_path, result)
        summary = {**result["summary"], "schemaVersion": 2, "gameId": GAME_ID, "mode": "live", "outFile": str(out_path), "generatedAtUtc": utc_now_iso()}
        write_json_log(args.log_dir, stem, summary)
        print(json.dumps(summary, indent=2))
        return 0 if summary["isPassed"] and summary["unresolvedFieldCount"] == 0 else 1

    banks = synth_fn()
    result = decode_fn(banks)
    with tempfile.TemporaryDirectory(prefix=f"{stem}_") as tmp:
        out_dir = Path(args.out_dir).resolve() if args.out_dir else Path(tmp)
        out_path = out_dir / out_filename
        write_json(out_path, result)
        summary = {**result["summary"], "schemaVersion": 2, "gameId": GAME_ID, "mode": "offline-synthetic", "outFile": str(out_path), "generatedAtUtc": utc_now_iso()}
        write_json_log(args.log_dir, stem, summary)
        print(json.dumps(summary, indent=2))
        return 0 if summary["isPassed"] and summary["unresolvedFieldCount"] == 0 else 1


def check_spec_spokes(dev_dir: Path) -> tuple[bool, list[str], dict[str, int]]:
    """Verify all 4 Dev/docs/specifications/*.md spokes exist, have >=20 lines, and pass strict clean-room rules."""
    specs_dir = dev_dir / "docs" / "specifications"
    issues: list[str] = []
    line_counts: dict[str, int] = {}
    for name in SPEC_SPOKES:
        fp = specs_dir / name
        if not fp.is_file():
            issues.append(f"missing:{name}")
            continue
        raw = fp.read_bytes()
        lines = raw.decode("utf-8", errors="replace").splitlines()
        line_counts[name] = len(lines)
        if len(lines) < 20:
            issues.append(f"short:{name}:{len(lines)}")
        errs = validate_cleanroom_bytes(f"Dev/docs/specifications/{name}", raw, strict=True)
        issues.extend(errs)
    return not issues, issues, line_counts


def _build_all_synthetic() -> dict[str, bytes]:
    from decode_codec_and_audio import populate_synthetic_codec
    from decode_guards_and_weapons import populate_synthetic_guards
    from decode_rooms_and_metatiles import populate_synthetic_rooms

    banks = make_blank_banks()
    populate_synthetic_rooms(banks)
    populate_synthetic_guards(banks)
    populate_synthetic_codec(banks)
    return {k: bytes(v) for k, v in banks.items()}


def _run_orchestration(banks: dict[str, bytes], paths: TrackPaths, out_dir: Path, write_spec_cov: bool, cov_dest: Path, mode: str) -> dict[str, Any]:
    from decode_codec_and_audio import decode_codec_and_audio
    from decode_guards_and_weapons import decode_guards_and_weapons
    from decode_rooms_and_metatiles import decode_rooms_and_metatiles

    rooms = decode_rooms_and_metatiles(banks)
    guards = decode_guards_and_weapons(banks)
    codec = decode_codec_and_audio(banks)
    write_json(out_dir / "rooms_metatiles_chr.json", rooms)
    write_json(out_dir / "guards_weapons_passwords.json", guards)
    write_json(out_dir / "codec_and_audio.json", codec)

    spokes_ok, spoke_issues, spoke_lines = check_spec_spokes(paths.dev_dir)
    base_cov = validate_schemas(paths.schemas_dir)
    checks = [
        {"name": "rooms_metatiles_and_chr_tables", "isPassed": rooms["summary"]["isPassed"] and rooms["summary"]["unresolvedFieldCount"] == 0, "detail": f"rooms={rooms['summary']['roomCount']}, chr={rooms['summary']['chrHeaderCount']}, unresolved={rooms['summary']['unresolvedFieldCount']}"},
        {"name": "guards_weapons_and_password_tables", "isPassed": guards["summary"]["isPassed"] and guards["summary"]["unresolvedFieldCount"] == 0, "detail": f"patrols={guards['summary']['patrolPointerCount']}, dialogs={guards['summary']['dialogPointerCount']}, spawns={guards['summary']['roomSpawnCount']}, unresolved={guards['summary']['unresolvedFieldCount']}"},
        {"name": "codec_and_bank06_audio_tables", "isPassed": codec["summary"]["isPassed"] and codec["summary"]["unresolvedFieldCount"] == 0, "detail": f"calls={codec['summary']['totalCallEntries']}, msgs={codec['summary']['uniqueMessageIdCount']}, snd={codec['summary']['soundDescriptorCount']}, unresolved={codec['summary']['unresolvedFieldCount']}"},
        {"name": "spec_spokes_cleanroom", "isPassed": spokes_ok, "detail": f"spokes={len(spoke_lines)}/{len(SPEC_SPOKES)}, issues={spoke_issues[:3]}"},
        {"name": "schema_type_coverage", "isPassed": bool(base_cov["isPassed"]), "detail": f"funcs={base_cov['namedFunctionCount']}/{base_cov['totalFunctionCount']}, globals={base_cov['mappedGlobalCount']}/{base_cov['totalGlobalCount']}, structs={base_cov['definedStructCount']}, enums={base_cov['definedEnumCount']}"},
    ]
    unresolved = rooms["summary"]["unresolvedFieldCount"] + guards["summary"]["unresolvedFieldCount"] + codec["summary"]["unresolvedFieldCount"]
    passed_n = sum(1 for c in checks if c["isPassed"])
    all_ok = bool(base_cov["isPassed"]) and unresolved == 0 and passed_n == len(checks)
    spec_cov = {
        **base_cov,
        "isPassed": all_ok,
        "unresolvedFieldCount": unresolved,
        "assertionsPassedCount": passed_n,
        "assertionsTotalCount": len(checks),
        "checks": checks,
        "notes": f"Verified all 3 ROM table decoders and 4 clean-room specification spokes with unresolvedFieldCount={unresolved}.",
    }
    if write_spec_cov:
        write_json(cov_dest, spec_cov)
    summary = {
        "schemaVersion": 2, "gameId": GAME_ID, "mode": mode, "isPassed": all_ok,
        "unresolvedFieldCount": unresolved, "assertionsPassedCount": passed_n, "assertionsTotalCount": len(checks),
        "checks": checks, "specCoverageWritten": bool(write_spec_cov),
        "specCoverageFile": cov_dest.name if write_spec_cov else None, "generatedAtUtc": utc_now_iso(),
    }
    write_json(out_dir / "all_bank_tables_summary.json", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    """Orchestrate all 3 ROM bank table decoders, check spec spokes, and optionally write spec_coverage.json."""
    ap = argparse.ArgumentParser(description="Orchestrate all PRG table decoders and verify specification spokes.")
    ap.add_argument("--data-dir", type=Path, default=None)
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--log-dir", type=Path, default=None)
    ap.add_argument("--offline-synthetic", action="store_true")
    ap.add_argument("--write-spec-coverage", action="store_true")
    args = ap.parse_args(argv)

    paths = resolve_paths(data_dir=args.data_dir)
    if args.offline_synthetic:
        banks = _build_all_synthetic()
        with tempfile.TemporaryDirectory(prefix="nes_dec_all_") as tmp:
            out_dir = Path(args.out_dir).resolve() if args.out_dir else Path(tmp)
            cov_dest = (Path(args.out_dir).resolve() if args.out_dir else out_dir) / "spec_coverage.json"
            summary = _run_orchestration(banks, paths, out_dir, args.write_spec_coverage, cov_dest, "offline-synthetic")
            write_json_log(args.log_dir, "decode_all_bank_tables", summary)
            print(json.dumps(summary, indent=2))
            return 0 if summary["isPassed"] else 1

    banks, missing = load_prg_banks(paths, ALL_BANK_NAMES)
    if missing:
        payload = missing_media_payload(paths.corpus_root, missing, "Extracted .prg bank images missing; pass --data-dir or --offline-synthetic.")
        write_json_log(args.log_dir, "decode_all_bank_tables", payload)
        print(json.dumps(payload, indent=2))
        return 2
    out_dir = Path(args.out_dir).resolve() if args.out_dir else (paths.work_dir / "decoded_tables").resolve()
    cov_dest = (Path(args.out_dir).resolve() / "spec_coverage.json") if args.out_dir else (paths.schemas_dir / "spec_coverage.json")
    summary = _run_orchestration(banks, paths, out_dir, args.write_spec_coverage, cov_dest, "live")
    write_json_log(args.log_dir, "decode_all_bank_tables", summary)
    print(json.dumps(summary, indent=2))
    return 0 if summary["isPassed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
