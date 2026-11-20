# IronFrame OuterFortress (Cart) 01 — Stage 4 Readable Codebase Guide

- **Title ID:** `NES-ME-USA` (`6502_2a03` / `iNES Mapper 2 UNROM`)
- **Workspace:** [IronFrame-OuterFortress-Cart-01-Decomp.code-workspace](../../IronFrame-OuterFortress-Cart-01-Decomp.code-workspace)
- **Generated Tree:** Local gitignored `Corpus/readable/` (tracked artifacts live in `Dev/schemas/`, `Dev/docs/`, and `Dev/scripts/`)

## 1. Directory Layout (`Corpus/readable/`)

| Folder / File | Purpose | Count / Notes |
| :--- | :--- | :--- |
| `Corpus/readable/include/metalgear_types.h` | Root type umbrella (`ghidra_compat.h` + `nes_hardware.h`, `mg_player.h`, `mg_world.h`, `mg_audio.h`) | `22` structs, `22` enums |
| `Corpus/readable/include/metalgear_globals.h` | Typed `extern` declarations from [globals_map.json](../../schemas/globals_map.json) + unmapped raw labels pending `v0.2.0` resolution | `2,324` mapped globals |
| `Corpus/readable/include/ghidra_compat.h` | 6502/MSP430-compatible P-code helper macros (`SUB21`, `SEXT12`, `CARRY1/2`, `CONCAT11`, `u8/u16`) | Generated |
| `Corpus/readable/src/core/core_01.c .. core_33.c` | Fixed PRG bank (`PRG_FIXED_07.prg`, `$C000–$FFFF`) initial decompiled C slices | `246` funcs / `33` slices |
| `Corpus/readable/overlays/BANK_00.prg/ .. BANK_06.prg/` | Switchable `$8000–$BFFF` UNROM PRG banks (`BANK_00`..`BANK_06`) initial slices | `253` funcs / `35` slices |
| `Corpus/work/lifted_asm/*.s` | Hand-verified 6502 hardware & trampoline assembly (`vectors_and_nmi.s`, `unrom_trampoline.s`, `ppu_joypad_io.s`) | `3` modules |
| `Corpus/readable/compile_commands.json` | LLVM/clangd database targeting `msp430-unknown-none-elf` (`16-bit` pointer ABI) | Generated |
| `Corpus/readable/SYMBOL_MAP.md` | Address-to-symbol quick reference across `499` functions & mapped globals | Auto-generated |
| `Corpus/readable/ARCHITECTURE_WALKTHROUGH.md` | High-level call hierarchy and bank routing overview | Auto-generated |

*(Note: Coalescing the `68` initial line-split slices into cohesive domain modules and refactoring them into warning-free idiomatic C11 is scheduled for `v0.2.0`–`v0.3.0`.)*

## 2. Opening & Browsing in VS Code / Antigravity

1. Open [IronFrame-OuterFortress-Cart-01-Decomp.code-workspace](../../IronFrame-OuterFortress-Cart-01-Decomp.code-workspace) directly in your IDE.
2. `clangd` uses `Corpus/readable/compile_commands.json` (`--target=msp430-unknown-none-elf`) so `uint16_t` 6502 pointers (`nes_addr_t`), zero-page locals, and hardware register structs resolve cleanly.
3. Cross-reference lifted C routines with the clean-room 6502 modules in `Corpus/work/lifted_asm/`:
   - `vectors_and_nmi.s` — Reset initialization, NMI frame handler, and OAM DMA (`$4014`).
   - `unrom_trampoline.s` — Bus-conflict-safe bank select (`$C932–$C958`) and inline jump dispatch (`$C6B7`).
   - `ppu_joypad_io.s` — VRAM buffer flush (`$2006/$2007`) and dual-controller shift-register reads (`$4016/$4017`).

## 3. Verifying `Corpus/readable/` & Assembly Output

After staging your legally obtained `NES-ME-USA` ROM locally in `Corpus/standalone/`, run the verification scripts from the repository root:

```powershell
python -B Dev/scripts/build_and_verify_d5.py
python -B Dev/scripts/build_and_verify_d4.py
```
