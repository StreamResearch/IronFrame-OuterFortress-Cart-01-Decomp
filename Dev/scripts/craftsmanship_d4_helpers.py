# @module: IronFrame.Dev.scripts.craftsmanship_d4_helpers
# @purpose: Shared C span utilities, D4 block extraction, strict SixTell detector, and schema/config validators
# @depends-on: json, pathlib, re, typing, nes_cli_common
# @exports: STRICT_D4_FLAGS, C_KEYWORDS, code_spans, map_code, mask_non_code, match_fwd, match_back, has_top_comma, extract_d4_func_blocks, find_d4_craftsmanship_tells, count_d4_craftsmanship_tells, is_clangd_clean, validate_d4_rewrites_dir

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

import nes_cli_common as ncc

STRICT_D4_FLAGS = [
    "-std=gnu11", "-fsigned-char", "-O1", "-ffreestanding", "-fno-builtin",
    "-Wall", "-Wextra", "-Wno-unused-parameter",
]
C_KEYWORDS = frozenset(
    "auto break case char const continue default do double else enum extern float for goto if inline int "
    "long register restrict return short signed sizeof static struct switch typedef union unsigned void "
    "volatile while bool true false NULL u8 u16 u32 u64 s8 s16 s32 s64 uintptr_t uint8_t uint16_t uint32_t "
    "int8_t int16_t int32_t nes_addr_t".split()
)
EXPECTED_SHARDS = (
    "core_runtime.json", "core_gameplay.json", "overlays_b00_b02.json",
    "overlays_b03_b04.json", "overlays_b05_b06.json",
)
_DOM_PFX = frozenset(
    "bank rom prg chr ppu apu pad joy pulse channel track voice stage level room world area "
    "sprite actor slot timer frame nametable palette tile irq nmi mmc port player bit".split()
)
_DOC_BLK_RE = re.compile(r"/\*\*.*?\*/", re.S)
_DOC_SYM_RE = re.compile(r"^\s*\*\s*@symbol\s+([A-Za-z_]\w*)\b", re.M)
_DOC_ADDR_RE = re.compile(r"^\s*\*\s*@address\s+0x([0-9a-fA-F]+)\b", re.M)
_D3_HDR_RE = re.compile(r"^// Function:\s+(\S+)\s+@\s+0x([0-9a-fA-F]+)", re.M)
_BOILER_RE = re.compile(r"/\*\s*WARNING:|^\s*//\s*Function:|^\s*\*\s*@(?:callers|callees)\s+none\b", re.M)
_DECL_RE = re.compile(
    r"(?:^|[;(,])\s*(?:const\s+|volatile\s+|unsigned\s+|signed\s+|register\s+|static\s+|struct\s+)*"
    r"(?!return\b|goto\b|else\b|case\b|typedef\b)[A-Za-z_]\w*(?:\s*\*+)?\s+([A-Za-z_]\w*)\s*(?=[=;,)\[])", re.M,
)
_SSA_RE = re.compile(r"^([A-Za-z_]\w*?)_(?:0\d|[2-9]\d*)$")
_SHORT_VAR_RE = re.compile(r"^[va][1-9]\d*$")
_PLACEHOLDER_RE = re.compile(
    r"\b(?:tmp_?\d+|temp_?\d+|var_?\d+|val_?\d+|arg_?\d+|ret_val\d*|work_word|work_acc|status_flags"
    r"|tmp_val|accum_val|reg_val|slot_val|ctx_val|abi_val|byte_[0-9A-Fa-f]+|word_[0-9A-Fa-f]+"
    r"|dword_[0-9A-Fa-f]+|off_[0-9A-Fa-f]+|unk_[0-9A-Za-z_]+|fn_\d+|func_?\d+)\b"
)
_TELL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("undef_types", re.compile(r"\bundefined(?:1|2|3|4|8)?\b")),
    ("pcode_macros", re.compile(r"\b(?:CONCAT(?:11|12|13|21|22|31|44)|SUB(?:21|31|32|41|42|81|82|84)|ZEXT(?:12|13|14|23|24)|SEXT(?:12|13|14|23|24)|(?:SCARRY|SBORROW|CARRY)[12]|POPCOUNT|BADSPACEBASE)\b")),
    ("raw_locals", re.compile(r"\b(?:[apbcsuilf]+Var\d+|pcVar\d+|pp?[A-Za-z]?Var\d+|[ubcs]Stack[0-9A-Za-z_]*|stack0x[0-9A-Fa-f]+|_?local_[0-9A-Za-z_]+|extraout_[A-Za-z0-9_]+|unaff_[A-Za-z0-9_]+|in_(?:[A-Z][A-Za-z0-9_]*|stack_[0-9A-Za-z_]+|register_[0-9A-Za-z_]+)|param_?\d+)\b")),
    ("raw_symbols", re.compile(r"\b(?:FUN|DAT|UNK|PTR|LAB|SUB|switchD)_[0-9A-Za-z_]+\b|\b(?:sub|loc)_[0-9A-Fa-f]+\b|\b(?:code|joined)_r0x[0-9A-Fa-f]+\b|\bcode\s*\*|\(\s*void\s*\*\s*\)\s*0x0\b|\bhalt_baddata\b")),
    ("ptr_arithmetic", re.compile(r"&\s*g_[A-Za-z0-9_]+(?:\s*\))?\s*[+-](?![>=\-])|\*\s*\([^);]+\*\)\s*&\s*(?:\(|g_[A-Za-z0-9_]+|[A-Za-z_]\w*\s*(?:\.|->|\[))")),
    ("shift_signext", re.compile(r"(?:<<|\*)\s*(?:16|24|0x10|0x18|0x10000|0x1000000)[uUlL]*[\s\)]*>>\s*(?:16|24|0x10|0x18)\b")),
    ("unidiomatic_flow", re.compile(r"\bwhile\s*\(\s*true\s*\)|\bgoto\s+(?:LAB|loc|L)_[0-9A-Za-z_]+\s*;|\b([A-Za-z_]\w*(?:\.[A-Za-z_]\w*|->[A-Za-z_]\w*){0,3})\s*(?<![!<>])=\s*\1\s*[+-]\s*1\s*;")),
    ("yoda_cmp", re.compile(r"(?<![A-Za-z0-9_.\-+])(?:0x[0-9A-Fa-f]+|-?\d+|'(?:\\.|[^'\\])')\s*(?<![<>])(?:<=|>=|<|>)(?![<>=])\s*[A-Za-z_]\w*")),
    ("abi_tells", re.compile(r"\b(?:__stdcall|__cdecl|__fastcall|__thiscall|WINAPI|APIENTRY)\b|\(\s*(?:uintptr_t|intptr_t|uint64_t|u64)\s*\)\s*0x[0-9A-Fa-f]{4}\b|\(\s*(?:volatile\s+)?(?:u?int(?:16|32|64)_t|[us](?:16|32|64)|ushort|uint|ulong)\s*\*\s*\)\s*0x(?:200[0-7]|40[01][0-9A-Fa-f])\b")),
)
_CBODY_RE = re.compile(r"\b(?:void|int|uint|short|ushort|char|long|byte|u8|s8|u16|u32|uint8_t|uint16_t|uint32_t|int32_t)\s+[A-Za-z_]\w*\s*\([^;{]*\)\s*\{")
_BRAND_WORDS = ("kon" + "ami", "metal" + "gear", "metal " + "gear")
_FRAG_RE = re.compile(r"_(?:0[1-9]|[1-9]\d+)\.c$", re.I)


def code_spans(text: str) -> list[tuple[int, int, bool]]:
    """Split C source into (start, end, is_code) spans excluding comments and string literals."""
    spans, i, n, cur = [], 0, len(text), 0
    while i < n:
        ch, nxt = text[i], text[i + 1] if i + 1 < n else ""
        if ch == "/" and nxt in ("/", "*"):
            if i > cur:
                spans.append((cur, i, True))
            j = text.find("\n" if nxt == "/" else "*/", i + 2)
            j = n if j < 0 else (j if nxt == "/" else j + 2)
            spans.append((i, j, False))
            i = cur = j
        elif ch in ('"', "'"):
            if i > cur:
                spans.append((cur, i, True))
            j = i + 1
            while j < n:
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == ch:
                    j += 1
                    break
                j += 1
            spans.append((i, j, False))
            i = cur = j
        else:
            i += 1
    if cur < n:
        spans.append((cur, n, True))
    return spans


def map_code(text: str, fn: Any) -> str:
    """Apply transform fn exclusively to non-comment/non-string C spans."""
    return "".join(fn(text[s:e]) if is_c else text[s:e] for s, e, is_c in code_spans(text))


def mask_non_code(text: str) -> str:
    """Replace comments and literals with spaces while preserving line counts."""
    chars = list(text)
    for s, e, is_c in code_spans(text):
        if not is_c:
            for k in range(s, e):
                if chars[k] != "\n":
                    chars[k] = " "
    return "".join(chars)


def match_fwd(s: str, open_idx: int, lo: str = "(", hi: str = ")") -> int:
    """Return index of matching closing delimiter for s[open_idx] == lo, ignoring strings."""
    depth, i, n = 0, open_idx, len(s)
    while i < n:
        ch = s[i]
        if ch in ('"', "'"):
            i += 1
            while i < n:
                if s[i] == "\\":
                    i += 2
                    continue
                if s[i] == ch:
                    break
                i += 1
        elif ch == lo:
            depth += 1
        elif ch == hi:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def match_back(s: str, close_idx: int, lo: str = "(", hi: str = ")") -> int:
    """Return index of matching opening delimiter for s[close_idx] == hi."""
    depth = 0
    for idx in range(close_idx, -1, -1):
        depth += 1 if s[idx] == hi else (-1 if s[idx] == lo else 0)
        if depth == 0:
            return idx
    return -1


def extract_d4_func_blocks(text: str) -> list[tuple[int, str, str]]:
    """Extract (address, name, block_text) for both D4 @symbol/@address and D3 // Function blocks."""
    starts: list[tuple[int, int, str]] = []
    for m in _DOC_BLK_RE.finditer(text):
        blk = m.group(0)
        if (sm := _DOC_SYM_RE.search(blk)) and (am := _DOC_ADDR_RE.search(blk)):
            starts.append((m.start(), int(am.group(1), 16), sm.group(1)))
    if not starts:
        pos = [m.start() for m in _D3_HDR_RE.finditer(text)]
        for i, idx in enumerate(pos):
            prev = pos[i - 1] if i > 0 else 0
            doc = text.rfind("\n/**", prev, idx)
            st = doc + 1 if (doc >= 0 and "*/" in text[doc:idx]) else (text.find("/**") if (i == 0 and text.lstrip().startswith("/**") and "*/" in text[:idx]) else idx)
            if m := _D3_HDR_RE.search(text, idx):
                starts.append((st, int(m.group(2), 16), m.group(1)))
    return [(addr, nm, text[st:(starts[i + 1][0] if i + 1 < len(starts) else len(text))].strip()) for i, (st, addr, nm) in enumerate(starts)]


def has_top_comma(expr: str) -> bool:
    """Return True if expr contains a comma operator outside function-call argument lists."""
    s, depth, call_d, i = mask_non_code(expr), 0, [], 0
    while i < len(s):
        ch = s[i]
        if ch in ("(", "["):
            depth += 1
            if ch == "(" and (km := re.search(r"([A-Za-z_]\w*)$", s[:i].rstrip())) and km.group(1) not in ("if", "while", "return", "sizeof"):
                call_d.append(depth)
        elif ch in (")", "]"):
            if call_d and call_d[-1] == depth:
                call_d.pop()
            depth -= 1
        elif ch == "," and not call_d:
            return True
        i += 1
    return False


def _has_comma_in_if(stripped: str) -> int:
    return sum(1 for m in re.finditer(r"\bif\s*\(", stripped) if (end := match_fwd(stripped, m.end() - 1)) >= 0 and has_top_comma(stripped[m.end():end]))


def find_d4_craftsmanship_tells(text: str, is_header: bool = False) -> dict[str, int]:
    """Count all 6 Standard R02 / SixTellDetector tell families in one C or header string."""
    counts: dict[str, int] = {}
    def add(k: str, n: int) -> None:
        if n > 0:
            counts[k] = counts.get(k, 0) + n

    add("ghidra_comments", len(_BOILER_RE.findall(text)))
    if any(f in text for f in ("-Wno-everything", "-Wno-all")) or re.search(r"#\s*pragma\s+(?:clang|GCC)\s+diagnostic\s+ignored", text):
        add("banned_suppression", 1)
    stripped = mask_non_code(text)
    for key, rx in _TELL_PATTERNS:
        add(key, len(rx.findall(stripped)))
    add("comma_in_if", _has_comma_in_if(stripped))
    add("placeholders", len(_PLACEHOLDER_RE.findall(stripped)))
    decls = [m.group(1) for m in _DECL_RE.finditer(stripped) if m.group(1) not in C_KEYWORDS]
    add("hexrays_short", 1 if sum(1 for d in decls if _SHORT_VAR_RE.match(d)) >= 2 else 0)
    add("ssa_suffix", sum(1 for d in decls if (sm := _SSA_RE.match(d)) and not any(sm.group(1).lower() == p or sm.group(1).lower().startswith(p + "_") for p in _DOM_PFX)))
    lines, s_lines = text.splitlines(), stripped.splitlines()
    if not any(ln.strip().startswith(("//", "/*", "*")) and not _BOILER_RE.search(ln) for ln in lines[:16] if ln.strip()):
        add("missing_header", 1)
    if not is_header:
        c_cnt = sum(1 for ln in s_lines if ln.strip() and not ln.lstrip().startswith("#"))
        cmt_cnt = sum(1 for ln in lines if ("//" in ln or "/*" in ln) and not _BOILER_RE.search(ln))
        if c_cnt > 35 and cmt_cnt <= 1:
            add("missing_comments", 1)
    return counts


def is_clangd_clean(tree_dir: Path) -> bool:
    """Return True when .clangd and compile_commands.json pass strict D4 warning and target ABI rules."""
    cl_p, cdb_p = Path(tree_dir) / ".clangd", Path(tree_dir) / "compile_commands.json"
    if not cl_p.is_file() or not cdb_p.is_file():
        return False
    cl_txt, cdb_txt = cl_p.read_text(encoding="utf-8", errors="replace"), cdb_p.read_text(encoding="utf-8", errors="replace")
    joined = cl_txt + "\n" + cdb_txt
    if any(b in joined for b in ("-Wno-everything", "-Wno-all", "Suppress:")) or re.search(r'(?:^|[\s"\',=\[])-w(?=$|[\s"\',\];])', joined):
        return False
    if re.search(r'(?:--target=|-target["\',\s-]+)(?:x86_64|amd64|aarch64|arm64|win64|x64)\b|-m64\b', joined, re.I):
        return False
    return all(f in cl_txt and f in cdb_txt for f in ("-Wall", "-Wextra", "-Wno-unused-parameter"))


def count_d4_craftsmanship_tells(tree_dir: Path) -> tuple[int, dict[str, int]]:
    """Scan all .c/.h files and build configs under tree_dir; return (total_tells, per_category)."""
    root, totals = Path(tree_dir), {}
    for fp in sorted(root.rglob("*")):
        if not fp.is_file() or fp.suffix.lower() not in (".c", ".h"):
            continue
        if fp.suffix.lower() == ".c" and _FRAG_RE.search(fp.name):
            totals["split_fragment"] = totals.get("split_fragment", 0) + 1
        for k, v in find_d4_craftsmanship_tells(fp.read_text(encoding="utf-8", errors="replace"), is_header=(fp.suffix.lower() == ".h")).items():
            totals[k] = totals.get(k, 0) + v
    if not is_clangd_clean(root):
        totals["config_suppression"] = 1
    return sum(totals.values()), totals


def validate_d4_rewrites_dir(rewrites_dir: Path) -> tuple[bool, dict[str, Any]]:
    """Validate all 5 Standard 18 v2 zero-body JSON shards under Dev/schemas/d4_rewrites/."""
    rdir, files_seen, sym_total, errs = Path(rewrites_dir), 0, 0, []
    for name in EXPECTED_SHARDS:
        fp = rdir / name
        if not fp.is_file():
            errs.append(f"missing:{name}")
            continue
        raw = fp.read_text(encoding="utf-8")
        low = raw.lower()
        if '"cbody"' in low or '"functionbody"' in low or _CBODY_RE.search(raw) or any(b in low for b in _BRAND_WORDS):
            errs.append(f"cleanroom_leak:{name}")
        data = json.loads(raw)
        if data.get("schemaVersion") != 2 or data.get("gameId") != ncc.GAME_ID or not data.get("isZeroDecompilerTellsVerified") or not data.get("isZeroWarningsVerified"):
            errs.append(f"invalid_header:{name}")
        files_seen += int(data.get("fileCount", 0))
        sym_total += int(data.get("symbolCount", 0))
    return (not errs and files_seen == 26 and sym_total >= 499), {"fileCount": files_seen, "symbolCount": sym_total, "errors": errs}
