# @module: IronFrame.Dev.scripts.package_release
# @purpose: Clean-room Tier R release packager and 10-invariant stage auditor
# @depends-on: argparse, json, os, re, shutil, subprocess, sys, tempfile, zipfile, pathlib, typing, nes_cli_common, export_decomp_bundle
# @exports: resolve_release_metadata, build_source_zip, audit_release_stage, package_release, main

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any
import zipfile

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import export_decomp_bundle as edb  # noqa: E402
import nes_cli_common as ncc  # noqa: E402

_ROOT_WHITELIST = ("README.md", "FEATURES.md", "ROADMAP.md", "CHANGELOG.md", "SECURITY.md", "CONTRIBUTING.md", "LICENSE", ".gitignore", ".gitattributes", "active.state")
_EXCLUDED_DEV_DIRS = frozenset({"__pycache__", ".pytest_cache", ".git", "corpus", "archive", "data", "logs"})
_EXCLUDED_DOCS_SUBDIRS = frozenset({"plans", "reports", "tests", "archive"})
_FORBIDDEN_NAME_TOKENS = ("harvest", "moon", "play" + "station", "kings" + "field", "metal" + "gear", "super" + "battleship", "quarter" + "back")
_SHA_LINE_RE = re.compile(r"^([0-9a-f]{64})  ([^\r\n]+)$")
_ZIP_DATE, _DOCS_SYNC = (2026, 11, 20, 0, 0, 0), ("README.md", "FEATURES.md", "CHANGELOG.md")
_SKIP_REL_EXTS = edb._SKIP_EXTS | {".decomp"}


def _find_7z() -> Path | None:
    pf = os.environ.get("ProgramFiles", "").strip()
    cands = [shutil.which("7z"), str(Path(pf) / "7-Zip" / "7z.exe") if pf else ""]
    return next((Path(c) for c in cands if c and Path(c).is_file()), None)


def resolve_release_metadata(repo_root: Path) -> dict[str, str]:
    """Load canonical release naming and SemVer metadata from recipe, state, and manifest."""
    root = Path(repo_root).resolve()
    load = lambda rel: json.loads((root / rel).read_text(encoding="utf-8"))
    recipe, state, manifest = load("Dev/schemas/decomp_recipe.json"), load("active.state"), load("Dev/research.manifest.json")
    pkg = str(recipe.get("packageFileName") or f"{root.name}.decomp").strip()
    slug = str(recipe.get("upstreamResearchPath") or root.name).strip()
    ver = str(recipe.get("packageVersion") or "").strip()
    wrap = f"{slug}-v{ver}"
    return {
        "packageFileName": pkg, "repoSlug": slug, "version": ver, "title": str(recipe.get("title") or slug).strip(),
        "moduleId": str(recipe.get("moduleId") or "").strip(), "stateVersion": str(state.get("version") or "").strip(),
        "manifestVersion": str(manifest.get("version") or "").strip(), "wrapPrefix": wrap,
        "zipName": f"{wrap}.zip", "src7zName": f"{wrap}-src.7z",
    }


def _is_excluded_rel(rel_posix: str) -> bool:
    parts = [p.lower() for p in PurePosixPath(rel_posix).parts]
    if parts[-1] == "agents.md" or parts[-1] in edb._OS_JUNK_NAMES or parts[-1].startswith("._"):
        return True
    if any(p in _EXCLUDED_DEV_DIRS for p in parts[:-1]):
        return True
    if len(parts) >= 4 and parts[0] == "dev" and parts[1] == "docs" and parts[2] in _EXCLUDED_DOCS_SUBDIRS:
        return True
    return PurePosixPath(rel_posix).suffix.lower() in _SKIP_REL_EXTS


def _validate_release_entry(rel_posix: str, payload: bytes) -> list[str]:
    norm = rel_posix.replace("\\", "/")
    parts = [p.lower() for p in PurePosixPath(norm).parts]
    ok_docs = len(parts) >= 3 and parts[0] == "dev" and parts[1] == "docs" and (len(parts) == 3 or parts[2] not in _EXCLUDED_DOCS_SUBDIRS)
    return [
        err for err in edb.validate_cleanroom_bytes(norm, payload)
        if not (err == f"forbidden_ext:{norm}" and norm.lower() == "active.state")
        and not (err == f"forbidden_path:{norm}" and ok_docs and not any(t in norm.lower() for t in edb._FORBIDDEN_TOKENS))
    ]


def _collect_release_files(repo_root: Path, meta: dict[str, str]) -> list[tuple[str, bytes]]:
    cands = [(n, repo_root / n) for n in (*_ROOT_WHITELIST, meta["packageFileName"]) if (repo_root / n).is_file()]
    for sub in ("Dev", ".github"):
        if (repo_root / sub).is_dir():
            cands.extend((fp.relative_to(repo_root).as_posix(), fp) for fp in (repo_root / sub).rglob("*") if fp.is_file() and not _is_excluded_rel(fp.relative_to(repo_root).as_posix()))
    entries, violations = [], []
    for rel, fp in sorted(cands, key=lambda item: item[0]):
        data = fp.read_bytes()
        errs = edb.validate_cleanroom_archive(fp) if rel == meta["packageFileName"] else _validate_release_entry(rel, data)
        violations.extend(errs) if errs else entries.append((rel, data))
    if violations:
        raise ValueError(f"Release clean-room check failed: {'; '.join(violations[:8])}")
    return entries


def build_source_zip(repo_root: Path, dest_zip: Path, meta: dict[str, str]) -> list[str]:
    """Assemble wrapped clean-room release ZIP excluding AGENTS.md, duplicate .decomp, and local-only folders."""
    entries, dest = _collect_release_files(Path(repo_root).resolve(), meta), Path(dest_zip).resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp, wrap, arcnames = dest.with_suffix(dest.suffix + ".tmp"), meta["wrapPrefix"], []
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel_posix, payload in entries:
            arcname = f"{wrap}/{rel_posix}"
            zi = zipfile.ZipInfo(arcname, date_time=_ZIP_DATE)
            zi.compress_type, zi.external_attr = zipfile.ZIP_DEFLATED, 0o644 << 16
            zf.writestr(zi, payload)
            arcnames.append(arcname)
    os.replace(tmp, dest)
    return arcnames


def _audit_zip_entries(zip_path: Path, latest_decomp: Path, repo_root: Path, meta: dict[str, str]) -> list[str]:
    issues, wrap_prefix, by_hash, decomps = [], f"{meta['wrapPrefix']}/", {}, []
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = [i.filename for i in zf.infolist() if not i.is_dir()]
        if bad := [n for n in names if not n.startswith(wrap_prefix) or "\\" in n or ".." in PurePosixPath(n).parts]:
            issues.append(f"zip_wrapper_violation:{bad[:3]}")
        for name in names:
            payload = zf.read(name)
            if payload:
                by_hash.setdefault(ncc.sha256_bytes(payload), []).append(name)
            if name.lower().endswith(".decomp"):
                decomps.append(name)
            inner = name[len(wrap_prefix):] if name.startswith(wrap_prefix) else name
            if inner != meta["packageFileName"] and _is_excluded_rel(inner):
                issues.append(f"zip_excluded_leak:{inner}")
            if inner != meta["packageFileName"]:
                issues.extend(_validate_release_entry(inner, payload))
        if decomps != [f"{wrap_prefix}{meta['packageFileName']}"]:
            issues.append(f"zip_decomp_count_or_path:{decomps}")
        elif latest_decomp.is_file() and ncc.sha256_bytes(zf.read(decomps[0])) != ncc.sha256_bytes(latest_decomp.read_bytes()):
            issues.append("zip_decomp_mismatch_with_latest")
        if dups := [p for p in by_hash.values() if len(p) > 1]:
            issues.append(f"zip_duplicate_payloads:{dups[:3]}")
        name_set = set(names)
        issues.extend(f"zip_doc_drift:{d}" for d in _DOCS_SYNC if f"{wrap_prefix}{d}" not in name_set or not (repo_root / d).is_file() or zf.read(f"{wrap_prefix}{d}") != (repo_root / d).read_bytes())
    return issues


def _audit_7z_archives(out_dir: Path, version: str, expected_names: set[str]) -> list[str]:
    v_7z, l_7z = out_dir / f"v{version}.7z", out_dir / "Latest.7z"
    if not (v_7z.is_file() and l_7z.is_file()):
        return ["missing_7z_archive"]
    issues = ["7z_latest_version_mismatch"] if v_7z.read_bytes() != l_7z.read_bytes() else []
    if (seven_z := _find_7z()) is None:
        return issues + ["missing_7z_binary"]
    res = subprocess.run([str(seven_z), "l", "-slt", str(l_7z)], capture_output=True, text=True, check=False)
    if res.returncode != 0:
        return issues + [f"7z_list_failed:{res.returncode}"]
    lines = res.stdout.splitlines()
    after = lines[lines.index("----------") + 1:] if "----------" in lines else []
    listed = {ln.split(" = ", 1)[1].strip() for ln in after if ln.startswith("Path = ")}
    return issues + ([f"7z_entry_mismatch:{sorted(listed)}"] if listed != expected_names else [])


def audit_release_stage(out_dir: Path, repo_root: Path, check_7z: bool = True, forbidden_name_tokens: tuple[str, ...] = _FORBIDDEN_NAME_TOKENS) -> list[str]:
    """Enforce all 10 release-stage invariants on a staged Tier R release directory."""
    out, root = Path(out_dir).resolve(), Path(repo_root).resolve()
    meta = resolve_release_metadata(root)
    issues = [] if len({meta["version"], meta["stateVersion"], meta["manifestVersion"]}) == 1 and meta["version"] else [f"version_lockstep_mismatch:{meta['version']}/{meta['stateVersion']}/{meta['manifestVersion']}"]
    latest, expected = out / "Latest", {*_DOCS_SYNC, "RELEASE_NOTES.md", "SHA256SUMS.txt", meta["packageFileName"], meta["zipName"]}
    if not latest.is_dir():
        return issues + ["missing_latest_dir"]
    children = list(latest.iterdir())
    if any(c.is_dir() for c in children) or {c.name for c in children} != expected:
        issues.append(f"latest_payload_mismatch:{sorted(c.name for c in children)}")
    sum_map: dict[str, str] = {}
    if (latest / "SHA256SUMS.txt").is_file():
        lines = [ln for ln in (latest / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines() if ln.strip()]
        for ln in lines:
            if m := _SHA_LINE_RE.match(ln):
                sum_map[m.group(2)] = m.group(1)
            else:
                issues.append(f"invalid_sha256_line:{ln}")
        if set(sum_map) != (expected - {"SHA256SUMS.txt"}) or len(lines) != 6:
            issues.append(f"sha256_entry_set_mismatch:{sorted(sum_map)}")
        issues.extend(f"sha256_digest_mismatch:{f}" for f, d in sum_map.items() if not (latest / f).is_file() or ncc.sha256_bytes((latest / f).read_bytes()) != d)
    issues.extend(f"uncoded_filename:{fn}" for fn in sorted({c.name for c in children} | set(sum_map) | {meta["packageFileName"], meta["zipName"]}) if any(t in fn.lower() for t in forbidden_name_tokens))
    issues.extend(f"latest_doc_drift:{d}" for d in _DOCS_SYNC if not ((latest / d).is_file() and (root / d).is_file() and (latest / d).read_bytes() == (root / d).read_bytes()))
    decomp_path, zip_path = latest / meta["packageFileName"], latest / meta["zipName"]
    if decomp_path.is_file():
        issues.extend(f"decomp:{v}" for v in edb.validate_cleanroom_archive(decomp_path))
    if zip_path.is_file():
        issues.extend(_audit_zip_entries(zip_path, decomp_path, root, meta))
    return issues + (_audit_7z_archives(out, meta["version"], expected) if check_7z else [])


def _run_7z(seven_z: Path, archive_path: Path, cwd: Path, items: list[str]) -> None:
    tmp = archive_path.with_suffix(".tmp.7z")
    tmp.unlink(missing_ok=True)
    res = subprocess.run([str(seven_z), "a", "-t7z", "-mx=9", "-y", str(tmp), *items], cwd=cwd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"7z failed ({archive_path.name}): {res.stderr or res.stdout}")
    os.replace(tmp, archive_path)


def package_release(
    out_dir: Path, repo_root: Path | None = None, release_notes_path: Path | None = None,
    log_dir: Path | None = None, skip_export: bool = False, make_7z: bool = True, verify_only: bool = False,
) -> dict[str, Any]:
    """Stage and verify a clean-room Tier R release mirror (ZIP, .decomp, SHA256SUMS, and optional .7z)."""
    root, out = Path(repo_root).resolve() if repo_root else REPO_ROOT, Path(out_dir).resolve()
    meta = resolve_release_metadata(root)
    if not verify_only:
        if not skip_export:
            edb.export_decomp_bundle(repo_root=root, verify_cleanroom=True)
        latest = out / "Latest"
        shutil.rmtree(latest, ignore_errors=True)
        latest.mkdir(parents=True, exist_ok=True)
        for name in (*_DOCS_SYNC, meta["packageFileName"]):
            shutil.copy2(root / name, latest / name)
        shutil.copy2(Path(release_notes_path).resolve(), latest / "RELEASE_NOTES.md") if release_notes_path else (latest / "RELEASE_NOTES.md").write_text(f"# {meta['title']} Decomp v{meta['version']} (Beta) Release Notes\n", encoding="utf-8", newline="\n")
        build_source_zip(root, latest / meta["zipName"], meta)
        sum_names = sorted((*_DOCS_SYNC, "RELEASE_NOTES.md", meta["packageFileName"], meta["zipName"]))
        (latest / "SHA256SUMS.txt").write_text("".join(f"{ncc.sha256_bytes((latest / n).read_bytes())}  {n}\n" for n in sum_names), encoding="utf-8", newline="\n")
        if make_7z:
            if (seven_z := _find_7z()) is None:
                raise RuntimeError("7z CLI not found; pass --no-7z or install 7-Zip.")
            _run_7z(seven_z, out / f"v{meta['version']}.7z", latest, sorted([*sum_names, "SHA256SUMS.txt"]))
            shutil.copy2(out / f"v{meta['version']}.7z", out / "Latest.7z")
            with tempfile.TemporaryDirectory() as tmp_src:
                for rel_posix, payload in _collect_release_files(root, meta):
                    dest = Path(tmp_src) / meta["wrapPrefix"] / rel_posix
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(payload)
                _run_7z(seven_z, out / meta["src7zName"], Path(tmp_src), [meta["wrapPrefix"]])
    violations, zip_file = audit_release_stage(out, root, check_7z=make_7z), out / "Latest" / meta["zipName"]
    report = {
        "schemaVersion": 2, "isPassed": not violations, "version": meta["version"], "repoSlug": meta["repoSlug"],
        "packageFileName": meta["packageFileName"], "zipName": meta["zipName"],
        "sha256Hex": ncc.sha256_bytes(zip_file.read_bytes()) if zip_file.is_file() else "",
        "violations": violations, "generatedAtUtc": ncc.utc_now_iso(),
    }
    ncc.write_json_log(log_dir, "package_release", report)
    if violations:
        raise ValueError(f"Release audit failed: {'; '.join(violations[:8])}")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage and verify a clean-room Tier R release bundle.")
    parser.add_argument("--out-dir", type=Path, required=True, help="Output staging directory.")
    parser.add_argument("--repo-root", type=Path, default=None, help="Repository root override.")
    parser.add_argument("--release-notes", type=Path, default=None, help="Path to RELEASE_NOTES.md.")
    parser.add_argument("--log-dir", type=Path, default=None, help="Optional directory for package_release.log.")
    parser.add_argument("--skip-export", action="store_true", help="Skip re-exporting root .decomp bundle.")
    parser.add_argument("--no-7z", action="store_true", help="Skip .7z archive creation and audit.")
    parser.add_argument("--verify-only", action="store_true", help="Only audit an existing staged release directory.")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(package_release(args.out_dir, args.repo_root, args.release_notes, args.log_dir, args.skip_export, not args.no_7z, args.verify_only), indent=2))
        return 0
    except Exception as exc:
        err = {"schemaVersion": 2, "isPassed": False, "errorCode": "RELEASE_PACKAGE_FAILED", "errorMessage": str(exc), "generatedAtUtc": ncc.utc_now_iso()}
        ncc.write_json_log(args.log_dir, "package_release", err)
        print(json.dumps(err, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
