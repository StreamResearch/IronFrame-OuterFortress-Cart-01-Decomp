# @module: IronFrame.Dev.scripts.decode_rooms_and_metatiles
# @purpose: Clean-room decoder for BANK_05 rooms, BANK_04 metatiles/attrs/adjacency, BANK_00..03 CHR headers, and $FD00/$FE00 metadata
# @depends-on: sys, pathlib, typing, decode_all_bank_tables, nes_cli_common
# @exports: REQUIRED_BANKS, populate_synthetic_rooms, decode_rooms_and_metatiles, main

from __future__ import annotations

import struct
import sys
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from decode_all_bank_tables import (  # noqa: E402
    in_bank,
    make_blank_banks,
    run_decoder_cli,
    u16_be,
    u16_le,
)
from nes_cli_common import GAME_ID, crc32_hex, utc_now_iso  # noqa: E402

REQUIRED_BANKS = (
    "BANK_00.prg", "BANK_01.prg", "BANK_02.prg", "BANK_03.prg",
    "BANK_04.prg", "BANK_05.prg", "PRG_FIXED_07.prg",
)
_CHR_COUNTS = ((0, 18, True), (1, 27, True), (2, 3, False), (3, 3, False))


def populate_synthetic_rooms(banks: dict[str, bytearray]) -> None:
    """Populate deterministic synthetic room, metatile, transition, CHR, and metadata tables."""
    b4, b5, b7 = banks["BANK_04.prg"], banks["BANK_05.prg"], banks["PRG_FIXED_07.prg"]
    for i in range(256):
        r_addr = 0x8201 + (i % 165) * 48
        struct.pack_into("<H", b5, 0x0001 + i * 2, r_addr)
        b5[r_addr - 0x8000:r_addr - 0x8000 + 48] = bytes((j + i) & 0x3F for j in range(48))
        b7[0x3D00 + i] = i % 27
        b7[0x3E00 + i] = ((i % 6) << 4) | ((i % 2) << 2) | (i & 1)
        adj_addr = 0x8D30 + (i % 235) * 8
        tbl = 0x0B30 if i < 128 else 0x0C30
        struct.pack_into("<H", b4, tbl + (i & 0x7F) * 2, adj_addr)
        b4[adj_addr - 0x8000:adj_addr - 0x8000 + 8] = bytes([i & 0xFF, 0xFF, 0xFF, (i + 1) & 0xFF, 0xFF, 0xFF, 0xFF, 0xFF])
    for i in range(6):
        m_addr, a_addr = 0x90AC + i * 32, 0x90BC + i * 32
        struct.pack_into("<H", b4, 0x0003 + i * 2, m_addr)
        struct.pack_into("<H", b4, 0x000F + i * 2, a_addr)
        b4[m_addr - 0x8000:a_addr - 0x8000] = bytes([i] * 16)
        b4[a_addr - 0x8000] = i
    for i in range(18):
        b4[0x0A8E + i], b4[0x0AA0 + i] = i, (i + 0x40) & 0xFF
    for i in range(8):
        b4[0x0AB2 + i] = 0x10 + i
        struct.pack_into("<H", b4, 0x0ABA + i * 2, 0x8ACA + i * 2)
    for i in range(17):
        b4[0x0ADC + i] = 0xEE + i
        struct.pack_into("<H", b4, 0x0AED + i * 2, 0x8B0F + (i % 10) * 3)
    for b_idx, cnt, has_term in _CHR_COUNTS:
        bk = banks[f"BANK_{b_idx:02d}.prg"]
        cursor = 0x83A6 if b_idx == 0 else (0x8056 if b_idx == 1 else (0x8007 if b_idx == 2 else 0x8106))
        for i in range(cnt):
            struct.pack_into("<H", bk, 1 + i * 2, cursor)
            struct.pack_into(">HH", bk, cursor - 0x8000, 0x1000 if b_idx < 2 else 0x0000, 16)
            bk[cursor - 0x8000 + 4:cursor - 0x8000 + 20] = bytes([(i + b_idx) & 0xFF] * 16)
            cursor += 20
        if has_term:
            struct.pack_into("<H", bk, 1 + cnt * 2, 0xFFFF)


def _synth_rooms() -> dict[str, bytes]:
    banks = make_blank_banks()
    populate_synthetic_rooms(banks)
    return {k: bytes(v) for k, v in banks.items()}


def decode_rooms_and_metatiles(banks: dict[str, bytes]) -> dict[str, Any]:
    """Decode rooms, metatiles, attributes, adjacency, transitions, CHR headers, and room metadata."""
    b4, b5, b7 = banks["BANK_04.prg"], banks["BANK_05.prg"], banks["PRG_FIXED_07.prg"]
    unresolved = 0

    rooms: list[dict[str, Any]] = []
    for r in range(256):
        ptr = u16_le(b5, 0x8000, 0x8001 + r * 2)
        ok = in_bank(ptr) and (ptr + 48) <= 0xC000
        if not ok:
            unresolved += 1
        grid = b5[ptr - 0x8000:ptr - 0x8000 + 48] if ok else b""
        rooms.append({"roomId": r, "ptrHex": f"0x{ptr:04x}", "layoutBytes": len(grid), "uniqueTileCount": len(set(grid)), "crc32Hex": crc32_hex(grid), "inBounds": ok})

    m_ptrs = [u16_le(b4, 0x8000, 0x8003 + i * 2) for i in range(6)]
    a_ptrs = [u16_le(b4, 0x8000, 0x800F + i * 2) for i in range(6)]
    tilesets: list[dict[str, Any]] = []
    for i in range(6):
        mp, ap = m_ptrs[i], a_ptrs[i]
        m_len = ap - mp
        n_meta = m_len // 16 if m_len > 0 else 0
        a_len = (m_ptrs[i + 1] - ap) if i < 5 else n_meta
        ok = in_bank(mp) and in_bank(ap) and ap > mp and (m_len % 16 == 0) and (ap + a_len) <= 0xC000
        if not ok:
            unresolved += 1
        tilesets.append({"tilesetId": i, "metatilePtrHex": f"0x{mp:04x}", "attrPtrHex": f"0x{ap:04x}", "metatileCount": n_meta, "metatileBytes": m_len, "attrBytes": a_len, "inBounds": ok})

    door_returns = [{"roomId": b4[0x0A8E + i], "destRoomId": b4[0x0AA0 + i]} for i in range(18)]
    elevators: list[dict[str, Any]] = []
    for i in range(8):
        ep = u16_le(b4, 0x8000, 0x8ABA + i * 2)
        ok = in_bank(ep)
        if not ok:
            unresolved += 1
        elevators.append({"roomId": b4[0x0AB2 + i], "tablePtrHex": f"0x{ep:04x}", "inBounds": ok})
    special_warps: list[dict[str, Any]] = []
    for i in range(17):
        sp = u16_le(b4, 0x8000, 0x8AED + i * 2)
        ok = in_bank(sp) and (sp + 3) <= 0xC000
        if not ok:
            unresolved += 1
        special_warps.append({"roomId": b4[0x0ADC + i], "tablePtrHex": f"0x{sp:04x}", "tupleBytes": list(b4[sp - 0x8000:sp - 0x8000 + 3]) if ok else [], "inBounds": ok})

    adjacency: list[dict[str, Any]] = []
    for r in range(256):
        tbl_addr = (0x8B30 if r < 128 else 0x8C30) + (r & 0x7F) * 2
        ap = u16_le(b4, 0x8000, tbl_addr)
        ok = in_bank(ap) and (ap + 8) <= 0xC000
        if not ok:
            unresolved += 1
        vec = list(b4[ap - 0x8000:ap - 0x8000 + 8]) if ok else []
        adjacency.append({"roomId": r, "ptrHex": f"0x{ap:04x}", "neighbors": vec, "inBounds": ok})

    chr_headers: list[dict[str, Any]] = []
    for b_idx, cnt, has_term in _CHR_COUNTS:
        bk = banks[f"BANK_{b_idx:02d}.prg"]
        if has_term and u16_le(bk, 0x8000, 0x8001 + cnt * 2) != 0xFFFF:
            unresolved += 1
        for i in range(cnt):
            cp = u16_le(bk, 0x8000, 0x8001 + i * 2)
            ok = in_bank(cp) and (cp + 4) <= 0xC000
            ppu_addr = u16_be(bk, 0x8000, cp) if ok else 0
            length = u16_be(bk, 0x8000, cp + 2) if ok else 0
            ok = ok and (cp + 4 + length) <= 0xC000
            if not ok:
                unresolved += 1
            payload = bk[cp - 0x8000 + 4:cp - 0x8000 + 4 + length] if ok else b""
            chr_headers.append({"bank": f"BANK_{b_idx:02d}", "index": i, "ptrHex": f"0x{cp:04x}", "ppuAddrHex": f"0x{ppu_addr:04x}", "byteLength": length, "crc32Hex": crc32_hex(payload), "inBounds": ok})

    room_meta: list[dict[str, Any]] = []
    for r in range(256):
        fd, fe = b7[0x3D00 + r], b7[0x3E00 + r]
        ts = (fe >> 4) & 0x07
        if ts >= 6:
            unresolved += 1
        room_meta.append({"roomId": r, "fd00": fd, "fe00": fe, "paletteIndex": fd & 0x1F, "chrSubVariant": (fd >> 6) & 0x03, "chrBankLo": fe & 0x03, "chrBankSelect": (fe >> 2) & 0x03, "tilesetIndex": ts})

    return {
        "schemaVersion": 2,
        "gameId": GAME_ID,
        "generatedAtUtc": utc_now_iso(),
        "summary": {
            "isPassed": unresolved == 0,
            "unresolvedFieldCount": unresolved,
            "roomCount": len(rooms),
            "uniqueRoomLayoutCount": len({x["ptrHex"] for x in rooms}),
            "tilesetCount": len(tilesets),
            "doorReturnCount": len(door_returns),
            "elevatorRoomCount": len(elevators),
            "specialWarpCount": len(special_warps),
            "adjacencyCount": len(adjacency),
            "uniqueAdjacencyCount": len({x["ptrHex"] for x in adjacency}),
            "chrHeaderCount": len(chr_headers),
            "roomMetadataCount": len(room_meta),
        },
        "rooms": rooms,
        "tilesets": tilesets,
        "doorReturns": door_returns,
        "elevators": elevators,
        "specialWarps": special_warps,
        "adjacency": adjacency,
        "chrUploadHeaders": chr_headers,
        "roomMetadata": room_meta,
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for rooms, metatiles, adjacency, CHR, and room metadata decoder."""
    return run_decoder_cli(
        "decode_rooms_and_metatiles", REQUIRED_BANKS, _synth_rooms,
        decode_rooms_and_metatiles, "rooms_metatiles_chr.json",
        "Decode BANK_05 rooms, BANK_04 metatiles/adjacency, BANK_00..03 CHR headers, and $FD00/$FE00 metadata.", argv,
    )


if __name__ == "__main__":
    raise SystemExit(main())
