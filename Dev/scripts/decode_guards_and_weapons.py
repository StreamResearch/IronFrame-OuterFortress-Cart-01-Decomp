# @module: IronFrame.Dev.scripts.decode_guards_and_weapons
# @purpose: Clean-room decoder for patrol scripts, dialog pointer offsets/lengths, room spawns, weapon/explosion tables, passwords, and rank HP
# @depends-on: struct, sys, pathlib, typing, decode_all_bank_tables, nes_cli_common
# @exports: REQUIRED_BANKS, populate_synthetic_guards, decode_guards_and_weapons, main

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
    s8,
    u16_le,
)
from nes_cli_common import GAME_ID, crc32_hex, utc_now_iso  # noqa: E402

REQUIRED_BANKS = (
    "BANK_00.prg", "BANK_01.prg", "BANK_03.prg", "BANK_04.prg",
    "BANK_05.prg", "BANK_06.prg", "PRG_FIXED_07.prg",
)


def populate_synthetic_guards(banks: dict[str, bytearray]) -> None:
    """Populate deterministic synthetic patrol, dialog-ptr, spawn, weapon, password, and rank tables."""
    b0, b1, b3 = banks["BANK_00.prg"], banks["BANK_01.prg"], banks["BANK_03.prg"]
    b4, b5, b6, b7 = banks["BANK_04.prg"], banks["BANK_05.prg"], banks["BANK_06.prg"], banks["PRG_FIXED_07.prg"]

    for i in range(123):
        p_addr = 0x813E + (i % 96) * 4
        struct.pack_into("<H", b0, 0x0048 + i * 2, p_addr)
        b0[p_addr - 0x8000:p_addr - 0x8000 + 4] = bytes([0x10, 0x81, 0x11, 0xFF])
    for i in range(160):
        slot_off = (0x3DFA + i * 2) if i < 128 else (0x3EFA + (i - 128) * 2)
        use_b1 = (i % 5) == 0
        t_addr = (0x9372 + i * 4) if use_b1 else (0xA200 + i * 4)
        struct.pack_into("<H", b0, slot_off, t_addr)
        tgt = b1 if use_b1 else b5
        tgt[t_addr - 0x8000:t_addr - 0x8000 + 4] = bytes([0x20, 0xFE, 0x20, 0xFF])

    for i in range(217):
        s_addr = 0x8744 + (i % 85) * 5
        struct.pack_into("<H", b4, 0x0592 + i * 2, s_addr)
        b4[s_addr - 0x8000:s_addr - 0x8000 + 5] = bytes([0x01, i & 0x3F, 0x50, 0x80, 0xFF])

    b6[0x09F0:0x09F4] = bytes([0x00, 0x08, 0x0C, 0x04])
    b6[0x09F4:0x0A14] = bytes(i & 0x0F for i in range(32))
    b6[0x0A14:0x0A1C] = bytes([0x07, 0x0A, 0x07, 0x1A, 0x00, 0x0B, 0x10, 0x0B])
    b6[0x0A1C:0x0B1C] = bytes([0xFE if (i & 1) else 0x01 for i in range(256)])
    b6[0x0B1C:0x0B24] = bytes([0x00, 0x28, 0x31, 0x33, 0x29, 0x28, 0x32, 0x2D])
    b6[0x0B24:0x0B28] = bytes([0x34, 0x35, 0x36, 0x00])
    b6[0x0B28:0x0B68] = bytes([0xF8 if (i & 1) else 0x10 for i in range(64)])

    b3[0x39DF:0x39E8] = bytes([0x90] * 8 + [0xFF])
    b3[0x3AAD:0x3AB8] = bytes([0x21, 0x6C] + [0x45] * 8 + [0xFF])
    for i in range(57):
        struct.pack_into("<H", b3, 0x3BB3 + i * 2, 0x20AA + i * 2)
    b3[0x3DC0:0x3DC2] = bytes([0xC2, 0xBD])
    b3[0x3DC2:0x3DE2] = bytes(range(0x31, 0x51))
    b3[0x3DE2:0x3DF6] = bytes([0xA8, 0x00, 0xAD, 0x00, 0xB2, 0x00, 0xB7, 0x00, 0xBC, 0x00, 0x8A, 0x22, 0x91, 0x22, 0xCA, 0x22, 0xD1, 0x22, 0x0A, 0x23])

    b7[0x17B8:0x17CE] = bytes([0x00, 0x08, 0xF1, 0x40, 0x74, 0xA5, 0x80, 0x88, 0x5C, 0x68, 0x90, 0x60, 0x80, 0x90, 0xE0, 0x80, 0x28, 0x80, 5, 8, 12, 15])
    for i in range(8):
        struct.pack_into("<H", b7, 0x2E6A + i * 2, 0xEE57 + i * 4)


def _synth_guards() -> dict[str, bytes]:
    banks = make_blank_banks()
    populate_synthetic_guards(banks)
    return {k: bytes(v) for k, v in banks.items()}


def decode_guards_and_weapons(banks: dict[str, bytes]) -> dict[str, Any]:
    """Decode patrol scripts, dialog pointer offsets/lengths, spawns, weapon tables, passwords, and rank HP."""
    b0, b1, b3 = banks["BANK_00.prg"], banks["BANK_01.prg"], banks["BANK_03.prg"]
    b4, b5, b6, b7 = banks["BANK_04.prg"], banks["BANK_05.prg"], banks["BANK_06.prg"], banks["PRG_FIXED_07.prg"]
    unresolved = 0

    first_patrol = u16_le(b0, 0x8000, 0x8048)
    patrol_count = max(0, min(256, (first_patrol - 0x8048) // 2)) if in_bank(first_patrol) and first_patrol > 0x8048 else 0
    if patrol_count == 0:
        unresolved += 1
    patrols: list[dict[str, Any]] = []
    for i in range(patrol_count):
        ptr = u16_le(b0, 0x8000, 0x8048 + i * 2)
        ok = in_bank(ptr)
        off = ptr - 0x8000
        end = b0.find(0xFF, off) if ok else -1
        term_ok = ok and end >= off
        if not term_ok:
            unresolved += 1
        blen = (end - off) if term_ok else 0
        patrols.append({"patrolId": i, "ptrHex": f"0x{ptr:04x}", "byteLength": blen, "stepCount": blen // 2, "isTerminated": term_ok, "inBounds": ok})

    dialogs: list[dict[str, Any]] = []
    for i in range(192):
        addr = 0xBDFA + i * 2
        if addr + 2 > 0xC000:
            break
        ptr = u16_le(b0, 0x8000, addr)
        if i >= 128 and not in_bank(ptr):
            break
        ok_ptr = in_bank(ptr)
        use_b1 = ptr < 0xA000
        tgt = b1 if use_b1 else b5
        off = ptr - 0x8000
        end = tgt.find(0xFF, off) if ok_ptr else -1
        term_ok = ok_ptr and end >= off
        if not term_ok:
            unresolved += 1
        span = tgt[off:end] if term_ok else b""
        dialogs.append({
            "dialogId": i, "table": "$BDFA" if i < 128 else "$BEFA",
            "targetBank": "BANK_01" if use_b1 else "BANK_05", "ptrHex": f"0x{ptr:04x}",
            "byteLength": len(span), "lineBreakCount": span.count(0xFE), "isTerminated": term_ok, "inBounds": ok_ptr,
        })

    spawns: list[dict[str, Any]] = []
    for r in range(217):
        ptr = u16_le(b4, 0x8000, 0x8592 + r * 2)
        ok = in_bank(ptr)
        off = ptr - 0x8000
        hdr = b4[off] if ok else 0xFF
        rec_cnt, pos, term_ok = 0, off + 1, ok
        if ok and not (hdr & 0x80):
            while pos < len(b4) and b4[pos] != 0xFF:
                pos += 3
                rec_cnt += 1
            term_ok = pos < len(b4) and b4[pos] == 0xFF
        if not (ok and term_ok):
            unresolved += 1
        blen = 1 if (hdr & 0x80) else ((pos - off + 1) if term_ok else 0)
        spawns.append({"roomId": r, "ptrHex": f"0x{ptr:04x}", "headerByte": hdr, "recordCount": rec_cnt, "byteLength": blen, "isTerminated": term_ok, "inBounds": ok})

    weapon_tables = {
        "facingDirectionBase": list(b6[0x09F0:0x09F4]),
        "spreadAngleTable": [list(b6[0x09F4 + i * 8:0x09F4 + (i + 1) * 8]) for i in range(4)],
        "projectileSpawnOffsets": [{"facing": i, "dy": s8(b6[0x0A14 + i * 2]), "dx": s8(b6[0x0A15 + i * 2])} for i in range(4)],
        "projectileMotionDxLut": {"addrHex": "0x8a1c", "byteLength": 256, "quadrants": 4, "stepsPerQuadrant": 64, "crc32Hex": crc32_hex(b6[0x0A1C:0x0B1C])},
        "weaponProjectileActorIds": list(b6[0x0B1C:0x0B24]),
        "explosionStageActorIds": list(b6[0x0B24:0x0B28]),
        "weaponHitboxBounds": {"addrHex": "0x8b28", "boundsBytes": [s8(x) for x in b6[0x0B28:0x0B60]], "altLauncherActorIds": list(b6[0x0B60:0x0B68])},
    }

    pwd_slots = [u16_le(b3, 0x8000, 0xBBB3 + i * 2) for i in range(57)]
    if any(a >= 0x3F00 for a in pwd_slots) or b3[0x39E7] != 0xFF or b3[0x3AB7] != 0xFF:
        unresolved += 1
    password_tables = {
        "headerBanner": {"addrHex": "0xb9df", "glyphCount": 8, "totalBytes": 9, "terminated": b3[0x39E7] == 0xFF},
        "errorBanner": {"addrHex": "0xbaad", "ppuAddrHex": f"0x{u16_be_val(b3[0x3AAD], b3[0x3AAE]):04x}", "glyphCount": 8, "totalBytes": 11, "terminated": b3[0x3AB7] == 0xFF},
        "gridVramAddresses": {"addrHex": "0xbbb3", "slotCount": 25, "gridCellCount": 32, "totalEntries": len(pwd_slots), "totalBytes": 114},
        "alphabetLayout": {"addrHex": "0xbdc0", "headerBytes": 2, "alphabetIndexCount": 32, "rowOffsetCount": 5, "rowPpuAddrCount": 5, "totalBytes": 54},
    }

    spawns_fixed = [{"slot": i, "roomId": b7[0x17B8 + i], "posY": b7[0x17BE + i], "posX": b7[0x17C4 + i]} for i in range(6)]
    rank_hp = list(b7[0x17CA:0x17CE])
    wep_jmp = []
    for i in range(8):
        jp = u16_le(b7, 0xC000, 0xEE6A + i * 2)
        ok = in_bank(jp, is_fixed=True)
        if not ok:
            unresolved += 1
        wep_jmp.append({"weaponId": i, "handlerPtrHex": f"0x{jp:04x}", "inBounds": ok})

    return {
        "schemaVersion": 2,
        "gameId": GAME_ID,
        "generatedAtUtc": utc_now_iso(),
        "summary": {
            "isPassed": unresolved == 0,
            "unresolvedFieldCount": unresolved,
            "patrolPointerCount": len(patrols),
            "uniquePatrolScriptCount": len({p["ptrHex"] for p in patrols}),
            "dialogPointerCount": len(dialogs),
            "uniqueDialogPointerCount": len({d["ptrHex"] for d in dialogs}),
            "roomSpawnCount": len(spawns),
            "uniqueRoomSpawnCount": len({s["ptrHex"] for s in spawns}),
            "weaponTableCount": 7,
            "passwordTableCount": 4,
            "fixedSpawnCount": len(spawns_fixed),
            "rankMaxHpValues": rank_hp,
            "weaponJumpCount": len(wep_jmp),
        },
        "patrolScripts": patrols,
        "dialogPointers": dialogs,
        "roomActorSpawns": spawns,
        "weaponTables": weapon_tables,
        "passwordTables": password_tables,
        "fixedSpawnAndRank": {"spawns": spawns_fixed, "rankMaxHp": rank_hp, "weaponJumpTable": wep_jmp},
    }


def u16_be_val(hi: int, lo: int) -> int:
    """Combine high and low byte into a 16-bit big-endian integer."""
    return (hi << 8) | lo


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for patrols, dialog pointers, spawns, weapons, passwords, and rank HP."""
    return run_decoder_cli(
        "decode_guards_and_weapons", REQUIRED_BANKS, _synth_guards,
        decode_guards_and_weapons, "guards_weapons_passwords.json",
        "Decode BANK_00 patrols/dialog offsets, BANK_04 spawns, BANK_06 weapon tables, BANK_03 password layouts, and fixed rank/jump tables.", argv,
    )


if __name__ == "__main__":
    raise SystemExit(main())
