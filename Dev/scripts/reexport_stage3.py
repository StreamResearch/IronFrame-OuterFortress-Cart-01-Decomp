# @module: IronFrame.Dev.scripts.reexport_stage3
# @purpose: Clean-room Stage 3 Ghidra headless re-export helper using optional external tools discovery
# @depends-on: argparse, importlib.util, json, os, shutil, stat, subprocess, sys, pathlib, typing, nes_cli_common
# @exports: WINDOW_SPEC, main

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from nes_cli_common import (  # noqa: E402
    GAME_ID, missing_media_payload, resolve_optional_rd_tools, resolve_paths, utc_now_iso, write_json_log,
)

WINDOW_SPEC = ";".join(
    ["PRG_FIXED_07.prg=0xc000-0x10000"] + [f"BANK_{b:02d}.prg=0x8000-0xc000" for b in range(7)]
)


def _force_writable(path: Path) -> None:
    if not path.exists():
        return
    for root, dirs, files in os.walk(path):
        for name in dirs + files:
            os.chmod(Path(root) / name, stat.S_IWRITE | stat.S_IREAD)
    os.chmod(path, stat.S_IWRITE | stat.S_IREAD)


def _resolve_project_name(src_proj: Path, schemas_dir: Path) -> str:
    if src_proj.is_dir():
        gprs = sorted(src_proj.glob("*.gpr"))
        if gprs:
            return gprs[0].stem
    recipe = schemas_dir / "decomp_recipe.json"
    if recipe.is_file():
        name = str(json.loads(recipe.read_text(encoding="utf-8")).get("ghidraProjectName") or "").strip()
        if name:
            return name
    return "IronFrameOuterFortressCart01"


def _load_inspect_binary(tools_root: Path) -> Any:
    mod_path = tools_root / "inspect_binary.py"
    spec = importlib.util.spec_from_file_location("_optional_inspect_binary", mod_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {mod_path}")
    mod = importlib.util.module_from_spec(spec)
    if str(tools_root) not in sys.path:
        sys.path.insert(0, str(tools_root))
    spec.loader.exec_module(mod)
    return mod


def _emit(log_dir: Path | None, payload: dict[str, Any], code: int) -> int:
    write_json_log(log_dir, "reexport_stage3", payload)
    print(json.dumps(payload, indent=2))
    return code


def main() -> int:
    ap = argparse.ArgumentParser(description="Apply Stage 3 symbol bundle via optional Ghidra headless tools.")
    ap.add_argument("--data-dir", type=Path, default=None)
    ap.add_argument("--tools-dir", type=Path, default=None)
    ap.add_argument("--log-dir", type=Path, default=None)
    ap.add_argument("--offline-synthetic", action="store_true")
    args = ap.parse_args()

    paths = resolve_paths(data_dir=args.data_dir)
    tools_root = resolve_optional_rd_tools(args.tools_dir, paths.project_root)
    src_proj = paths.standalone_dir / "ghidra_project"
    bundle_path = paths.work_dir / "ghidra_stage_bundle.json"

    if args.offline_synthetic:
        payload = {
            "schemaVersion": 2, "gameId": GAME_ID, "generatedAtUtc": utc_now_iso(), "isPassed": True,
            "mode": "offline-synthetic", "windowSpec": WINDOW_SPEC,
            "ghidraProjectName": _resolve_project_name(src_proj, paths.schemas_dir),
            "toolsAvailable": tools_root is not None and (tools_root / "inspect_binary.py").is_file(),
            "hasGhidraProject": src_proj.is_dir(), "hasStageBundle": bundle_path.is_file(),
        }
        return _emit(args.log_dir, payload, 0)

    scripts_dir = (tools_root / "ghidra_scripts") if tools_root else None
    missing: list[str] = []
    if not src_proj.is_dir():
        missing.append("standalone/ghidra_project")
    if not bundle_path.is_file():
        missing.append("work/ghidra_stage_bundle.json")
    if tools_root is None or not (tools_root / "inspect_binary.py").is_file() or scripts_dir is None or not scripts_dir.is_dir():
        missing.append("optional_tools/inspect_binary.py+ghidra_scripts")
    if missing:
        msg = "Standalone ghidra_project, Stage 3 bundle, or optional Ghidra tools missing."
        return _emit(args.log_dir, missing_media_payload(paths.corpus_root, missing, msg), 2)

    assert tools_root is not None and scripts_dir is not None
    ib = _load_inspect_binary(tools_root)
    final_reexport = paths.work_dir / "ghidra_reexport"
    tmp_work = ib.WORK_ROOT / "ironframe-stage3"
    tmp_proj, tmp_scripts, tmp_reexport, tmp_bundle = tmp_work / "ghidra_project", tmp_work / "ghidra_scripts", tmp_work / "ghidra_reexport", tmp_work / "ghidra_stage_bundle.json"
    for d in (tmp_work, final_reexport):
        if d.exists():
            _force_writable(d)
            shutil.rmtree(d)
    try:
        shutil.copytree(src_proj, tmp_proj)
        _force_writable(tmp_proj)
        shutil.copytree(scripts_dir, tmp_scripts)
        shutil.copy2(bundle_path, tmp_bundle)
        tmp_reexport.mkdir(parents=True, exist_ok=True)
        proj_name = _resolve_project_name(src_proj, paths.schemas_dir)
        cmd = ib.build_ghidra_headless_cmd(
            tmp_proj, proj_name,
            [
                "-process", "-noanalysis", "-scriptPath", str(ib.ensure_ghidra_safe_path(tmp_scripts)),
                "-postScript", "GhidraUniversalApplyAndExport.java",
                str(ib.ensure_ghidra_safe_path(tmp_bundle)), str(ib.ensure_ghidra_safe_path(tmp_reexport)), WINDOW_SPEC,
            ],
        )
        subprocess.run(cmd, env={**os.environ, "JAVA_HOME": str(ib.JDK25_HOME)}, check=True)
        shutil.copytree(tmp_reexport, final_reexport)
    finally:
        if tmp_work.exists():
            _force_writable(tmp_work)
            shutil.rmtree(tmp_work, ignore_errors=True)

    progs = sorted(p.name for p in final_reexport.iterdir() if p.is_dir() and (p / "functions.json").is_file())
    payload = {
        "schemaVersion": 2, "gameId": GAME_ID, "generatedAtUtc": utc_now_iso(), "isPassed": len(progs) > 0,
        "mode": "reexport", "programCount": len(progs), "programs": progs, "outDir": str(final_reexport),
    }
    return _emit(args.log_dir, payload, 0 if progs else 1)


if __name__ == "__main__":
    raise SystemExit(main())
