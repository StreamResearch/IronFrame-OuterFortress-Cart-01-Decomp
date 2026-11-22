# @module: IronFrame.Dev.scripts.craftsmanship_d4_ast_cleaner
# @purpose: Transform D3 C function bodies into idiomatic zero-tell D4 C11 under strict warnings
# @depends-on: re, typing, craftsmanship_d4_helpers
# @exports: SCALAR_ARRAY_MAP, clean_function_block, unroll_if_commas, parenthesize_bitwise_and, reverse_yoda_cmps

from __future__ import annotations

import re
from typing import Any

from craftsmanship_d4_helpers import C_KEYWORDS, has_top_comma, mask_non_code, match_fwd

SCALAR_ARRAY_MAP: dict[str, tuple[str, int]] = {
    **{f"g_wram_07{h:02x}": ("g_vram_transfer_queue", h - 0x40) for h in (0x41, 0x42, 0x43, 0x53)},
    **{f"g_spr_shadow_03{h:02x}": ("g_actor_soa_ram", h) for h in (0x02, 0x0C, 0x10, 0x18, 0x2C, 0x38, 0x4C, 0x58)},
    **{f"g_apu_pulse1_{n}": ("g_apu_mmio_regs", i) for i, n in enumerate(("ctrl", "sweep", "lo", "hi"))},
}
_LOCAL_MAP = {
    "in_A": "cpu_a", "in_X": "cpu_x", "in_Y": "cpu_y", "in_Z": "cpu_zero", "in_C": "cpu_carry",
    "in_N": "cpu_neg", "in_V": "cpu_overflow", "in_B": "cpu_brk", "in_D": "cpu_decimal", "in_I": "cpu_irq_mask",
    "unaff_retaddr": "caller_ret_addr", "unaff_retaddr_00": "caller_ret_hi", "pbVar1": "byte_ptr",
    **dict(zip(("bVar1", "bVar2", "bVar3", "bVar4", "bVar5"), ("temp_byte", "step_byte", "mask_byte", "idx_byte", "flag_byte"))),
    **dict(zip(("cVar1", "cVar2", "cVar3", "cVar4", "cVar5"), ("signed_val", "signed_step", "signed_delta", "signed_flag", "signed_idx"))),
    "uVar1": "byte_val", "uVar2": "next_byte", "uVar3": "slot_byte", "sVar2": "signed_lo", "sVar3": "signed_hi",
    "anim_tile_00": "anim_tile_cur", "actor_slot_00": "actor_slot_cur", "oam_offset_00": "oam_offset_cur",
    "dir_index_00": "dir_index_cur", "proj_slot_00": "proj_slot_cur",
}
_ALT_NAMES = ("aux_byte", "cur_byte", "loop_byte", "read_byte", "hold_byte", "alt_byte", "delta_byte", "count_byte")
_TYPE_WORDS = (
    (r"\bundefined1?\b|\bbyte\b|\buchar\b", "u8"), (r"\bsbyte\b", "s8"),
    (r"\bundefined2\b|\bushort\b|\bword\b", "u16"), (r"\bundefined[34]\b|\bdword\b|\buint\b|\bulong\b", "u32"),
    (r"\bundefined8\b|\bulonglong\b", "u64"), (r"\blonglong\b", "s64"), (r"\bshort\b", "s16"),
)
_STACK_DECL_RE = re.compile(r"^[ \t]*(?:undefined1|byte|char|sbyte|u8|s8)\s+([ubcs]Stack[0-9A-Za-z_]*)\s*;\s*$")
_STACK_ASSIGN_RE = re.compile(r"^([ \t]*)([ubcs]Stack[0-9A-Za-z_]*)\s*=\s*([^;]+);\s*$")
_PTR_CAST_RE = re.compile(r"\(\s*((?:u8|s8|char|bool|u16|s16|u32|s32|u64|s64|void)\s*\*+)\s*\)\s*")
_LOCAL_INIT_RE = re.compile(r"^([ \t]+(?:(?:u8|s8|u16|s16|u32|s32|u64|s64|bool|char|int)\s+(?:\*\s*)?))([A-Za-z_]\w*)\s*;", re.M)
_SIG_RE = re.compile(r"^(?:static\s+)?((?:const\s+)?[A-Za-z_]\w*(?:\s*\*+)?)\s+([A-Za-z_]\w*)\s*\(([^)]*)\)", re.M)
_YODA_LIT_RE = re.compile(r"(?<![A-Za-z0-9_.\-+])((?:0x[0-9A-Fa-f]+[uUlL]*|-?\d+[uUlL]*|'(?:\\.|[^'\\])+'))\s*(?<![<>])(<=|>=|<|>)(?![<>=])\s*")
_FLIP_OP, _ALPHA = {"<": ">", "<=": ">=", ">": "<", ">=": "<="}, "abcdefghijklmnopqrstuvwxyz"


def _tag(i: int) -> str:
    return _ALPHA[i] if i < 26 else f"{_ALPHA[(i // 26) - 1]}{_ALPHA[i % 26]}"


def _alloc_name(base: str, used: set[str]) -> str:
    cands = [base, *(_ALT_NAMES if ("byte" in base or "val" in base) else ())]
    if not (cand := next((c for c in cands if c not in used), None)):
        i = 0
        while f"{base}_{_tag(i)}" in used:
            i += 1
        cand = f"{base}_{_tag(i)}"
    used.add(cand)
    return cand


def _sub_masked(code: str, pat: re.Pattern[str], repl_fn: Any) -> str:
    masked, out, pos = mask_non_code(code), [], 0
    for m in pat.finditer(masked):
        if m.start() >= pos:
            out.append(code[pos:m.start()] + repl_fn(code, m)); pos = m.end()
    return "".join(out) + code[pos:]


def _clean_stack_and_locals(code: str, used: set[str]) -> tuple[str, dict[str, str], list[str]]:
    renames, transforms, lines = {}, [], code.splitlines()
    live = {t for ln in lines if not _STACK_DECL_RE.match(ln) and not ((m := _STACK_ASSIGN_RE.match(ln)) and m.group(2) not in m.group(3)) for t in re.findall(r"\b([ubcs]Stack[0-9A-Za-z_]*)\b", ln)}
    dead = {m.group(1) for ln in lines if (m := _STACK_DECL_RE.match(ln))} - live
    if dead:
        code = "\n".join(f"{am.group(1)}{am.group(3).strip()};" if (am := _STACK_ASSIGN_RE.match(ln)) and am.group(2) in dead and any(t in am.group(3) for t in ("(", "++", "--")) else ln
                         for ln in lines if not ((dm := _STACK_DECL_RE.match(ln)) and dm.group(1) in dead) and not ((am2 := _STACK_ASSIGN_RE.match(ln)) and am2.group(2) in dead and not any(t in am2.group(3) for t in ("(", "++", "--"))))
        transforms.append("dead_stack_elim")
    renames.update({st: _alloc_name("saved_acc", used) for st in sorted(live)})
    masked = mask_non_code(code)
    renames.update({raw: _alloc_name(_LOCAL_MAP[raw], used) for raw in sorted(set(_LOCAL_MAP) & set(re.findall(r"\b[A-Za-z_]\w*\b", masked)), key=len, reverse=True)})
    renames.update({lbl: _alloc_name(f"step_{_tag(idx)}", used) for idx, lbl in enumerate(dict.fromkeys(re.findall(r"\b((?:LAB|code_r0x|joined_r0x)[0-9A-Za-z_]+)\b", masked)))})
    if renames:
        code = _sub_masked(code, re.compile(r"\b(" + "|".join(re.escape(k) for k in sorted(renames, key=len, reverse=True)) + r")\b"), lambda _c, m: renames[m.group(1)])
        transforms.append("local_rename")
    return code, renames, transforms


def _split_top_binop(expr: str, ops: tuple[str, ...]) -> tuple[str, str, str] | None:
    depth, in_q, ordered, i = 0, None, tuple(sorted(ops, key=len, reverse=True)), 0
    while i < len(expr):
        ch = expr[i]
        if in_q:
            i += 2 if ch == "\\" else 1
            in_q = None if (ch == in_q and expr[i - 2:i - 1] != "\\") else in_q
            continue
        if ch in ('"', "'"):
            in_q = ch
        elif ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        elif depth == 0:
            prev = expr[i - 1] if i > 0 else ""
            for op in ordered:
                nxt = expr[i + len(op):i + len(op) + 1]
                if expr.startswith(op, i) and not (op == "=" and (prev in "!=<>+-|&^" or nxt == "=")) and not (op in "<>" and (prev == op or nxt in (op, "="))) and not (op in "|&" and (prev == op or nxt in (op, "="))):
                    return op, expr[:i].strip(), expr[i + len(op):].strip()
        i += 1
    return None


def _strip_parens(s: str) -> str:
    s = s.strip()
    while s.startswith("(") and s.endswith(")") and match_fwd(s, 0) == len(s) - 1:
        s = s[1:-1].strip()
    return s


def _emit_cond_eval(expr: str, var: str, ind: str) -> list[str]:
    s = _strip_parens(expr)
    if not has_top_comma(s):
        return [f"{ind}{var} = ({s});"]
    if (sp := _split_top_binop(s, ("||",)) or _split_top_binop(s, ("&&",))):
        return [*_emit_cond_eval(sp[1], var, ind), f"{ind}if ({'!' if sp[0] == '||' else ''}{var}) {{", *_emit_cond_eval(sp[2], var, ind + "  "), f"{ind}}}"]
    if (cm := _split_top_binop(s, (",",))):
        return [f"{ind}{_strip_parens(cm[1])};", *_emit_cond_eval(cm[2], var, ind)]
    return [f"{ind}{var} = ({s});"]


def _stmt_end(s: str, pos: int) -> int:
    while pos < len(s) and s[pos].isspace():
        pos += 1
    if s[pos:].startswith("{"):
        return match_fwd(s, pos, "{", "}") + 1
    if re.match(r"if\s*\(", s[pos:]):
        end = _stmt_end(s, match_fwd(s, s.find("(", pos)) + 1)
        return _stmt_end(s, end + em.end()) if (em := re.match(r"\s*else\b", s[end:])) else end
    return s.find(";", pos) + 1


def unroll_if_commas(code: str, used: set[str]) -> str:
    """Unroll comma-operator side-effect chains inside if (...) preserving short-circuit semantics."""
    while (masked := mask_non_code(code)) and (hit := next(((m, end) for m in re.finditer(r"\bif\s*\(", masked) if (end := match_fwd(masked, m.end() - 1)) >= 0 and has_top_comma(code[m.end():end])), None)):
        m, end = hit
        ls = code.rfind("\n", 0, m.start()) + 1
        pref, ind, then_end = code[ls:m.start()], re.match(r"[ \t]*", code[ls:m.start()]).group(0), _stmt_end(code, end + 1)
        then_s, rest, var = code[end + 1:then_end], code[then_end:], _alloc_name("cond_gate", used)
        blk = f"{ind}{{\n{ind}  bool {var} = false;\n" + "\n".join(_emit_cond_eval(code[m.end():end], var, ind + "  ")) + f"\n{ind}  if ({var}){then_s}"
        if (em := re.match(r"^\s*else\b", rest)):
            e_end = _stmt_end(rest, em.end())
            blk, rest = blk + rest[:e_end] + f"\n{ind}}}", rest[e_end:]
        else:
            blk += f"\n{ind}}}"
        code = code[:ls] + (f"{ind}else {{\n{blk}\n{ind}}}" if pref.strip() == "else" else (pref if pref.strip() else "") + blk) + rest
    return code


def reverse_yoda_cmps(code: str) -> str:
    """Flip literal-on-left comparisons (lit < expr -> expr > lit) across full code safely."""
    masked, out, pos = mask_non_code(code), [], 0
    for m in _YODA_LIT_RE.finditer(code):
        if m.start() < pos or masked[m.start(2)] == " ":
            continue
        pre = masked[:m.start()].rstrip()
        if (m.group(1).startswith("-") and pre and pre[-1] not in "(,[;=?:!&|") or (pre and pre[-1] in "*/%+-<>)]" and not pre.endswith(("&&", "||"))):
            continue
        depth, i, n = 0, m.end(), len(code)
        while i < n:
            if code[i] in ('"', "'") and masked[i] == " ":
                i += 1; continue
            ch = masked[i]
            if (ch in ")]" and depth == 0) or (depth == 0 and (ch in ",;?:=" or masked[i:i + 2] in ("&&", "||", "==", "!=", "<=", ">=") or (ch in "&|^<>" and masked[i:i + 2] not in ("<<", ">>")))):
                break
            depth += 1 if ch in "([" else (-1 if ch in ")]" else 0)
            i += 1
        if rhs := code[m.end():i].strip():
            out.append(code[pos:m.start()] + f"{rhs} {_FLIP_OP[m.group(2)]} {m.group(1)}"); pos = i
    return "".join(out) + code[pos:]


def _d0_parts(txt: str, hit_fn: Any) -> list[tuple[str, str]]:
    segs, start, d, m_t = [], 0, 0, mask_non_code(txt)
    for idx, ch in enumerate(m_t):
        if d == 0 and (oplen := hit_fn(m_t, idx)):
            segs.append((txt[start:idx], txt[idx:idx + oplen])); start = idx + oplen
        d += 1 if ch in "([" else (-1 if ch in ")]" else 0)
    return [*segs, (txt[start:], "")]


def _has_d0(txt: str, rx: str) -> bool:
    d, mt = 0, mask_non_code(txt)
    return bool(re.search(rx, "".join(ch if (d := d + (1 if ch in "([" else (-1 if ch in ")]" else 0))) == 0 and ch not in ")]" else " " for ch in mt)))


def _wrap_bit_term(t: str) -> str:
    s = t.strip()
    return f"{t[:len(t) - len(t.lstrip())]}({s}){t[len(t.rstrip()):]}" if s and _has_d0(s, r"(?<![&])&(?![&=])") and not (s.startswith("(") and match_fwd(s, 0) == len(s) - 1) else t


def parenthesize_bitwise_and(expr: str) -> str:
    """Wrap binary '&' terms inside '|' or '^' expressions while preserving formatting."""
    m_s = mask_non_code(expr)
    if "&" not in m_s or ("|" not in m_s and "^" not in m_s):
        return expr
    out, i = [], 0
    while i < len(expr):
        if m_s[i] in ("(", "[") and (end := match_fwd(expr, i, m_s[i], ")" if m_s[i] == "(" else "]")) > i:
            out.append(expr[i] + parenthesize_bitwise_and(expr[i + 1:end]) + (")" if m_s[i] == "(" else "]")); i = end + 1
        else:
            out.append(expr[i]); i += 1
    j = "".join(out)
    if not _has_d0(j, r"(?<![&])&(?![&=])") or not _has_d0(j, r"(?<![|])\|(?![|=])|\^(?!=)"):
        return j
    low_fn = lambda mt, idx: 1 if mt[idx] in ";{},?:" else next((len(op) for op in ("||", "&&", "|=", "&=", "^=", "+=", "-=", "==", "!=", "<=", ">=", "=", "<", ">") if mt.startswith(op, idx) and not (op == "=" and (mt[idx - 1:idx] in "!=<>+-|&^" or mt[idx + 1:idx + 2] == "=")) and not (op in "<>" and (mt[idx - 1:idx] == op or mt[idx + 1:idx + 2] in (op, "=")))), 0)
    res = []
    for seg, sep in _d0_parts(j, low_fn):
        if _has_d0(seg, r"(?<![&])&(?![&=])") and _has_d0(seg, r"(?<![|])\|(?![|=])|\^(?!=)"):
            for xt, x_sep in _d0_parts(seg, lambda mt, idx: 1 if mt[idx] == "^" and mt[idx + 1:idx + 2] != "=" else 0):
                res.extend([_wrap_bit_term(ot) + o_sep for ot, o_sep in _d0_parts(xt, lambda mt, idx: 1 if mt[idx] == "|" and mt[idx - 1:idx] != "|" and mt[idx + 1:idx + 2] not in "|=" else 0)] if "|" in mask_non_code(xt) else [_wrap_bit_term(xt)])
                res.append(x_sep)
        else:
            res.append(seg)
        res.append(sep)
    return "".join(res)


def _lower_pcode_ptrs_and_types(code: str, g_addrs: dict[str, int]) -> str:
    arr_pat = re.compile(r"\(\s*&\s*(" + "|".join(SCALAR_ARRAY_MAP) + r")\s*\)\s*\[")
    while (m := arr_pat.search(mask_non_code(code))) and (end := match_fwd(code, m.end() - 1, "[", "]")) >= 0:
        arr_nm, off = SCALAR_ARRAY_MAP[m.group(1)]
        code = code[:m.start()] + f"{arr_nm}[(u8)(({code[m.end():end].strip()}) + 0x{off:02x}u)]" + code[end + 1:]
    for rx, fn in (
        (r"\(\s*(?:short|s16|u16|ushort)\s*\)\s*\(\s*&\s*(g_[A-Za-z0-9_]+)\s*\+\s*([^)]+)\)", lambda c, m: f"(u16)(0x{g_addrs[m.group(1)]:04x}u + ({c[m.start(2):m.end(2)].strip()}))" if m.group(1) in g_addrs else m.group(0)),
        (r"\(\s*(?:short|s16|u16|ushort)\s*\)\s*&\s*(g_[A-Za-z0-9_]+)\b(?!\s*\[)", lambda _c, m: f"(u16)0x{g_addrs[m.group(1)]:04x}u" if m.group(1) in g_addrs else m.group(0)),
        (r"\(\s*(?:short|s16|u16|ushort)\s*\)\s*&\s*(?!(?:g_[A-Za-z0-9_]+|uintptr_t))([A-Za-z_]\w*)", lambda _c, m: f"(u16)(uintptr_t)&{m.group(1)}"),
        (r"\(\s*\*\s*\(\s*\(\s*uint8_t\s*\*\s*\)\s*&\s*\(\s*([A-Za-z_]\w*)\s*\)\s*\+\s*([01])\s*\)\s*\)", lambda _c, m: f"((u8)({m.group(1)} {'>> 8' if m.group(2)=='1' else '& 0xFFu'}))"),
    ):
        if "uint8_t" in rx:
            sub_w = re.compile(r"\(\s*\*\s*\(\s*\(\s*uint8_t\s*\*\s*\)\s*&\s*\(\s*([A-Za-z_]\w*)\s*\)\s*\+\s*([01])\s*\)\s*\)\s*=")
            while (m := sub_w.search(mask_non_code(code))) and (semi := mask_non_code(code).find(";", m.end())) >= 0:
                nm, hi, rhs = m.group(1), m.group(2) == "1", code[m.end():semi].strip()
                code = code[:m.start()] + f"{nm} = (u16)(({nm} & {'0x00FFu' if hi else '0xFF00u'}) | {'((u16)(u8)(' + rhs + ') << 8)' if hi else '(u8)(' + rhs + ')'});" + code[semi + 1:]
        code = _sub_masked(code, re.compile(rx), fn)
    for rx, fn in ((r"\bCONCAT11\s*\(", lambda a, b: f"((u16)(((u16)(u8)({a}) << 8) | (u8)({b})))"), (r"\bCARRY1\s*\(", lambda a, b: f"((u8)(((u16)(u8)({a}) + (u8)({b})) >> 8))")):
        pat = re.compile(rx)
        while (m := pat.search(mask_non_code(code))) and (end := match_fwd(code, m.end() - 1)) >= 0 and (sp := _split_top_binop(code[m.end():end], (",",))):
            code = code[:m.start()] + fn(sp[1], sp[2]) + code[end + 1:]
    for pat, rep in _TYPE_WORDS:
        code = _sub_masked(code, re.compile(pat), lambda _c, _m, r=rep: r)
    return _sub_masked(code, _PTR_CAST_RE, lambda c, m: c[m.start():m.end()] + ("(uintptr_t)" if not c[m.end():].startswith(("(uintptr_t", "sizeof", "&")) and not re.match(r"^(?:0\b|0x[0-9A-Fa-f]+\b)", c[m.end():]) and re.match(r"^(?:\(|[A-Za-z_])", c[m.end():]) else ""))


def _prune_unused_locals(body: str) -> str:
    kept, m_body = [], mask_non_code(body)
    decl_rx = r"^[ \t]+(?:u8|s8|u16|s16|u32|s32|u64|s64|bool|char|int)\s*(?:\*\s*)?([A-Za-z_]\w*)\s*(?:=\s*0\s*)?;"
    decls = [m.group(1) for m in re.finditer(decl_rx, m_body, re.M)]
    unused = {nm for nm in decls if len(re.findall(rf"\b{re.escape(nm)}\b", m_body)) == 1}
    set_only = {nm for nm in decls if sum(1 for ln in m_body.splitlines() if re.search(rf"\b{re.escape(nm)}\b", ln) and not re.match(rf"^\s*{re.escape(nm)}\s*=(?!=)", ln) and not re.match(r"^\s*(?:u8|s8|u16|s16|u32|s32|u64|s64|bool|char|int)\b", ln)) == 0} - unused
    for ln in body.splitlines():
        if (dm := re.match(decl_rx + r"\s*$", ln)) and (dm.group(1) in unused or dm.group(1) in set_only):
            continue
        kept.append(f"{am.group(1)}(void)({am.group(3).strip()});" if (am := re.match(r"^([ \t]*)([A-Za-z_]\w*)\s*=(?!=)\s*([^;]+);\s*$", ln)) and am.group(2) in set_only else ln)
    return "\n".join(kept)


def clean_function_block(blk: str, g_addrs: dict[str, int], known_globals: set[str]) -> tuple[str, dict[str, Any]]:
    """Clean one D3 function block into zero-tell D4 C11 and return rewrite telemetry."""
    doc_m = re.match(r"^\s*(/\*\*.*?\*/)\s*", blk, re.S)
    doc, rest = (doc_m.group(1), blk[doc_m.end():]) if doc_m else ("", blk)
    rest = re.sub(r"^\s*//\s*Function:[^\n]*\r?\n?|/\*\s*WARNING:.*?\*/[ \t]*\r?\n?", "", rest, flags=re.M | re.S)
    used = set(C_KEYWORDS) | known_globals | set(re.findall(r"\b[A-Za-z_]\w*\b", mask_non_code(rest)))
    code, renames, transforms = _clean_stack_and_locals(rest, used)
    code = _lower_pcode_ptrs_and_types(unroll_if_commas(code, used), g_addrs)
    if (b0 := code.find("{")) >= 0:
        code = code[:b0 + 1] + _prune_unused_locals(_LOCAL_INIT_RE.sub(r"\1\2 = 0;", code[b0 + 1:]))
        transforms.append("init_locals")
    sig_m = _SIG_RE.search(mask_non_code(code))
    ret_t, fn_name = (sig_m.group(1).strip(), sig_m.group(2).strip()) if sig_m else ("void", "unknown")
    if doc:
        doc = re.sub(r"^[ \t]*\*\s*@(?:callers|callees)\s+none[ \t]*\r?\n", "", doc, flags=re.M)
        if "* @symbol " not in doc:
            doc = doc.replace(" * @address ", f" * @symbol {fn_name}\n * @address ", 1) if " * @address " in doc else doc[:-2].rstrip() + f"\n * @symbol {fn_name}\n */"
    ret_stmt = "return;" if ret_t == "void" else "return 0;"
    for pat, rep in ((r"\bhalt_baddata\s*\(\s*\)\s*;", f"/* Unreachable: truncated ROM data boundary. */ {ret_stmt}"), (r"(\}\s*)while\s*\(\s*true\s*\)\s*;", r"\1while (1);"), (r"\bwhile\s*\(\s*true\s*\)", "for (;;)"), (r"\b([A-Za-z_]\w*(?:\[[^\]]+\])?)\s*=\s*\1\s*\+\s*(?:1|'\\x01')\s*;", r"\1++;"), (r"\b([A-Za-z_]\w*(?:\[[^\]]+\])?)\s*=\s*(?:\1\s*-\s*1|\1\s*\+\s*(?:-1|'\\xff'))\s*;", r"\1--;")):
        code = _sub_masked(code, re.compile(pat), lambda _c, m, r=rep: m.expand(r))
    code = re.sub(r"\)[ \t]*\r?\n(?:[ \t]*\r?\n)*[ \t]*\{", ") {", parenthesize_bitwise_and(reverse_yoda_cmps(code)), count=1)
    if ret_t == "void":
        code = re.sub(r"([;}])[ \t]*\r?\n[ \t]*return;[ \t]*\r?\n\}$", r"\1\n}", code)
    return (f"{doc}\n{code.lstrip()}" if doc else code.lstrip()), {"symbol": fn_name, "localRenames": renames, "transformsApplied": [*transforms, "pcode_and_ptrs", "idiomatic_flow"], "signature": f"{ret_t} {fn_name}({sig_m.group(3).strip() if sig_m else 'void'})"}
