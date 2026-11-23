# @module: IronFrame.Dev.scripts.d4b_oracle_bridges
# @purpose: Mesen 2.1.1 primary oracle Lua bridge and read-only reCart.Core.dll InterpreterOracle witness
# @depends-on: json, os, pathlib, subprocess, sys, tempfile, typing, nes_cli_common
# @exports: TOTAL_FRAMES, SCENES, input_mask_for_frame, mask_wram_stack, resolve_mesen_exe, ensure_mesen_io_access, resolve_recart_dir, run_mesen_oracle, run_recart_oracle

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from nes_cli_common import crc32_hex, sha256_bytes, write_json_log  # noqa: E402

TOTAL_FRAMES = 650
_FRAME_BYTES = 2048 + 256 + 36 + 24
BTN_A, BTN_B, BTN_SELECT, BTN_START, BTN_UP, BTN_DOWN, BTN_LEFT, BTN_RIGHT = 1, 2, 4, 8, 16, 32, 64, 128

SCENES: tuple[tuple[str, int, int], ...] = (
    ("scene_1_boot_and_title", 1, 100),
    ("scene_2_intro_to_dock", 101, 220),
    ("scene_3_dock_traversal", 221, 380),
    ("scene_4_transceiver_and_pause", 381, 520),
    ("scene_5_combat_action", 521, 650),
)

_MESEN_LUA = r"""
local outPath, totalFrames = assert(os.getenv("MESEN_D4B_OUT")), tonumber(os.getenv("MESEN_D4B_FRAMES") or "650")
local apu = {}; for i = 0, 23 do apu[i] = 0 end
emu.addMemoryCallback(function(addr, val)
  if addr ~= 0x4014 and addr ~= 0x4016 then apu[addr - 0x4000] = val & 0xFF end
end, emu.callbackType.write, 0x4000, 0x4017)

local f, done = 0, false
emu.addEventCallback(function()
  local nf = f + 1
  local inp = { a=false, b=false, select=false, start=false, up=false, down=false, left=false, right=false }
  if (nf >= 105 and nf <= 109) or (nf >= 140 and nf <= 144) or (nf >= 485 and nf <= 489) or (nf >= 505 and nf <= 509) then inp.start = true end
  if nf >= 260 and nf <= 320 then inp.right = true end
  if nf >= 325 and nf <= 385 then inp.up = true end
  if (nf >= 410 and nf <= 414) or (nf >= 460 and nf <= 464) then inp.select = true end
  if nf >= 521 and nf <= 650 and ((nf % 20) < 4) then inp.up = true; inp.b = true end
  emu.setInput(inp, 0)
end, emu.eventType.inputPolled)

local out = assert(io.open(outPath, "wb"))
local char, concat, read = string.char, table.concat, emu.read
local mWram, mOam, mPal = emu.memType.nesInternalRam, emu.memType.nesSpriteRam, emu.memType.nesPaletteRam

emu.addEventCallback(function()
  if done then return end
  f = f + 1
  local st = emu.getState()
  local t = st["ppu.tmpVideoRamAddr"] or 0
  local ctrl = ((t >> 10) & 3) | (st["ppu.control.verticalWrite"] and 4 or 0)
    | ((st["ppu.control.spritePatternAddr"] ~= 0) and 8 or 0) | ((st["ppu.control.backgroundPatternAddr"] ~= 0) and 16 or 0)
    | (st["ppu.control.largeSprites"] and 32 or 0) | (st["ppu.control.nmiOnVerticalBlank"] and 128 or 0)
  local mask = (st["ppu.mask.grayscale"] and 1 or 0) | (st["ppu.mask.backgroundMask"] and 2 or 0)
    | (st["ppu.mask.spriteMask"] and 4 or 0) | (st["ppu.mask.backgroundEnabled"] and 8 or 0)
    | (st["ppu.mask.spritesEnabled"] and 16 or 0) | (st["ppu.mask.intensifyRed"] and 32 or 0)
    | (st["ppu.mask.intensifyGreen"] and 64 or 0) | (st["ppu.mask.intensifyBlue"] and 128 or 0)
  local sx = ((t & 0x1F) << 3) | (st["ppu.xScroll"] or 0)
  local sy = (((t >> 5) & 0x1F) << 3) | ((t >> 12) & 7)
  local buf, k = {}, 1
  for i = 0, 2047 do buf[k] = char((i >= 0x100 and i <= 0x1FF) and 0 or read(i, mWram)); k = k + 1 end
  for i = 0, 255 do buf[k] = char(read(i, mOam)); k = k + 1 end
  buf[k] = char(ctrl, mask, sx, sy); k = k + 1
  for i = 0, 31 do buf[k] = char(read(i, mPal)); k = k + 1 end
  for i = 0, 23 do buf[k] = char(apu[i]); k = k + 1 end
  out:write(concat(buf))
  if f >= totalFrames then done = true; out:close(); emu.stop(0) end
end, emu.eventType.endFrame)
"""

_RECART_PROGRAM_CS = r"""
using System;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using reCart.Contracts;
using reCart.Core.Cpu;
using reCart.Core.Runtime;

var romPath = Environment.GetEnvironmentVariable("RECART_D4B_ROM") ?? "";
var outPath = Environment.GetEnvironmentVariable("RECART_D4B_OUT") ?? "";
int totalFrames = int.Parse(Environment.GetEnvironmentVariable("RECART_D4B_FRAMES") ?? "650");
Func<byte[], uint> crc32Fn = (data) => {
    uint c = 0xFFFFFFFFu;
    foreach (byte b in data) { c ^= b; for (int k = 0; k < 8; k++) c = (c & 1u) != 0 ? (c >> 1) ^ 0xEDB88320u : (c >> 1); }
    return c ^ 0xFFFFFFFFu;
};
var romBytes = File.ReadAllBytes(romPath);
using var host = CartMachineFactory.CreateFromRomBytes(romBytes, CartVideoRegionStandard.Ntsc, CartExecutionTierMode.InterpreterOracle);
var bus = (CartMemoryBus)host.Bus;
var prev = new byte[2048];
var wram = new byte[2048];
var sb = new StringBuilder();
int transitions = 0, nonZeroFinal = 0;
uint bootCrc = 0, finalCrc = 0;
for (int f = 1; f <= totalFrames; f++) {
    uint mask = 0;
    if ((f >= 105 && f <= 109) || (f >= 140 && f <= 144) || (f >= 485 && f <= 489) || (f >= 505 && f <= 509)) mask |= 0x08u;
    if (f >= 260 && f <= 320) mask |= 0x80u;
    if (f >= 325 && f <= 385) mask |= 0x10u;
    if ((f >= 410 && f <= 414) || (f >= 460 && f <= 464)) mask |= 0x04u;
    if (f >= 521 && f <= 650 && (f % 20) < 4) mask |= 0x12u;
    host.SetControllerButtons(0, mask);
    host.StepFrame();
    Buffer.BlockCopy(bus.CaptureState(), 12, wram, 0, 2048);
    if (!wram.AsSpan().SequenceEqual(prev)) transitions++;
    Buffer.BlockCopy(wram, 0, prev, 0, 2048);
    if (f == totalFrames) for (int i = 0; i < 2048; i++) if (wram[i] != 0) nonZeroFinal++;
    Array.Clear(wram, 0x100, 0x100);
    uint crc = crc32Fn(wram);
    if (f == 1) bootCrc = crc;
    finalCrc = crc;
    sb.Append($"{crc:x8},");
}
var sha = Convert.ToHexString(SHA256.HashData(Encoding.ASCII.GetBytes(sb.ToString()))).ToLowerInvariant();
File.WriteAllText(outPath, $"{{\"frames\":{totalFrames},\"framesRendered\":{host.Diagnostics.FramesRendered},\"transitions\":{transitions},\"nonZeroFinalBytes\":{nonZeroFinal},\"bootWramCrc32\":\"{bootCrc:x8}\",\"finalWramCrc32\":\"{finalCrc:x8}\",\"wramTraceSha256\":\"{sha}\"}}");
"""


def input_mask_for_frame(frame: int) -> int:
    """Return canonical NES controller-1 bitmask for 1-based frame across 5 D4b scenes."""
    mask = 0
    if (105 <= frame <= 109) or (140 <= frame <= 144) or (485 <= frame <= 489) or (505 <= frame <= 509):
        mask |= BTN_START
    if 260 <= frame <= 320:
        mask |= BTN_RIGHT
    if 325 <= frame <= 385:
        mask |= BTN_UP
    if (410 <= frame <= 414) or (460 <= frame <= 464):
        mask |= BTN_SELECT
    if 521 <= frame <= 650 and (frame % 20) < 4:
        mask |= BTN_UP | BTN_B
    return mask


def mask_wram_stack(wram: bytes | bytearray) -> bytes:
    """Zero out hardware stack $0100-$01FF inside 2048-byte NES WRAM snapshot."""
    if len(wram) != 2048:
        raise ValueError(f"Expected 2048-byte WRAM buffer, got {len(wram)}")
    buf = bytearray(wram)
    buf[0x100:0x200] = b"\x00" * 256
    return bytes(buf)


def resolve_mesen_exe(mesen_exe: str | Path | None = None) -> Path:
    """Resolve Mesen 2.1.1 executable via --mesen-exe, MESEN_EXE, or LOCALAPPDATA."""
    cands: list[Path] = []
    if mesen_exe:
        cands.append(Path(mesen_exe))
    if env_val := os.environ.get("MESEN_EXE", "").strip():
        cands.append(Path(env_val))
    if local_app := os.environ.get("LOCALAPPDATA", "").strip():
        cands.append(Path(local_app) / "Programs" / "Mesen2" / "Mesen.exe")
    for cand in cands:
        if cand.is_file():
            return cand.resolve()
    raise FileNotFoundError("Mesen 2.1.1 executable not found via --mesen-exe, MESEN_EXE, or LOCALAPPDATA.")


def ensure_mesen_io_access(mesen_exe: Path) -> Path:
    """Ensure Debug.ScriptWindow.AllowIoOsAccess is True in settings.json adjacent to Mesen.exe."""
    cfg_path = mesen_exe.parent / "settings.json"
    data = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.is_file() else {}
    dbg = data.setdefault("Debug", {})
    sw = dbg.setdefault("ScriptWindow", {})
    if sw.get("AllowIoOsAccess") is not True:
        sw["AllowIoOsAccess"] = True
        cfg_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return cfg_path


def resolve_recart_dir(recart_dir: str | Path | None = None, project_root: Path | None = None) -> Path:
    """Resolve read-only reCartOne app directory containing reCart.Core.dll and reCart.Contracts.dll."""
    root = Path(project_root).resolve() if project_root else _SCRIPTS_DIR.parents[1]
    cands: list[Path] = []
    if recart_dir:
        cands.append(Path(recart_dir))
    if env_val := os.environ.get("RECART_DIR", "").strip():
        cands.append(Path(env_val))
    if root.parent.parent != root.parent:
        cands.append(root.parent.parent / "Personal" / "reCartOne" / "Builds" / "v0.1.0" / "app")
    for cand in cands:
        if cand.is_dir() and (cand / "reCart.Core.dll").is_file() and (cand / "reCart.Contracts.dll").is_file():
            return cand.resolve()
    raise FileNotFoundError("reCartOne app directory with reCart.Core.dll and reCart.Contracts.dll not found.")


def run_mesen_oracle(
    rom_path: Path, mesen_exe: str | Path | None = None, total_frames: int = TOTAL_FRAMES,
    timeout_sec: int = 45, log_dir: Path | None = None,
) -> dict[str, Any]:
    """Run headless Mesen 2.1.1 --testRunner over total_frames and return subsystem CRC32 digests."""
    exe = resolve_mesen_exe(mesen_exe)
    ensure_mesen_io_access(exe)
    rom = Path(rom_path).resolve()
    if not rom.is_file():
        raise FileNotFoundError(f"ROM not found: {rom}")
    with tempfile.TemporaryDirectory(prefix="d4b_mesen_") as tmp:
        tdir = Path(tmp)
        lua_p, bin_p = tdir / "trace_d4b.lua", tdir / "frames.bin"
        lua_p.write_text(_MESEN_LUA.lstrip(), encoding="utf-8", newline="\n")
        env = {**os.environ, "MESEN_D4B_OUT": str(bin_p), "MESEN_D4B_FRAMES": str(total_frames)}
        proc = subprocess.run(
            [str(exe), "--testRunner", f"--timeout={timeout_sec}", str(rom), str(lua_p)],
            capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL, timeout=timeout_sec + 15, check=False,
        )
        if not bin_p.is_file():
            raise RuntimeError(f"Mesen failed to write trace (rc={proc.returncode}): {proc.stderr[:300]}")
        blob = bin_p.read_bytes()
    if len(blob) != total_frames * _FRAME_BYTES:
        raise RuntimeError(f"Mesen frame trace size {len(blob)} != {total_frames * _FRAME_BYTES}")
    frames: list[dict[str, Any]] = []
    for idx in range(total_frames):
        off = idx * _FRAME_BYTES
        wram = mask_wram_stack(blob[off : off + 2048])
        oam, ppu, apu = blob[off + 2048 : off + 2304], blob[off + 2304 : off + 2340], blob[off + 2340 : off + 2364]
        frames.append({
            "frame": idx + 1, "wramCrc32": crc32_hex(wram), "oamCrc32": crc32_hex(oam),
            "ppuCrc32": crc32_hex(ppu), "apuCrc32": crc32_hex(apu),
        })
    digests = {
        k: sha256_bytes(",".join(f[k] for f in frames).encode("ascii"))
        for k in ("wramCrc32", "oamCrc32", "ppuCrc32", "apuCrc32")
    }
    write_json_log(log_dir, "d4b_mesen_oracle", {"oracleType": "mesen", "totalFrames": total_frames, "digests": digests})
    return {"oracleType": "mesen", "totalFrames": total_frames, "frames": frames, "digests": digests}


def _recart_csproj_xml(app_dir: Path) -> str:
    dlls = ("reCart.Core", "reCart.Contracts", "Foundation.Core", "Foundation.Retro", "reEngine.Core", "reEngine.Host")
    refs = "\n".join(f'    <Reference Include="{n}"><HintPath>{app_dir / (n + ".dll")}</HintPath></Reference>' for n in dlls if (app_dir / f"{n}.dll").is_file())
    return (
        '<Project Sdk="Microsoft.NET.Sdk">\n  <PropertyGroup>\n    <OutputType>Exe</OutputType>\n'
        '    <TargetFramework>net8.0</TargetFramework>\n    <ImplicitUsings>enable</ImplicitUsings>\n'
        f'    <Nullable>enable</Nullable>\n  </PropertyGroup>\n  <ItemGroup>\n{refs}\n  </ItemGroup>\n</Project>\n'
    )


def run_recart_oracle(
    rom_path: Path, recart_dir: str | Path | None = None, project_root: Path | None = None,
    total_frames: int = TOTAL_FRAMES, log_dir: Path | None = None,
) -> dict[str, Any]:
    """Run read-only reCart.Core.dll InterpreterOracle witness over total_frames via temp net8.0 host."""
    app_dir = resolve_recart_dir(recart_dir, project_root)
    rom = Path(rom_path).resolve()
    if not rom.is_file():
        raise FileNotFoundError(f"ROM not found: {rom}")
    with tempfile.TemporaryDirectory(prefix="d4b_recart_") as tmp:
        tdir = Path(tmp)
        (tdir / "Witness.csproj").write_text(_recart_csproj_xml(app_dir), encoding="utf-8")
        (tdir / "Program.cs").write_text(_RECART_PROGRAM_CS.lstrip(), encoding="utf-8")
        out_p = tdir / "witness.json"
        env = {**os.environ, "RECART_D4B_ROM": str(rom), "RECART_D4B_OUT": str(out_p), "RECART_D4B_FRAMES": str(total_frames)}
        proc = subprocess.run(
            ["dotnet", "run", "--project", str(tdir / "Witness.csproj")],
            capture_output=True, text=True, cwd=str(tdir), env=env, stdin=subprocess.DEVNULL, timeout=120, check=False,
        )
        if proc.returncode != 0 or not out_p.is_file():
            raise RuntimeError(f"reCart witness failed (rc={proc.returncode}): {proc.stdout[-300:]} {proc.stderr[-300:]}")
        data = json.loads(out_p.read_text(encoding="utf-8"))
    write_json_log(log_dir, "d4b_recart_witness", data)
    return data
