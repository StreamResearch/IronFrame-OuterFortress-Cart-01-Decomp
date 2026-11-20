# @module: IronFrame.Dev.scripts.nes_unrom_unpack
# @purpose: Clean-room iNES Mapper 2 (UNROM) BYO-ROM validator, bank unpacker, and offline synthetic generator
# @depends-on: argparse, hashlib, json, sys, tempfile, pathlib, typing, nes_6502_cfg, nes_cli_common
# @exports: build_synthetic_unrom_rom, load_required_rom_spec, unpack_unrom_bytes, main

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from nes_6502_cfg import (  # noqa: E402
    BANK_SIZE, format_disasm, parse_ines, propagate_bank_calls, read_u16, to_intervals, trace_smart,
)
from nes_cli_common import (  # noqa: E402
    GAME_ID, crc32_hex, missing_media_payload, resolve_paths, sha256_bytes, utc_now_iso, write_json_log,
)

INES2_HEADER = bytes.fromhex("4e45531a080021082000000700000001")
DEFAULT_ROM_SIZE = 131088
DEFAULT_ROM_SHA256 = "79095355436222161cb3841ff9b5c7a572e77af11461935e433bd6e8dfd0f164"
DEFAULT_ROM_CRC32 = "25ba3d04"


def build_synthetic_unrom_rom(out_path: Path | None = None) -> bytes:
    """Build a minimal clean-room Mapper 2 (8x16 KiB PRG) synthetic NES 2.0 test ROM."""
    banks = [bytearray([0xFF] * BANK_SIZE) for _ in range(8)]
    for b in range(7):
        banks[b][0:4] = bytes((b, 0xA9, b, 0x60))
    fixed = banks[7]
    fixed[0x0000:0x0008] = bytes((0x20, 0x10, 0xC0, 0x4C, 0x00, 0xC0, 0x40, 0x40))
    fixed[0x0010:0x001A] = bytes((0x20, 0x32, 0xC9, 0x20, 0x01, 0x80, 0x20, 0x58, 0xC9, 0x60))
    fixed[0x0932:0x0937] = bytes((0xA0, 0x00, 0x4C, 0x4C, 0xC9))
    fixed[0x094C:0x0958] = bytes((0xAD, 0x00, 0x80, 0x85, 0x27, 0xB9, 0xD0, 0xFF, 0x99, 0xD0, 0xFF, 0x60))
    fixed[0x0958:0x0961] = bytes((0xA4, 0x27, 0xB9, 0xD0, 0xFF, 0x99, 0xD0, 0xFF, 0x60))
    fixed[0x3FD0:0x3FD8] = bytes(range(8))
    fixed[0x3FFA:0x4000] = bytes((0x06, 0xC0, 0x00, 0xC0, 0x07, 0xC0))
    rom_bytes = INES2_HEADER + b"".join(bytes(b) for b in banks)
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(rom_bytes)
    return rom_bytes


def load_required_rom_spec(schemas_dir: Path) -> tuple[int, str, str]:
    """Read expected BYO ROM size, sha256Hex, and crc32Hex from standalone_integrity.json."""
    integ_path = schemas_dir / "standalone_integrity.json"
    if not integ_path.is_file():
        return DEFAULT_ROM_SIZE, DEFAULT_ROM_SHA256, DEFAULT_ROM_CRC32
    data = json.loads(integ_path.read_text(encoding="utf-8"))
    req = data.get("requiredRomChecksums")
    item = req[0] if isinstance(req, list) and req else (req if isinstance(req, dict) else {})
    size = int(item.get("fileSizeBytes", item.get("expectedSizeBytes", DEFAULT_ROM_SIZE)))
    sha = str(item.get("sha256Hex", item.get("expectedSha256", DEFAULT_ROM_SHA256))).lower()
    crc = str(item.get("crc32Hex", item.get("expectedCrc32", DEFAULT_ROM_CRC32))).lower()
    return size, sha, crc


def _find_rom(rom_arg: Path | None, data_dir: Path | None, project_root: Path, corpus_root: Path, expected_sha: str) -> tuple[Path | None, list[Path]]:
    if rom_arg is not None:
        cand = Path(rom_arg).resolve()
        return (cand if cand.is_file() else None), [cand.parent]
    dirs = (
        [data_dir / "data" / "rom", data_dir / "rom", data_dir / "standalone", data_dir]
        if data_dir is not None else
        [project_root / "data" / "rom", corpus_root / "data" / "rom", corpus_root / "rom", corpus_root / "standalone", corpus_root]
    )
    seen: list[Path] = []
    cands: list[Path] = []
    for d in dirs:
        rd = d.resolve()
        if rd not in seen:
            seen.append(rd)
            if rd.is_dir():
                cands.extend(sorted(rd.glob("*.nes")))
    for p in cands:
        if sha256_bytes(p.read_bytes()) == expected_sha:
            return p, seen
    return (cands[0] if cands else None), seen


def _assert_safe_out_dir(out_dir: Path, project_root: Path) -> None:
    sealed = (project_root / "Corpus" / "standalone").resolve()
    resolved = out_dir.resolve()
    if resolved == sealed or sealed in resolved.parents:
        raise ValueError(f"Refusing to mutate sealed standalone directory: {resolved}")


def unpack_unrom_bytes(rom_bytes: bytes, rom_name: str, out_dir: Path | None, write_files: bool = True) -> dict[str, Any]:
    """Parse Mapper 2 PRG banks, trace 6502 CFG, and write 8 .prg + 8 .s + nes_bank_layout.json."""
    parsed = parse_ines(rom_bytes)
    prg, num_banks = parsed["prg_data"], parsed["prg_banks"]
    if parsed["mapper"] != 2 or num_banks < 2:
        raise ValueError(f"Expected Mapper 2 with >=2 PRG banks, got mapper={parsed['mapper']} banks={num_banks}")
    fixed_bank = prg[(num_banks - 1) * BANK_SIZE:num_banks * BANK_SIZE]
    fixed_mem = bytearray(prg[0:BANK_SIZE] + fixed_bank)
    nmi, reset, irq = read_u16(fixed_mem, 0xFFFA), read_u16(fixed_mem, 0xFFFC), read_u16(fixed_mem, 0xFFFE)
    insns, code_b, funcs = trace_smart(fixed_mem, [nmi, reset, irq], 0xC000, 0xFFFA)
    cross_bank = propagate_bank_calls(fixed_mem, funcs)

    programs_layout: dict[str, Any] = {
        "PRG_FIXED_07.prg": {
            "bank_index": num_banks - 1, "window": "0xc000-0x10000", "code_bytes": len(code_b),
            "entry_points": sorted(funcs), "data_intervals": to_intervals(set(range(0xC000, 0xFFFA)) - code_b, 0xC000, 0xFFFA),
        }
    }
    disasms: dict[str, str] = {"PRG_FIXED_07.s": format_disasm(fixed_mem, 0xC000, 0xFFFA, insns, funcs)}
    prgs: dict[str, bytes] = {"PRG_FIXED_07.prg": bytes(fixed_mem)}

    for b in range(num_banks - 1):
        bmem = bytearray(prg[b * BANK_SIZE:(b + 1) * BANK_SIZE] + fixed_bank)
        seeds = sorted(cross_bank.get(b, set()))
        sw_insns, sw_code, sw_funcs = trace_smart(bmem, seeds, 0x8000, 0xC000) if seeds else (set(), set(), set())
        pname = f"BANK_{b:02d}.prg"
        prgs[pname] = bytes(bmem)
        disasms[f"BANK_{b:02d}.s"] = format_disasm(bmem, 0x8000, 0xC000, sw_insns, sw_funcs)
        programs_layout[pname] = {
            "bank_index": b, "window": "0x8000-0xc000", "code_bytes": len(sw_code),
            "entry_points": sorted(sw_funcs), "data_intervals": to_intervals(set(range(0x8000, 0xC000)) - sw_code, 0x8000, 0xC000),
        }

    layout = {
        "rom_name": rom_name, "rom_bytes": len(rom_bytes),
        "crc32": crc32_hex(rom_bytes), "md5": hashlib.md5(rom_bytes).hexdigest().lower(),
        "sha1": hashlib.sha1(rom_bytes).hexdigest().lower(), "sha256": sha256_bytes(rom_bytes),
        "mapper": parsed["mapper"], "prg_banks": num_banks, "chr_banks": parsed["chr_banks"],
        "mirroring": parsed["mirroring"],
        "vectors": {"nmi": f"0x{nmi:04x}", "reset": f"0x{reset:04x}", "irq": f"0x{irq:04x}"},
        "programs": programs_layout,
    }
    written: list[str] = []
    if write_files and out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        for name, blob in prgs.items():
            (out_dir / name).write_bytes(blob)
            written.append(name)
        for name, txt in disasms.items():
            (out_dir / name).write_text(txt, encoding="utf-8")
            written.append(name)
        (out_dir / "nes_bank_layout.json").write_text(json.dumps(layout, indent=2) + "\n", encoding="utf-8")
        written.append("nes_bank_layout.json")
    return {"layout": layout, "written_files": sorted(written)}


def _emit(log_dir: Path | None, payload: dict[str, Any], code: int) -> int:
    write_json_log(log_dir, "nes_unrom_unpack", payload)
    print(json.dumps(payload, indent=2))
    return code


def main() -> int:
    ap = argparse.ArgumentParser(description="Clean-room BYO NES UNROM unpacker and verifier.")
    ap.add_argument("--rom", type=Path, default=None)
    ap.add_argument("--data-dir", type=Path, default=None)
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--log-dir", type=Path, default=None)
    ap.add_argument("--offline-synthetic", action="store_true")
    ap.add_argument("--verify-only", action="store_true")
    args = ap.parse_args()

    paths = resolve_paths(data_dir=args.data_dir)
    if args.out_dir is not None:
        _assert_safe_out_dir(args.out_dir, paths.project_root)

    if args.offline_synthetic:
        with tempfile.TemporaryDirectory(prefix="nes_unrom_synth_") as tmp:
            troot = Path(tmp)
            rom_path = troot / "synthetic_unrom.nes"
            rom_bytes = build_synthetic_unrom_rom(rom_path)
            out_dir = Path(args.out_dir).resolve() if args.out_dir else (troot / "unpacked")
            res = unpack_unrom_bytes(rom_bytes, rom_path.name, out_dir, write_files=not args.verify_only)
            lay = res["layout"]
            payload = {
                "schemaVersion": 2, "gameId": GAME_ID, "generatedAtUtc": utc_now_iso(), "isPassed": True,
                "mode": "offline-synthetic", "outDir": str(out_dir), "fileSizeBytes": len(rom_bytes),
                "crc32Hex": lay["crc32"], "sha256Hex": lay["sha256"], "prgBankCount": lay["prg_banks"],
                "extractedFileCount": len(res["written_files"]),
                "codeByteCount": sum(v["code_bytes"] for v in lay["programs"].values()),
                "seedFunctionCount": sum(len(v["entry_points"]) for v in lay["programs"].values()),
            }
            return _emit(args.log_dir, payload, 0)

    exp_size, exp_sha, exp_crc = load_required_rom_spec(paths.schemas_dir)
    rom_path, searched = _find_rom(args.rom, args.data_dir, paths.project_root, paths.corpus_root, exp_sha)
    if rom_path is None:
        base = args.data_dir or paths.corpus_root
        return _emit(args.log_dir, missing_media_payload(base, ["data/rom/*.nes"], f"No .nes ROM found in {[str(s) for s in searched]}"), 2)

    rom_bytes = rom_path.read_bytes()
    act_sha, act_crc = sha256_bytes(rom_bytes), crc32_hex(rom_bytes)
    if len(rom_bytes) != exp_size or act_sha != exp_sha or (exp_crc and act_crc != exp_crc):
        payload = {
            "schemaVersion": 2, "gameId": GAME_ID, "generatedAtUtc": utc_now_iso(), "isPassed": False,
            "errorCode": "CHECKSUM_MISMATCH", "romPath": str(rom_path),
            "expectedSizeBytes": exp_size, "actualSizeBytes": len(rom_bytes),
            "expectedSha256": exp_sha, "actualSha256": act_sha, "expectedCrc32": exp_crc, "actualCrc32": act_crc,
        }
        return _emit(args.log_dir, payload, 1)

    out_dir = Path(args.out_dir).resolve() if args.out_dir else (paths.work_dir / "unpacked").resolve()
    _assert_safe_out_dir(out_dir, paths.project_root)
    res = unpack_unrom_bytes(rom_bytes, rom_path.name, out_dir, write_files=not args.verify_only)
    lay = res["layout"]
    payload = {
        "schemaVersion": 2, "gameId": GAME_ID, "generatedAtUtc": utc_now_iso(), "isPassed": True,
        "mode": "verify-only" if args.verify_only else "unpack", "romPath": str(rom_path), "outDir": str(out_dir),
        "fileSizeBytes": len(rom_bytes), "crc32Hex": lay["crc32"], "md5Hex": lay["md5"],
        "sha1Hex": lay["sha1"], "sha256Hex": lay["sha256"], "mapper": lay["mapper"],
        "prgBankCount": lay["prg_banks"], "chrBankCount": lay["chr_banks"],
        "extractedFileCount": len(res["written_files"]),
        "codeByteCount": sum(v["code_bytes"] for v in lay["programs"].values()),
        "seedFunctionCount": sum(len(v["entry_points"]) for v in lay["programs"].values()),
    }
    return _emit(args.log_dir, payload, 0)


if __name__ == "__main__":
    raise SystemExit(main())
