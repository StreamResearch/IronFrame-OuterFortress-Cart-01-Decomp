# @module: IronFrame.Dev.scripts.decode_codec_and_audio
# @purpose: Clean-room decoder for BANK_05 codec freqs/calls, BANK_06 envelopes/periods/audio descriptors, and PRG_FIXED_07 dmc[0]
# @depends-on: struct, sys, pathlib, typing, decode_all_bank_tables, nes_cli_common
# @exports: REQUIRED_BANKS, populate_synthetic_codec, decode_codec_and_audio, main

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
    u16_le,
)
from nes_cli_common import GAME_ID, utc_now_iso  # noqa: E402

REQUIRED_BANKS = ("BANK_00.prg", "BANK_01.prg", "BANK_05.prg", "BANK_06.prg", "PRG_FIXED_07.prg")


def populate_synthetic_codec(banks: dict[str, bytearray]) -> None:
    """Populate deterministic synthetic codec, call, envelope, period, audio descriptor, and DMC[0] tables."""
    b0, b1, b5, b6, b7 = (
        banks["BANK_00.prg"], banks["BANK_01.prg"], banks["BANK_05.prg"],
        banks["BANK_06.prg"], banks["PRG_FIXED_07.prg"],
    )
    b5[0x397C:0x3983] = bytes([0x0D, 0x10, 0x5B, 0x30, 0x4F, 0x55, 0x21])
    b5[0x398A] = 0xFF
    empty_tbl = 0xBF00
    b5[empty_tbl - 0x8000] = 0x00
    cursor = 0xBD63
    for idx in range(74):
        tbl_addr = cursor
        cnt = 1 if idx < 32 else 2
        b5[cursor - 0x8000] = cnt
        cursor += 1
        for k in range(cnt):
            msg_id = (idx + k) % 72 + 2
            b5[cursor - 0x8000] = 0x41 + (k % 6)
            b5[cursor - 0x8000 + 1] = msg_id
            cursor += 2
        struct.pack_into("<H", b5, 0x3B65 + idx * 2, tbl_addr)
    for r in range(74, 255):
        off = (0x3B65 + r * 2) if r < 128 else (0x3C65 + (r - 128) * 2)
        struct.pack_into("<H", b5, off, empty_tbl if r >= 116 else (0xBD63 + (r % 20) * 3))

    for i in range(160):
        slot_off = (0x3DFA + i * 2) if i < 128 else (0x3EFA + (i - 128) * 2)
        if u16_le(b0, 0, slot_off) == 0xFFFF:
            use_b1 = (i % 5) == 0
            t_addr = (0x9372 + i * 4) if use_b1 else (0xA200 + i * 4)
            struct.pack_into("<H", b0, slot_off, t_addr)
            tgt = b1 if use_b1 else b5
            tgt[t_addr - 0x8000:t_addr - 0x8000 + 4] = bytes([0x20, 0x20, 0x20, 0xFF])

    for i in range(5):
        e_addr = 0xAAC2 + i * 16
        struct.pack_into("<H", b6, 0x11EE + i * 2, e_addr)
        b6[e_addr - 0x8000:e_addr - 0x8000 + 6] = bytes([6, 4, 3, 2, 1, 0xFF])
    for i in range(12):
        struct.pack_into("<H", b6, 0x1923 + i * 2, 0x06AE - i * 0x40)
    b6[0x3C15:0x3C18] = bytes([0x10, 0x0A, 0xFF])
    for i in range(1, 133):
        hdr = 0x05 if i < 65 else (0x18 if (i - 65) % 4 == 0 else ((i - 65) % 4))
        b6[0x3C15 + i * 3] = hdr
        struct.pack_into("<H", b6, 0x3C15 + i * 3 + 1, 0x9ABE + i * 4)

    b7[0x3C80:0x3C84] = bytes([0x0E, 0x00, 0xF0, 0x08])


def _synth_codec() -> dict[str, bytes]:
    banks = make_blank_banks()
    populate_synthetic_codec(banks)
    return {k: bytes(v) for k, v in banks.items()}


def _resolve_msg_length(b0: bytes, b1: bytes, b5: bytes, msg_id: int) -> tuple[bool, int]:
    if msg_id >= 160:
        return False, 0
    slot_addr = (0xBDFA + msg_id * 2) if msg_id < 128 else (0xBEFA + (msg_id - 128) * 2)
    ptr = u16_le(b0, 0x8000, slot_addr)
    if not in_bank(ptr):
        return False, 0
    tgt = b1 if ptr < 0xA000 else b5
    off = ptr - 0x8000
    end = tgt.find(0xFF, off)
    return (end >= off), ((end - off) if end >= off else 0)


def decode_codec_and_audio(banks: dict[str, bytes]) -> dict[str, Any]:
    """Decode codec freqs/calls, volume envelopes, 12 note periods, 132 sound descriptors, and dmc[0]."""
    b0, b1, b5, b6, b7 = (
        banks["BANK_00.prg"], banks["BANK_01.prg"], banks["BANK_05.prg"],
        banks["BANK_06.prg"], banks["PRG_FIXED_07.prg"],
    )
    unresolved = 0

    freqs = list(b5[0x397C:0x3983])
    if b5[0x398A] != 0xFF:
        unresolved += 1

    room_calls: list[dict[str, Any]] = []
    total_entries = 0
    unique_ptrs: set[int] = set()
    unique_msgs: set[int] = set()
    for r in range(255):
        tbl_slot = (0xBB65 + r * 2) if r < 128 else (0xBC65 + (r - 128) * 2)
        ptr = u16_le(b5, 0x8000, tbl_slot)
        ok = in_bank(ptr)
        if not ok:
            unresolved += 1
            room_calls.append({"roomId": r, "ptrHex": f"0x{ptr:04x}", "entryCount": 0, "entries": [], "inBounds": False})
            continue
        unique_ptrs.add(ptr)
        off = ptr - 0x8000
        cnt = b5[off]
        entries: list[dict[str, Any]] = []
        for j in range(cnt):
            if off + 1 + j * 2 + 1 >= len(b5):
                unresolved += 1
                break
            hdr_b, msg_id = b5[off + 1 + j * 2], b5[off + 1 + j * 2 + 1]
            msg_ok, msg_len = _resolve_msg_length(b0, b1, b5, msg_id)
            if not msg_ok:
                unresolved += 1
            unique_msgs.add(msg_id)
            total_entries += 1
            entries.append({"headerByte": hdr_b, "freqSlot": hdr_b & 0x07, "triggerMode": (hdr_b >> 6) & 0x03, "msgId": msg_id, "msgByteLength": msg_len, "msgTerminated": msg_ok})
        room_calls.append({"roomId": r, "ptrHex": f"0x{ptr:04x}", "entryCount": cnt, "entries": entries, "inBounds": ok})

    envelopes: list[dict[str, Any]] = []
    for i in range(5):
        ep = u16_le(b6, 0x8000, 0x91EE + i * 2)
        ok = in_bank(ep)
        off = ep - 0x8000
        pos = off
        while ok and pos < len(b6) and b6[pos] < 0xFE:
            pos += 1
        term_ok = ok and pos < len(b6)
        if not term_ok:
            unresolved += 1
        envelopes.append({"envelopeId": i, "ptrHex": f"0x{ep:04x}", "lengthBytes": (pos - off) if term_ok else 0, "terminatorByte": b6[pos] if term_ok else 0, "values": list(b6[off:pos]) if term_ok else [], "inBounds": ok})

    periods = [u16_le(b6, 0x8000, 0x9923 + i * 2) for i in range(12)]
    periods_ok = all(periods[i] > periods[i + 1] > 0 for i in range(11))
    if not periods_ok:
        unresolved += 1

    descriptors: list[dict[str, Any]] = []
    for sid in range(1, 133):
        base = 0xBC15 + sid * 3
        hdr = b6[base - 0x8000]
        sp = u16_le(b6, 0x8000, base + 1)
        ok = in_bank(sp)
        if not ok:
            unresolved += 1
        descriptors.append({"soundId": sid, "headerByte": hdr, "channel": hdr & 0x07, "extraTrackCount": (hdr >> 3) & 0x03, "category": "sfx" if sid < 0x41 else "bgm", "ptrHex": f"0x{sp:04x}", "inBounds": ok})

    dmc_bytes = b7[0x3C80:0x3C84]
    dmc_addr = 0xC000 + dmc_bytes[2] * 64
    dmc_len = dmc_bytes[3] * 16 + 1
    dmc_ok = in_bank(dmc_addr, is_fixed=True) and (dmc_addr + dmc_len) <= 0x10000
    if not dmc_ok:
        unresolved += 1

    return {
        "schemaVersion": 2,
        "gameId": GAME_ID,
        "generatedAtUtc": utc_now_iso(),
        "summary": {
            "isPassed": unresolved == 0,
            "unresolvedFieldCount": unresolved,
            "codecFreqCount": len(freqs),
            "roomCallPointerCount": len(room_calls),
            "uniqueCallTableCount": len(unique_ptrs),
            "totalCallEntries": total_entries,
            "uniqueMessageIdCount": len(unique_msgs),
            "envelopeCount": len(envelopes),
            "notePeriodCount": len(periods),
            "soundDescriptorCount": len(descriptors),
            "sfxDescriptorCount": sum(1 for d in descriptors if d["category"] == "sfx"),
            "bgmDescriptorCount": sum(1 for d in descriptors if d["category"] == "bgm"),
            "dmcSampleCount": 1,
        },
        "codecFreqBytes": freqs,
        "roomCallTables": room_calls,
        "volumeEnvelopes": envelopes,
        "notePeriods": [{"noteIndex": i, "period": p, "periodHex": f"0x{p:04x}"} for i, p in enumerate(periods)],
        "soundDescriptors": descriptors,
        "dmcSamples": [{"sampleId": 0, "rateFlags4010": dmc_bytes[0], "padByte": dmc_bytes[1], "addrReg4012": dmc_bytes[2], "lengthReg4013": dmc_bytes[3], "sampleAddrHex": f"0x{dmc_addr:04x}", "sampleByteLength": dmc_len, "inBounds": dmc_ok}],
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for codec frequencies, room call tables, audio tables, and DMC[0]."""
    return run_decoder_cli(
        "decode_codec_and_audio", REQUIRED_BANKS, _synth_codec,
        decode_codec_and_audio, "codec_and_audio.json",
        "Decode BANK_05 codec freqs/calls, BANK_06 envelopes/periods/descriptors, and fixed dmc[0].", argv,
    )


if __name__ == "__main__":
    raise SystemExit(main())
