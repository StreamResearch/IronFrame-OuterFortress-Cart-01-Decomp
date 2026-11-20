# @module: IronFrame.Dev.scripts.nes_6502_cfg
# @purpose: Pure-stdlib 6502 opcode table, iNES parser, CFG/inline jump-table tracer, UNROM call propagator, and disassembler
# @depends-on: typing
# @exports: BANK_SIZE, OPCODES, parse_ines, _parse_ines, read_u16, _read_u16, trace_cfg, _trace_cfg, trace_smart, _trace_smart, propagate_bank_calls, _propagate_bank_calls, format_disasm, _format_disasm, to_intervals, _to_intervals

from __future__ import annotations

from typing import Any

BANK_SIZE = 16384

_RAW_OPCODES = (
    "00:BRK:imp:1:stop 01:ORA:idx:2:n 05:ORA:zp:2:n 06:ASL:zp:2:n 08:PHP:imp:1:n "
    "09:ORA:imm:2:n 0A:ASL:acc:1:n 0D:ORA:abs:3:n 0E:ASL:abs:3:n "
    "10:BPL:rel:2:br 11:ORA:idy:2:n 15:ORA:zpx:2:n 16:ASL:zpx:2:n 18:CLC:imp:1:n "
    "19:ORA:aby:3:n 1D:ORA:abx:3:n 1E:ASL:abx:3:n "
    "20:JSR:abs:3:jsr 21:AND:idx:2:n 24:BIT:zp:2:n 25:AND:zp:2:n 26:ROL:zp:2:n 28:PLP:imp:1:n "
    "29:AND:imm:2:n 2A:ROL:acc:1:n 2C:BIT:abs:3:n 2D:AND:abs:3:n 2E:ROL:abs:3:n "
    "30:BMI:rel:2:br 31:AND:idy:2:n 35:AND:zpx:2:n 36:ROL:zpx:2:n 38:SEC:imp:1:n "
    "39:AND:aby:3:n 3D:AND:abx:3:n 3E:ROL:abx:3:n "
    "40:RTI:imp:1:stop 41:EOR:idx:2:n 45:EOR:zp:2:n 46:LSR:zp:2:n 48:PHA:imp:1:n "
    "49:EOR:imm:2:n 4A:LSR:acc:1:n 4C:JMP:abs:3:jmp 4D:EOR:abs:3:n 4E:LSR:abs:3:n "
    "50:BVC:rel:2:br 51:EOR:idy:2:n 55:EOR:zpx:2:n 56:LSR:zpx:2:n 58:CLI:imp:1:n "
    "59:EOR:aby:3:n 5D:EOR:abx:3:n 5E:LSR:abx:3:n "
    "60:RTS:imp:1:stop 61:ADC:idx:2:n 65:ADC:zp:2:n 66:ROR:zp:2:n 68:PLA:imp:1:n "
    "69:ADC:imm:2:n 6A:ROR:acc:1:n 6C:JMP:ind:3:ijmp 6D:ADC:abs:3:n 6E:ROR:abs:3:n "
    "70:BVS:rel:2:br 71:ADC:idy:2:n 75:ADC:zpx:2:n 76:ROR:zpx:2:n 78:SEI:imp:1:n "
    "79:ADC:aby:3:n 7D:ADC:abx:3:n 7E:ROR:abx:3:n "
    "81:STA:idx:2:n 84:STY:zp:2:n 85:STA:zp:2:n 86:STX:zp:2:n 88:DEY:imp:1:n "
    "8A:TXA:imp:1:n 8C:STY:abs:3:n 8D:STA:abs:3:n 8E:STX:abs:3:n "
    "90:BCC:rel:2:br 91:STA:idy:2:n 94:STY:zpx:2:n 95:STA:zpx:2:n 96:STX:zpy:2:n 98:TYA:imp:1:n "
    "99:STA:aby:3:n 9A:TXS:imp:1:n 9D:STA:abx:3:n "
    "A0:LDY:imm:2:n A1:LDA:idx:2:n A2:LDX:imm:2:n A4:LDY:zp:2:n A5:LDA:zp:2:n A6:LDX:zp:2:n "
    "A8:TAY:imp:1:n A9:LDA:imm:2:n AA:TAX:imp:1:n AC:LDY:abs:3:n AD:LDA:abs:3:n AE:LDX:abs:3:n "
    "B0:BCS:rel:2:br B1:LDA:idy:2:n B4:LDY:zpx:2:n B5:LDA:zpx:2:n B6:LDX:zpy:2:n B8:CLV:imp:1:n "
    "B9:LDA:aby:3:n BA:TSX:imp:1:n BC:LDY:abx:3:n BD:LDA:abx:3:n BE:LDX:aby:3:n "
    "C0:CPY:imm:2:n C1:CMP:idx:2:n C4:CPY:zp:2:n C5:CMP:zp:2:n C6:DEC:zp:2:n C8:INY:imp:1:n "
    "C9:CMP:imm:2:n CA:DEX:imp:1:n CC:CPY:abs:3:n CD:CMP:abs:3:n CE:DEC:abs:3:n "
    "D0:BNE:rel:2:br D1:CMP:idy:2:n D5:CMP:zpx:2:n D6:DEC:zpx:2:n D8:CLD:imp:1:n "
    "D9:CMP:aby:3:n DD:CMP:abx:3:n DE:DEC:abx:3:n "
    "E0:CPX:imm:2:n E1:SBC:idx:2:n E4:CPX:zp:2:n E5:SBC:zp:2:n E6:INC:zp:2:n E8:INX:imp:1:n "
    "E9:SBC:imm:2:n EA:NOP:imp:1:n EC:CPX:abs:3:n ED:SBC:abs:3:n EE:INC:abs:3:n "
    "F0:BEQ:rel:2:br F1:SBC:idy:2:n F5:SBC:zpx:2:n F6:INC:zpx:2:n F8:SED:imp:1:n "
    "F9:SBC:aby:3:n FD:SBC:abx:3:n FE:INC:abx:3:n"
)

OPCODES: dict[int, tuple[str, str, int, str]] = {
    int(hx, 16): (mn, md, int(ln), fk)
    for hx, mn, md, ln, fk in (tok.split(":") for tok in _RAW_OPCODES.split())
}

_MD2_FMT = {
    "imm": lambda b, a: f"#${b:02X}", "zp": lambda b, a: f"${b:02X}",
    "zpx": lambda b, a: f"${b:02X},X", "zpy": lambda b, a: f"${b:02X},Y",
    "idx": lambda b, a: f"(${b:02X},X)", "idy": lambda b, a: f"(${b:02X}),Y",
    "rel": lambda b, a: f"${a + 2 + (b - 256 if b >= 128 else b):04X}",
}


def parse_ines(rom_bytes: bytes) -> dict[str, Any]:
    """Parse iNES / NES 2.0 header and return mapper metadata plus PRG payload."""
    if len(rom_bytes) < 16 or rom_bytes[:4] != b"NES\x1a":
        raise ValueError("Not a valid iNES ROM image")
    prg_banks, chr_banks = rom_bytes[4], rom_bytes[5]
    flags6, flags7 = rom_bytes[6], rom_bytes[7]
    is_nes2 = (flags7 & 0x0C) == 0x08
    mapper = ((flags6 >> 4) & 0x0F) | (flags7 & 0xF0) | (((rom_bytes[8] & 0x0F) << 8) if is_nes2 else 0)
    expected = 16 + prg_banks * BANK_SIZE + chr_banks * 8192
    if prg_banks == 0 or len(rom_bytes) < expected:
        raise ValueError(f"Invalid or truncated iNES ROM: {len(rom_bytes)} < {expected}")
    return {
        "prg_banks": prg_banks, "chr_banks": chr_banks, "mapper": mapper, "is_nes2": is_nes2,
        "mirroring": "vertical" if (flags6 & 1) else "horizontal",
        "battery_sram": bool(flags6 & 2),
        "prg_data": rom_bytes[16:16 + prg_banks * BANK_SIZE],
    }


def read_u16(mem: bytes | bytearray, addr: int) -> int:
    """Read little-endian 16-bit word from 32 KiB CPU PRG window [$8000, $10000)."""
    off = addr - 0x8000
    return mem[off] | (mem[off + 1] << 8)


def trace_cfg(mem: bytes | bytearray, seeds: list[int], win_lo: int, win_hi: int) -> tuple[set[int], set[int], set[int]]:
    """Recursive-descent 6502 CFG tracer across 32 KiB PRG view [0x8000, 0x10000)."""
    visited_insns, code_bytes, funcs = set(), set(), set()
    queue = [s for s in seeds if win_lo <= s < win_hi]
    funcs.update(queue)
    while queue:
        pc = queue.pop()
        if pc in visited_insns or not (0x8000 <= pc < 0xFFFA):
            continue
        off = pc - 0x8000
        info = OPCODES.get(mem[off])
        if not info or off + info[2] > 0x7FFA:
            continue
        mn, _md, ln, fk = info
        if fk == "stop" and mn == "BRK":
            continue
        visited_insns.add(pc)
        code_bytes.update(range(pc, pc + ln))
        nxt = pc + ln
        if fk == "n":
            queue.append(nxt)
        elif fk == "br":
            rel = mem[off + 1]
            tgt = nxt + (rel - 256 if rel >= 128 else rel)
            queue.append(nxt)
            if win_lo <= tgt < 0xFFFA:
                queue.append(tgt)
        elif fk == "jmp":
            tgt = read_u16(mem, pc + 1)
            if win_lo <= tgt < 0xFFFA:
                if abs(tgt - pc) > 128 and tgt not in visited_insns and tgt < win_hi:
                    funcs.add(tgt)
                queue.append(tgt)
        elif fk == "jsr":
            tgt = read_u16(mem, pc + 1)
            queue.append(nxt)
            if 0x8000 <= tgt < 0xFFFA:
                if win_lo <= tgt < win_hi:
                    funcs.add(tgt)
                queue.append(tgt)
    return visited_insns, code_bytes, funcs


def trace_smart(mem: bytes | bytearray, seeds: list[int], win_lo: int, win_hi: int) -> tuple[set[int], set[int], set[int]]:
    """Trace 6502 CFG with inline jump tables (JSR $C6B7) and fixed dispatch ($C885)."""
    insns, code_b, funcs = trace_cfg(mem, seeds, win_lo, win_hi)
    while True:
        added: list[int] = []
        for pc in sorted(insns):
            off = pc - 0x8000
            if mem[off:off + 3] == b"\x20\xb7\xc6":
                tbl, min_t = pc + 3, win_hi
                while tbl + 2 <= min_t and tbl - 0x8000 + 2 <= len(mem):
                    w = read_u16(mem, tbl)
                    if not (0x8000 <= w < 0xFFFA):
                        break
                    if w > tbl:
                        min_t = min(min_t, w)
                    if win_lo <= w < win_hi and w not in insns:
                        added.append(w)
                    tbl += 2
        if win_lo == 0xC000 and 0xC885 in insns:
            for k in range(16):
                w = read_u16(mem, 0xC8A6 + 2 * k)
                if 0xC000 <= w < 0xFFFA and w not in insns:
                    added.append(w)
        if not added:
            break
        i2, c2, f2 = trace_cfg(mem, added, win_lo, win_hi)
        if not (i2 - insns):
            break
        insns |= i2
        code_b |= c2
        funcs |= f2
    return insns, code_b, funcs


def propagate_bank_calls(fm: bytes | bytearray, funcs: set[int]) -> dict[int, set[int]]:
    """Pair fixed-bank cross-bank JSR/JMP targets with active UNROM bank via dataflow."""
    sw_map = {0xC932 + 4 * b: b for b in range(7)}
    cross: dict[int, set[int]] = {b: set() for b in range(7)}
    for fstart in sorted(funcs):
        q: list[tuple[int, int, int]] = [(fstart, 6, 6)]
        seen: set[tuple[int, int, int]] = set()
        while q:
            pc, cur_b, prev_b = q.pop()
            if (pc, cur_b, prev_b) in seen or not (0xC000 <= pc < 0xFFFA):
                continue
            seen.add((pc, cur_b, prev_b))
            off = pc - 0x8000
            info = OPCODES.get(fm[off])
            if not info or off + info[2] > 0x7FFA:
                continue
            _, _, ln, fk = info
            nxt = pc + ln
            if fk == "n":
                q.append((nxt, cur_b, prev_b))
            elif fk == "br":
                rel = fm[off + 1]
                q.append((nxt, cur_b, prev_b))
                q.append((nxt + (rel - 256 if rel >= 128 else rel), cur_b, prev_b))
            elif fk == "jmp":
                t = read_u16(fm, pc + 1)
                if 0x8000 <= t < 0xC000:
                    cross[cur_b].add(t)
                elif t not in sw_map:
                    q.append((t, cur_b, prev_b))
            elif fk == "jsr":
                t = read_u16(fm, pc + 1)
                if t in sw_map:
                    q.append((nxt, sw_map[t], cur_b))
                elif t == 0xC958:
                    q.append((nxt, prev_b, cur_b))
                elif t == 0xC94C and off >= 2 and fm[off - 2] == 0xA0:
                    nb = fm[off - 1]
                    q.append((nxt, nb if nb < 7 else cur_b, cur_b))
                elif t == 0xC6B7:
                    tbl, min_t = nxt, 0xFFFA
                    while tbl + 2 <= min_t:
                        w = read_u16(fm, tbl)
                        if not (0x8000 <= w < 0xFFFA):
                            break
                        if w > tbl:
                            min_t = min(min_t, w)
                        if w < 0xC000:
                            cross[cur_b].add(w)
                        else:
                            q.append((w, cur_b, prev_b))
                        tbl += 2
                else:
                    if 0x8000 <= t < 0xC000:
                        cross[cur_b].add(t)
                    q.append((nxt, cur_b, prev_b))
    return cross


def format_disasm(mem: bytes | bytearray, win_lo: int, win_hi: int, insns: set[int], funcs: set[int]) -> str:
    """Format traced 6502 code and byte data into assembler-compatible .s disassembly."""
    lines = [f"; 6502 UNROM Bank Disassembly [{win_lo:#06x}, {win_hi:#06x})", ""]
    addr = win_lo
    while addr < win_hi:
        if addr in funcs:
            lines.append(f"\n; --- sub_{addr:04x} ---")
        off = addr - 0x8000
        info = OPCODES.get(mem[off])
        if addr in insns and info and addr + info[2] <= win_hi:
            mn, md, ln, _ = info
            raw = " ".join(f"{mem[off + i]:02X}" for i in range(ln))
            op_s = ""
            if ln == 2 and md in _MD2_FMT:
                op_s = _MD2_FMT[md](mem[off + 1], addr)
            elif ln == 3:
                w = mem[off + 1] | (mem[off + 2] << 8)
                sfx = ",X" if md == "abx" else (",Y" if md == "aby" else "")
                op_s = f"(${w:04X})" if md == "ind" else f"${w:04X}{sfx}"
            lines.append(f"${addr:04X}:  {raw:<9} {mn} {op_s}".rstrip())
            addr += ln
        else:
            lines.append(f"${addr:04X}:  {mem[off]:02X}        .byte ${mem[off]:02X}")
            addr += 1
    return "\n".join(lines) + "\n"


def to_intervals(addrs: set[int], lo: int, hi: int) -> list[list[int]]:
    """Collapse sorted integer addresses within [lo, hi) into half-open [start, end) ranges."""
    ivs: list[list[int]] = []
    for a in range(lo, hi):
        if a in addrs:
            if ivs and ivs[-1][1] == a:
                ivs[-1][1] = a + 1
            else:
                ivs.append([a, a + 1])
    return ivs


_parse_ines = parse_ines
_read_u16 = read_u16
_trace_cfg = trace_cfg
_trace_smart = trace_smart
_propagate_bank_calls = propagate_bank_calls
_format_disasm = format_disasm
_to_intervals = to_intervals
