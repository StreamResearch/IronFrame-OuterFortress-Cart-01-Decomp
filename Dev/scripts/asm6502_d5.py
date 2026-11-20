# @module: IronFrame.Dev.scripts.asm6502_d5
# @purpose: Clean-room two-pass MOS 6502 assembler supporting all 56 official mnemonics and 13 modes
# @depends-on: argparse, pathlib, re
# @exports: AssemblerError, OPCODES, MODE_SIZE, eval_expr, assemble_text, assemble_file, main

from __future__ import annotations

import argparse
import re
from pathlib import Path

_RAW_OPCODES = (
    "00:BRK:imp 01:ORA:idx 05:ORA:zp 06:ASL:zp 08:PHP:imp 09:ORA:imm 0A:ASL:acc 0D:ORA:abs 0E:ASL:abs "
    "10:BPL:rel 11:ORA:idy 15:ORA:zpx 16:ASL:zpx 18:CLC:imp 19:ORA:aby 1D:ORA:abx 1E:ASL:abx "
    "20:JSR:abs 21:AND:idx 24:BIT:zp 25:AND:zp 26:ROL:zp 28:PLP:imp 29:AND:imm 2A:ROL:acc 2C:BIT:abs 2D:AND:abs 2E:ROL:abs "
    "30:BMI:rel 31:AND:idy 35:AND:zpx 36:ROL:zpx 38:SEC:imp 39:AND:aby 3D:AND:abx 3E:ROL:abx "
    "40:RTI:imp 41:EOR:idx 45:EOR:zp 46:LSR:zp 48:PHA:imp 49:EOR:imm 4A:LSR:acc 4C:JMP:abs 4D:EOR:abs 4E:LSR:abs "
    "50:BVC:rel 51:EOR:idy 55:EOR:zpx 56:LSR:zpx 58:CLI:imp 59:EOR:aby 5D:EOR:abx 5E:LSR:abx "
    "60:RTS:imp 61:ADC:idx 65:ADC:zp 66:ROR:zp 68:PLA:imp 69:ADC:imm 6A:ROR:acc 6C:JMP:ind 6D:ADC:abs 6E:ROR:abs "
    "70:BVS:rel 71:ADC:idy 75:ADC:zpx 76:ROR:zpx 78:SEI:imp 79:ADC:aby 7D:ADC:abx 7E:ROR:abx "
    "81:STA:idx 84:STY:zp 85:STA:zp 86:STX:zp 88:DEY:imp 8A:TXA:imp 8C:STY:abs 8D:STA:abs 8E:STX:abs "
    "90:BCC:rel 91:STA:idy 94:STY:zpx 95:STA:zpx 96:STX:zpy 98:TYA:imp 99:STA:aby 9A:TXS:imp 9D:STA:abx "
    "A0:LDY:imm A1:LDA:idx A2:LDX:imm A4:LDY:zp A5:LDA:zp A6:LDX:zp A8:TAY:imp A9:LDA:imm AA:TAX:imp AC:LDY:abs AD:LDA:abs AE:LDX:abs "
    "B0:BCS:rel B1:LDA:idy B4:LDY:zpx B5:LDA:zpx B6:LDX:zpy B8:CLV:imp B9:LDA:aby BA:TSX:imp BC:LDY:abx BD:LDA:abx BE:LDX:aby "
    "C0:CPY:imm C1:CMP:idx C4:CPY:zp C5:CMP:zp C6:DEC:zp C8:INY:imp C9:CMP:imm CA:DEX:imp CC:CPY:abs CD:CMP:abs CE:DEC:abs "
    "D0:BNE:rel D1:CMP:idy D5:CMP:zpx D6:DEC:zpx D8:CLD:imp D9:CMP:aby DD:CMP:abx DE:DEC:abx "
    "E0:CPX:imm E1:SBC:idx E4:CPX:zp E5:SBC:zp E6:INC:zp E8:INX:imp E9:SBC:imm EA:NOP:imp EC:CPX:abs ED:SBC:abs EE:INC:abs "
    "F0:BEQ:rel F1:SBC:idy F5:SBC:zpx F6:INC:zpx F8:SED:imp F9:SBC:aby FD:SBC:abx FE:INC:abx"
)
OPCODES: dict[str, dict[str, int]] = {}
for _tok in _RAW_OPCODES.split():
    _hx, _mn, _md = _tok.split(":")
    OPCODES.setdefault(_mn, {})[_md] = int(_hx, 16)

MODE_SIZE = {"imp": 1, "acc": 1, "imm": 2, "zp": 2, "zpx": 2, "zpy": 2, "idx": 2, "idy": 2, "rel": 2, "abs": 3, "abx": 3, "aby": 3, "ind": 3}
_TOK_RE = re.compile(r"\s*(?:(\$[0-9A-Fa-f]+)|(0[xX][0-9A-Fa-f]+)|(%[01]+)|('(?:\\.|[^'])')|([0-9]+)|([A-Za-z_@.][A-Za-z0-9_@.]*)|([+\-*&|^<>()]))")
_ABS_HEX_RE = re.compile(r"^(?:\$[0-9A-Fa-f]{4}|0[xX][0-9A-Fa-f]{4})$")
_BIN_OPS = {"*": (3, int.__mul__), "+": (2, int.__add__), "-": (2, int.__sub__), "&": (1, int.__and__), "^": (1, int.__xor__), "|": (1, int.__or__)}


class AssemblerError(ValueError):
    """Raised on 6502 assembly syntax, expression, range, or phase error."""


def _strip_comment(line: str) -> str:
    q, esc = None, False
    for idx, ch in enumerate(line):
        if esc: esc = False
        elif ch == "\\" and q: esc = True
        elif ch in ('"', "'"): q = None if q == ch else (ch if q is None else q)
        elif ch == ";" and q is None: return line[:idx]
    return line


def _split_csv(text: str) -> list[str]:
    items, cur, q, depth = [], [], None, 0
    for ch in text:
        if ch in ('"', "'"): q = None if q == ch else (ch if q is None else q)
        elif q is None:
            if ch == "(": depth += 1
            elif ch == ")": depth -= 1
            elif ch == "," and depth == 0: items.append("".join(cur).strip()); cur = []; continue
        cur.append(ch)
    if cur or items: items.append("".join(cur).strip())
    return [i for i in items if i]


def _tokenize(expr: str) -> list[tuple[str, str]]:
    pos, out, n = 0, [], len(expr)
    while pos < n:
        if expr[pos].isspace(): pos += 1; continue
        m = _TOK_RE.match(expr, pos)
        if not m: raise AssemblerError(f"Unexpected token in {expr!r} at {pos}")
        pos, g = m.end(), m.lastindex
        if g == 1: out.append(("NUM", str(int(m.group(1)[1:], 16))))
        elif g == 2: out.append(("NUM", str(int(m.group(2)[2:], 16))))
        elif g == 3: out.append(("NUM", str(int(m.group(3)[1:], 2))))
        elif g == 4:
            raw = m.group(4)[1:-1]
            out.append(("NUM", str(ord(raw.encode("utf-8").decode("unicode_escape") if raw.startswith("\\") else raw))))
        elif g == 5: out.append(("NUM", m.group(5)))
        elif g == 6: out.append(("SYM", m.group(6)))
        else: out.append(("OP", m.group(7)))
    return out


def eval_expr(expr: str, symbols: dict[str, int], pc: int, allow_missing: bool = False) -> int | None:
    """Evaluate a 6502 expression supporting +, -, *, &, |, ^, <, >, (), literals, PC *, and symbols."""
    toks = _tokenize(expr)
    if not toks: raise AssemblerError("Empty expression")
    idx = 0

    def atom() -> int | None:
        nonlocal idx
        if idx >= len(toks): raise AssemblerError(f"Truncated expression: {expr!r}")
        k, v = toks[idx]; idx += 1
        if k == "OP" and v in ("+", "-", "<", ">"):
            val = atom()
            if val is None: return None
            return val if v == "+" else (-val if v == "-" else ((val & 0xFF) if v == "<" else ((val >> 8) & 0xFF)))
        if k == "OP" and v == "(":
            val = parse(1)
            if idx >= len(toks) or toks[idx] != ("OP", ")"): raise AssemblerError(f"Unmatched '(' in {expr!r}")
            idx += 1; return val
        if k == "OP" and v == "*": return pc
        if k == "NUM": return int(v)
        if k == "SYM":
            if v in symbols: return symbols[v]
            if allow_missing: return None
            raise AssemblerError(f"Undefined symbol: {v!r}")
        raise AssemblerError(f"Bad token {(k, v)!r} in {expr!r}")

    def parse(min_p: int) -> int | None:
        nonlocal idx
        left = atom()
        while idx < len(toks) and toks[idx][0] == "OP" and _BIN_OPS.get(toks[idx][1], (0, None))[0] >= min_p:
            p, fn = _BIN_OPS[toks[idx][1]]; idx += 1
            right = parse(p + 1)
            left = None if (left is None or right is None) else fn(left, right)
        return left

    res = parse(1)
    if idx != len(toks): raise AssemblerError(f"Trailing tokens in {expr!r}: {toks[idx:]}")
    return res


def _strip_override(expr: str) -> tuple[str, str]:
    m = re.fullmatch(r"([AaZz]):(.+)", expr.strip())
    return (m.group(1).lower(), m.group(2).strip()) if m else ("", expr.strip())


def _resolve_mode(mnem: str, arg: str, symbols: dict[str, int], pc: int, allow_missing: bool) -> tuple[str, int | None]:
    modes = OPCODES.get(mnem)
    if modes is None:
        raise AssemblerError(f"Unknown mnemonic {mnem!r}")
    if not arg:
        if "imp" in modes: return "imp", None
        if "acc" in modes: return "acc", None
        raise AssemblerError(f"{mnem} requires an operand")
    if arg.upper() == "A" and "acc" in modes:
        return "acc", None
    if arg.startswith("#"):
        if "imm" not in modes: raise AssemblerError(f"{mnem} has no imm mode")
        return "imm", eval_expr(arg[1:].strip(), symbols, pc, allow_missing)
    if "rel" in modes:
        return "rel", eval_expr(arg, symbols, pc, allow_missing)
    if (m := re.fullmatch(r"\((.+),\s*[Xx]\)", arg)) and "idx" in modes:
        return "idx", eval_expr(_strip_override(m.group(1))[1], symbols, pc, allow_missing)
    if (m := re.fullmatch(r"\((.+)\),\s*[Yy]", arg)) and "idy" in modes:
        return "idy", eval_expr(_strip_override(m.group(1))[1], symbols, pc, allow_missing)
    if (m := re.fullmatch(r"\((.+)\)", arg)) and "ind" in modes:
        return "ind", eval_expr(_strip_override(m.group(1))[1], symbols, pc, allow_missing)

    sfx, expr = "", arg
    if m := re.fullmatch(r"(.+),\s*[Xx]", arg): sfx, expr = "x", m.group(1).strip()
    elif m := re.fullmatch(r"(.+),\s*[Yy]", arg): sfx, expr = "y", m.group(1).strip()
    ov, inner = _strip_override(expr)
    force_abs = ov == "a" or bool(_ABS_HEX_RE.fullmatch(expr.strip()))
    zp_m, abs_m = ("zp" if not sfx else f"zp{sfx}"), ("abs" if not sfx else f"ab{sfx}")
    val = eval_expr(inner, symbols, pc, allow_missing)
    if force_abs:
        if abs_m not in modes: raise AssemblerError(f"{mnem} has no {abs_m} mode")
        return abs_m, val
    if ov == "z":
        if zp_m not in modes: raise AssemblerError(f"{mnem} has no {zp_m} mode")
        return zp_m, val
    if val is not None and 0 <= val <= 0xFF and zp_m in modes:
        return zp_m, val
    if abs_m in modes: return abs_m, val
    if zp_m in modes: return zp_m, val
    raise AssemblerError(f"{mnem} does not support {arg!r}")


def _parse_lines(source: str) -> list[tuple[int, str, str, str]]:
    stmts: list[tuple[int, str, str, str]] = []
    for lineno, raw in enumerate(source.splitlines(), start=1):
        line = _strip_comment(raw).strip()
        if not line: continue
        if m := re.fullmatch(r"([A-Za-z_.][A-Za-z0-9_.]*)\s*(?:=|\bEQU\b)\s*(.+)", line, re.IGNORECASE):
            stmts.append((lineno, "EQU", m.group(1), m.group(2).strip())); continue
        while ":" in line:
            head, tail = line.split(":", 1)
            lbl = head.strip()
            if not re.fullmatch(r"[A-Za-z_@.][A-Za-z0-9_@.]*", lbl): break
            stmts.append((lineno, "LBL", lbl, "")); line = tail.strip()
            if not line: break
        if not line: continue
        if m := re.fullmatch(r"\*\s*=\s*(.+)", line):
            stmts.append((lineno, "ORG", m.group(1).strip(), "")); continue
        parts = line.split(None, 1)
        op_u, arg = parts[0].upper(), (parts[1].strip() if len(parts) > 1 else "")
        if op_u in (".ORG", "ORG"): stmts.append((lineno, "ORG", arg, ""))
        elif op_u in (".EQU", "EQU"):
            k, v = (arg.split(",", 1) if "," in arg else arg.split(None, 1))
            stmts.append((lineno, "EQU", k.strip(), v.strip()))
        elif op_u in (".BYTE", ".DB"): stmts.append((lineno, "BYTE", arg, ""))
        elif op_u in (".WORD", ".DW"): stmts.append((lineno, "WORD", arg, ""))
        else: stmts.append((lineno, "INS", op_u, arg))
    return stmts


def _emit_bytes(arg: str, symbols: dict[str, int], pc: int, emit: bytearray | None) -> int:
    total = 0
    for item in _split_csv(arg):
        if len(item) >= 2 and item[0] == '"' and item[-1] == '"':
            raw = item[1:-1].encode("latin1")
            if emit is not None: emit.extend(raw)
            total += len(raw)
        else:
            if emit is not None:
                val = eval_expr(item, symbols, pc, allow_missing=False)
                assert val is not None
                if not (-128 <= val <= 0xFF): raise AssemblerError(f".byte {val} out of range")
                emit.append(val & 0xFF)
            total += 1
    return total


def assemble_text(source: str, fill_byte: int = 0xFF) -> tuple[bytes, int, dict[str, int]]:
    """Assemble clean-room 6502 source text in two passes; return (bytes, origin, symbols)."""
    stmts, symbols, pass1, pc, base_org = _parse_lines(source), {}, [], 0, None
    for lineno, kind, a, b in stmts:
        try:
            if kind == "EQU": symbols[a] = int(eval_expr(b, symbols, pc, False))  # type: ignore[arg-type]
            elif kind == "LBL": symbols[a] = pc
            elif kind == "ORG":
                pc = int(eval_expr(a, symbols, pc, False))  # type: ignore[arg-type]
                if base_org is None: base_org = pc
            elif kind == "BYTE":
                sz = _emit_bytes(a, symbols, pc, None); pass1.append((pc, f"B:{sz}")); pc += sz
            elif kind == "WORD":
                sz = len(_split_csv(a)) * 2; pass1.append((pc, f"W:{sz}")); pc += sz
            elif kind == "INS":
                mode, _ = _resolve_mode(a, b, symbols, pc, True)
                sz = MODE_SIZE[mode]; pass1.append((pc, f"{mode}:{sz}")); pc += sz
        except AssemblerError as exc:
            raise AssemblerError(f"Pass 1 line {lineno}: {exc}") from exc

    origin, buf, pc, idx = (0 if base_org is None else base_org), bytearray(), (0 if base_org is None else base_org), 0
    for lineno, kind, a, b in stmts:
        try:
            if kind in ("EQU", "LBL"): continue
            if kind == "ORG":
                pc = int(eval_expr(a, symbols, pc, False))  # type: ignore[arg-type]
                if pc < origin: raise AssemblerError(f".org ${pc:04X} < ${origin:04X}")
                if pc - origin > len(buf): buf.extend([fill_byte] * (pc - origin - len(buf)))
                continue
            p1_pc, p1_tag = pass1[idx]; idx += 1
            if pc != p1_pc: raise AssemblerError(f"Phase drift ${p1_pc:04X} != ${pc:04X}")
            chunk = bytearray()
            if kind == "BYTE": _emit_bytes(a, symbols, pc, chunk)
            elif kind == "WORD":
                for item in _split_csv(a):
                    v = int(eval_expr(item, symbols, pc, False))  # type: ignore[arg-type]
                    chunk.extend((v & 0xFF, (v >> 8) & 0xFF))
            elif kind == "INS":
                mode, val = _resolve_mode(a, b, symbols, pc, False)
                sz = MODE_SIZE[mode]
                if f"{mode}:{sz}" != p1_tag: raise AssemblerError(f"Mode drift {p1_tag} -> {mode}:{sz}")
                chunk.append(OPCODES[a][mode])
                if sz == 2:
                    assert val is not None
                    if mode == "rel":
                        disp = val - (pc + 2)
                        if not (-128 <= disp <= 127): raise AssemblerError(f"Branch {disp} out of range at ${pc:04X}")
                        chunk.append(disp & 0xFF)
                    else:
                        if not (-128 <= val <= 0xFF): raise AssemblerError(f"Operand ${val:X} > 8 bits")
                        chunk.append(val & 0xFF)
                elif sz == 3:
                    assert val is not None
                    chunk.extend((val & 0xFF, (val >> 8) & 0xFF))
            off = pc - origin
            if off + len(chunk) > len(buf): buf.extend([fill_byte] * (off + len(chunk) - len(buf)))
            buf[off:off + len(chunk)] = chunk; pc += len(chunk)
        except AssemblerError as exc:
            raise AssemblerError(f"Pass 2 line {lineno}: {exc}") from exc
    return bytes(buf), origin, symbols


def assemble_file(asm_path: Path, out_path: Path | None = None) -> tuple[bytes, int, dict[str, int]]:
    """Assemble a .asm file and optionally write its binary image."""
    raw, origin, syms = assemble_text(Path(asm_path).read_text(encoding="utf-8"))
    if out_path is not None:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True); Path(out_path).write_bytes(raw)
    return raw, origin, syms


def main() -> int:
    ap = argparse.ArgumentParser(description="Clean-room two-pass MOS 6502 assembler.")
    ap.add_argument("input", type=Path); ap.add_argument("-o", "--output", type=Path, required=True)
    args = ap.parse_args()
    raw, origin, syms = assemble_file(args.input, args.output)
    print(f"Assembled {args.input.name}: {len(raw)} bytes @ ${origin:04X}, {len(syms)} symbols -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
