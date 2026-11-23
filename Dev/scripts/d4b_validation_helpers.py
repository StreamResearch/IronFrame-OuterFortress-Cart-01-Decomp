# @module: IronFrame.Dev.scripts.d4b_validation_helpers
# @purpose: Pure Standard 18 v2 validators for D4b lockstep reports, spec coverage, and specification spokes
# @depends-on: json, pathlib, re, typing, export_decomp_bundle, nes_cli_common
# @exports: LEGACY_V1_KEYS, REQUIRED_D4B_CHECKS, REQUIRED_SPEC_SPOKES, has_legacy_v1, validate_d4b_lockstep_report, validate_spec_spokes_and_coverage

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from export_decomp_bundle import validate_cleanroom_bytes
from nes_cli_common import GAME_ID

LEGACY_V1_KEYS = frozenset({
    "generatedAt", "passed", "errors", "warnings", "compilerErrors", "compilerWarnings",
    "compiledFiles", "parityPassed", "parityTestsPassed", "parityTestsTotal",
    "assertionsPassed", "assertionsTotal", "matchedBinaries", "romBytes", "romMatched",
    "romCrc32", "romMd5", "romSha1", "relpath", "bytes", "sha256",
})
REQUIRED_D4B_CHECKS = (
    "scene_1_boot_and_title",
    "scene_2_intro_to_dock",
    "scene_3_dock_traversal",
    "scene_4_transceiver_and_pause",
    "scene_5_combat_action",
    "d4_clean_source_checkpoints",
    "recart_interpreter_oracle_witness",
)
REQUIRED_SPEC_SPOKES = (
    "symbol-and-bank-reference.md",
    "rooms-metatiles-and-chr-format.md",
    "guards-weapons-and-password-format.md",
    "codec-and-bank06-audio-format.md",
)
_LOCKSTEP_ALLOWED_KEYS = frozenset({
    "schemaVersion", "gameId", "generatedAtUtc", "oracleType", "mismatchedFrames",
    "isPassed", "assertionsPassedCount", "assertionsTotalCount", "checks", "notes",
})
_SPEC_COV_ALLOWED_KEYS = frozenset({
    "schemaVersion", "gameId", "generatedAtUtc", "isPassed", "totalFunctionCount",
    "namedFunctionCount", "totalGlobalCount", "mappedGlobalCount",
    "definedStructCount", "definedEnumCount", "unresolvedFieldCount",
    "assertionsPassedCount", "assertionsTotalCount", "checks", "notes",
})
_CHECK_ENTRY_KEYS = frozenset({"name", "isPassed", "detail"})
_FORBIDDEN_DUMP_KEYS = frozenset({
    "secondaryoracles", "rawram", "wramdump", "oamdump", "ppudump", "apudump",
    "ramdump", "rawwram", "memorydump", "savestate", "rambytes", "wrambytes", "frames",
})
_LARGE_HEX_RE = re.compile(r"[0-9a-fA-F]{129,}")
_SPACE_HEX_RE = re.compile(r"(?:[0-9a-fA-F]{2}\s+){32,}[0-9a-fA-F]{2}")
_EXTRA_PII_NEEDLES = ("e:" + "\\sets", "e:" + "/sets")


def has_legacy_v1(obj: Any) -> bool:
    """Return True if obj or any nested structure contains deprecated Standard 18 v1 keys."""
    if isinstance(obj, dict):
        return bool(LEGACY_V1_KEYS & set(obj)) or any(has_legacy_v1(v) for v in obj.values())
    if isinstance(obj, list):
        return any(has_legacy_v1(v) for v in obj)
    return False


def _scan_digest_only(obj: Any, path: str = "$") -> list[str]:
    errs: list[str] = []
    if isinstance(obj, dict):
        if bad_v1 := sorted(LEGACY_V1_KEYS & set(obj)):
            errs.append(f"legacy_v1:{path}:{bad_v1[0]}")
        for k, v in obj.items():
            if str(k).lower() in _FORBIDDEN_DUMP_KEYS:
                errs.append(f"forbidden_key:{path}.{k}")
            errs.extend(_scan_digest_only(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        if len(obj) > 32 and all(type(x) is int for x in obj):
            errs.append(f"raw_byte_array:{path}(len={len(obj)})")
        else:
            for idx, item in enumerate(obj):
                errs.extend(_scan_digest_only(item, f"{path}[{idx}]"))
    elif isinstance(obj, str) and (_LARGE_HEX_RE.search(obj) or _SPACE_HEX_RE.search(obj)):
        errs.append(f"raw_hex_blob:{path}")
    return errs


def _validate_checks_list(checks: Any) -> tuple[bool, dict[str, bool], str]:
    if not isinstance(checks, list) or not checks:
        return False, {}, "checks must be a non-empty list"
    status_map: dict[str, bool] = {}
    for idx, item in enumerate(checks):
        if not isinstance(item, dict):
            return False, {}, f"checks[{idx}] is not an object"
        extra = sorted(set(item) - _CHECK_ENTRY_KEYS)
        if extra:
            return False, {}, f"checks[{idx}] unregistered keys: {extra}"
        name, passed = item.get("name"), item.get("isPassed")
        if not isinstance(name, str) or not name.strip() or not isinstance(passed, bool):
            return False, {}, f"checks[{idx}] missing valid name/isPassed"
        if "detail" in item and (not isinstance(item["detail"], str) or not item["detail"].strip()):
            return False, {}, f"checks[{idx}] detail must be non-empty string"
        if name in status_map:
            return False, {}, f"duplicate check name: {name}"
        status_map[name] = passed
    if any(not ok for ok in status_map.values()):
        failed = [k for k, ok in status_map.items() if not ok]
        return False, status_map, f"failing checks: {failed[:4]}"
    return True, status_map, "ok"


def _load_json_dict(path: Path, rel_label: str) -> tuple[dict[str, Any] | None, bytes, str | None]:
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        data = json.loads(text)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, b"", f"invalid {rel_label}: {exc}"
    if not isinstance(data, dict):
        return None, b"", f"{rel_label} root must be a JSON object"
    if cr := validate_cleanroom_bytes(rel_label, raw, strict=True):
        return None, b"", f"cleanroom_leak({rel_label}): {cr[0]}"
    if any(n in text.lower() for n in _EXTRA_PII_NEEDLES):
        return None, b"", f"cleanroom_leak({rel_label}): workstation_path"
    return data, raw, None


def validate_d4b_lockstep_report(schemas_dir: Path, require_exists: bool = False) -> tuple[bool, str]:
    """Validate Dev/schemas/d4b_lockstep_report.json against Standard 18 v2 and R03 §1.1 digest-only rules."""
    fp = Path(schemas_dir) / "d4b_lockstep_report.json"
    if not fp.is_file():
        return (False, "missing d4b_lockstep_report.json") if require_exists else (True, "d4b_lockstep_report.json absent (pre-D4b baseline)")
    data, _raw, err = _load_json_dict(fp, "Dev/schemas/d4b_lockstep_report.json")
    if err or data is None:
        return False, err or "invalid json"
    if extra := sorted(set(data) - _LOCKSTEP_ALLOWED_KEYS):
        return False, f"unregistered top-level keys: {extra[:5]}"
    if dump_errs := _scan_digest_only(data):
        return False, f"digest-only/v1 violation: {dump_errs[0]}"
    if type(data.get("schemaVersion")) is not int or data["schemaVersion"] != 2 or data.get("gameId") != GAME_ID:
        return False, f"invalid schemaVersion/gameId: {data.get('schemaVersion')}/{data.get('gameId')}"
    if not isinstance(data.get("generatedAtUtc"), str) or not data["generatedAtUtc"].strip():
        return False, "missing generatedAtUtc"
    if data.get("oracleType") != "mesen":
        return False, f"invalid oracleType: {data.get('oracleType')!r}"
    if type(data.get("mismatchedFrames")) is not int or data["mismatchedFrames"] != 0:
        return False, f"mismatchedFrames={data.get('mismatchedFrames')!r} (expected 0)"
    if data.get("isPassed") is not True:
        return False, f"isPassed={data.get('isPassed')!r} (expected True)"
    p_cnt, t_cnt = data.get("assertionsPassedCount"), data.get("assertionsTotalCount")
    if type(p_cnt) is not int or type(t_cnt) is not int or p_cnt != t_cnt or p_cnt < 7:
        return False, f"invalid assertion counts: {p_cnt}/{t_cnt}"
    if "notes" in data and data["notes"] is not None and not isinstance(data["notes"], str):
        return False, "notes must be string or null"
    c_ok, status_map, c_err = _validate_checks_list(data.get("checks"))
    if not c_ok:
        return False, c_err
    if missing := [req for req in REQUIRED_D4B_CHECKS if status_map.get(req) is not True]:
        return False, f"missing required D4b checks: {missing}"
    return True, f"oracle=mesen, mismatched=0, assertions={p_cnt}/{t_cnt}, checks={len(status_map)}"


def validate_spec_spokes_and_coverage(dev_dir: Path, require_all_spokes: bool = True) -> tuple[bool, str]:
    """Validate Dev/schemas/spec_coverage.json and all 4 clean-room specification spokes."""
    dev = Path(dev_dir)
    cov_path = dev / "schemas" / "spec_coverage.json"
    if not cov_path.is_file():
        return False, "missing Dev/schemas/spec_coverage.json"
    cov, _raw, err = _load_json_dict(cov_path, "Dev/schemas/spec_coverage.json")
    if err or cov is None:
        return False, err or "invalid spec_coverage.json"
    if extra := sorted(set(cov) - _SPEC_COV_ALLOWED_KEYS):
        return False, f"spec_coverage unregistered keys: {extra[:5]}"
    if dump_errs := _scan_digest_only(cov):
        return False, f"spec_coverage violation: {dump_errs[0]}"
    base_ok = (
        type(cov.get("schemaVersion")) is int and cov["schemaVersion"] == 2
        and cov.get("gameId") == GAME_ID and cov.get("isPassed") is True
        and type(cov.get("unresolvedFieldCount")) is int and cov["unresolvedFieldCount"] == 0
        and type(cov.get("mappedGlobalCount")) is int and cov["mappedGlobalCount"] == 2324
        and cov.get("totalGlobalCount", 2324) == 2324
        and cov.get("totalFunctionCount", 499) == 499 and cov.get("namedFunctionCount", 499) == 499
    )
    if not base_ok:
        return False, f"spec_coverage invalid counts/header: unres={cov.get('unresolvedFieldCount')}, g={cov.get('mappedGlobalCount')}, pass={cov.get('isPassed')}"
    if "checks" in cov:
        c_ok, _smap, c_err = _validate_checks_list(cov["checks"])
        if not c_ok:
            return False, f"spec_coverage {c_err}"
    if "assertionsPassedCount" in cov or "assertionsTotalCount" in cov:
        p_cnt, t_cnt = cov.get("assertionsPassedCount"), cov.get("assertionsTotalCount")
        if type(p_cnt) is not int or type(t_cnt) is not int or p_cnt != t_cnt or p_cnt <= 0:
            return False, f"spec_coverage invalid assertions: {p_cnt}/{t_cnt}"

    errs: list[str] = []
    seen = 0
    for name in REQUIRED_SPEC_SPOKES:
        sp_path = dev / "docs" / "specifications" / name
        if not sp_path.is_file():
            if require_all_spokes:
                errs.append(f"missing_spoke:{name}")
            continue
        seen += 1
        raw = sp_path.read_bytes()
        text = raw.decode("utf-8", errors="replace")
        lines = text.splitlines()
        if len(lines) < 20 or not any(ln.strip() for ln in lines):
            errs.append(f"short_spoke:{name}({len(lines)}<20)")
        cr = validate_cleanroom_bytes(f"Dev/docs/specifications/{name}", raw, strict=True)
        if cr or any(n in text.lower() for n in _EXTRA_PII_NEEDLES):
            errs.append(f"cleanroom_leak:{name}({cr[0] if cr else 'workstation_path'})")
    if errs:
        return False, "; ".join(errs[:5])
    return True, f"mappedGlobals=2324, unresolved=0, spokes={seen}/4, cleanroom_spokes_ok=True"
