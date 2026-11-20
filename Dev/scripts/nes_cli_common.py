# @module: IronFrame.Dev.scripts.nes_cli_common
# @purpose: Shared standalone layout discovery, CLI log/media helpers, hashing, and Standard 18 v2 utilities
# @depends-on: dataclasses, datetime, hashlib, json, os, pathlib, shutil, sys, typing, zlib
# @exports: GAME_ID, TrackPaths, resolve_paths, utc_now_iso, sha256_bytes, sha256_file, crc32_hex, write_json_log, missing_media_payload, iter_integrity_entries, resolve_optional_rd_tools, detect_host_zig_target, resolve_zig_executable

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any
import zlib

GAME_ID = "ironframe-outerfortress-cart-01"


@dataclass(frozen=True)
class TrackPaths:
    """Resolved standalone Tier R workspace and optional local Corpus paths."""

    project_root: Path
    dev_dir: Path
    schemas_dir: Path
    scripts_dir: Path
    docs_dir: Path
    corpus_root: Path
    standalone_dir: Path
    readable_dir: Path
    work_dir: Path
    manifest_path: Path


def resolve_paths(repo_root: Path | None = None, data_dir: Path | None = None) -> TrackPaths:
    """Resolve repo paths strictly standalone with optional isolated --data-dir override."""
    root = Path(repo_root).resolve() if repo_root else Path(__file__).resolve().parents[2]
    dev = root / "Dev"
    if data_dir is not None:
        base = Path(data_dir).resolve()
        standalone = base if (base / "extracted").is_dir() else (base / "standalone")
        corpus, readable, work = base, base / "readable", base / "work"
    else:
        corpus = root / "Corpus"
        standalone, readable, work = corpus / "standalone", corpus / "readable", corpus / "work"
    return TrackPaths(
        project_root=root, dev_dir=dev, schemas_dir=dev / "schemas", scripts_dir=dev / "scripts",
        docs_dir=dev / "docs", corpus_root=corpus, standalone_dir=standalone, readable_dir=readable,
        work_dir=work, manifest_path=dev / "research.manifest.json",
    )


def utc_now_iso() -> str:
    """Return a millisecond-precision ISO-8601 UTC timestamp string ending in Z."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    """Return lowercase hex SHA-256 digest of bytes."""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    """Return lowercase hex SHA-256 digest of a file using 1 MiB chunks."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def crc32_hex(data: bytes) -> str:
    """Return 8-character lowercase hex CRC32 checksum of bytes."""
    return f"{zlib.crc32(data) & 0xFFFFFFFF:08x}"


def write_json_log(log_dir: Path | None, stem: str, payload: dict[str, Any]) -> None:
    """Append one JSON line record into <log_dir>/<stem>.log when --log-dir is set."""
    if log_dir is None:
        return
    target = Path(log_dir).resolve()
    target.mkdir(parents=True, exist_ok=True)
    with (target / f"{stem}.log").open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(payload) + "\n")


def missing_media_payload(data_dir: Path | str | None, missing_files: list[str], message: str) -> dict[str, Any]:
    """Build a fail-closed Standard 18 v2 MISSING_CORPUS_MEDIA JSON payload."""
    return {
        "schemaVersion": 2,
        "gameId": GAME_ID,
        "isPassed": False,
        "errorCode": "MISSING_CORPUS_MEDIA",
        "errorMessage": message,
        "dataDir": str(data_dir or ""),
        "missingFiles": list(missing_files),
        "generatedAtUtc": utc_now_iso(),
    }


def iter_integrity_entries(data: dict[str, Any]) -> list[tuple[str, int | None, str, str]]:
    """Read Standard 18 v2 entries list (or legacy verified_files fallback) as (rel, size, sha256, crc32)."""
    out: list[tuple[str, int | None, str, str]] = []
    entries = data.get("entries")
    if isinstance(entries, list):
        for item in entries:
            if isinstance(item, dict) and item.get("relativePath"):
                sz = item.get("fileSizeBytes", item.get("expectedSizeBytes", item.get("bytes")))
                sha = str(item.get("sha256Hex") or item.get("expectedSha256") or item.get("sha256") or "").lower()
                crc = str(item.get("crc32Hex") or item.get("crc32") or "").lower()
                out.append((str(item["relativePath"]), int(sz) if sz is not None else None, sha, crc))
        return out
    verified = data.get("verifiedFiles") or data.get("verified_files") or {}
    if isinstance(verified, dict):
        for rel, meta in verified.items():
            if isinstance(meta, dict):
                sz = meta.get("fileSizeBytes", meta.get("bytes"))
                sha = str(meta.get("sha256Hex") or meta.get("sha256") or "").lower()
                crc = str(meta.get("crc32Hex") or meta.get("crc32") or "").lower()
                out.append((str(rel), int(sz) if sz is not None else None, sha, crc))
    return out


def resolve_optional_rd_tools(tools_dir: Path | None = None, repo_root: Path | None = None) -> Path | None:
    """Locate optional local tools directory without hardcoding workstation paths."""
    candidates: list[Path] = []
    if tools_dir is not None:
        candidates.append(Path(tools_dir))
    if env_tools := os.environ.get("RD_DECOMP_TOOLS", "").strip():
        candidates.append(Path(env_tools))
    base = Path(repo_root).resolve() if repo_root else Path(__file__).resolve().parents[2]
    if base.parent.parent != base.parent:
        candidates.append(base.parent.parent / "Personal" / "R&D" / "Dev" / "tools")
        candidates.append(base.parent.parent / "Personal" / "R&D" / "Dev" / "tools" / "decomp")
    for cand in candidates:
        if cand.is_dir() and ((cand / "decomp" / "manifest_schema.py").is_file() or (cand / "manifest_schema.py").is_file()):
            return cand if (cand / "decomp").is_dir() else cand.parent
    return None


def detect_host_zig_target(override: str | None = None) -> str:
    """Return host Zig cross/native target triple for C parity tests."""
    if override and override.strip():
        return override.strip()
    return "x86-windows-gnu" if sys.platform == "win32" else "x86-linux-gnu"


def resolve_zig_executable(zig_exe: str | Path | None = None) -> Path:
    """Resolve zig compiler executable via CLI flag, ZIG_EXE env, PATH, or WinGet link."""
    for cand in (zig_exe, os.environ.get("ZIG_EXE")):
        if cand and Path(cand).is_file():
            return Path(cand).resolve()
    if found := shutil.which("zig"):
        return Path(found).resolve()
    if local_app := os.environ.get("LOCALAPPDATA", "").strip():
        winget = Path(local_app) / "Microsoft" / "WinGet" / "Links" / "zig.exe"
        if winget.is_file():
            return winget.resolve()
    raise FileNotFoundError("zig executable not found via --zig-exe, ZIG_EXE, PATH, or WinGet Links")
