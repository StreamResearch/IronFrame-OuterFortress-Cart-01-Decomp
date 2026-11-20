# IronFrame OuterFortress (Cart) 01 — Stage 4 Readable Codebase Guide

- **Title ID:** `NES-ME-USA` (`6502_2a03` / `iNES Mapper 2 UNROM`)
- **Workspace:** [IronFrame-OuterFortress-Cart-01-Decomp.code-workspace](../../IronFrame-OuterFortress-Cart-01-Decomp.code-workspace)
- **Generated Trees:** Local gitignored `Corpus/readable/` (synced to `D3_Mapped`) and `Corpus/tiers/{D1_Raw, D2_Structured, D3_Mapped}` (tracked artifacts live in `Dev/schemas/`, `Dev/docs/`, and `Dev/scripts/`)

## 1. Directory Layout (`Corpus/readable/` & `Corpus/tiers/`)

| Folder / File | Purpose | Count / Notes |
| :--- | :--- | :--- |
| `Corpus/readable/include/metalgear_types.h` | Root type umbrella (`ghidra_compat.h` + `nes_hardware.h`, `mg_player.h`, `mg_world.h`, `mg_audio.h`) | `22` structs, `22` enums |
| `Corpus/readable/include/metalgear_globals.h` | Typed `extern` declarations from [globals_map.json](../../schemas/globals_map.json) + deduplicated `D3` overrides ([d3_symbol_overrides.json](../../schemas/d3_symbol_overrides.json)) | `2,342` mapped `extern`s (`0` raw) |
| `Corpus/readable/include/metalgear_functions.h` | Typed prototypes across all `499` catalog functions + `8` `D3` adapters + `9` sub-entry prototypes | `0` raw `FUN_*`/`func_0x*` |
| `Corpus/readable/include/ghidra_compat.h` | 6502/MSP430-compatible P-code helper macros (`SUB21`, `SEXT12`, `CARRY1/2`, `CONCAT11`, `u8/u16`) | Generated |
| `Corpus/readable/src/core/*.c` | Cohesive `D3_Mapped` fixed PRG bank (`PRG_FIXED_07.prg`, `$C000–$FFFF`) domain C modules | `246` funcs (+`8` adapters) / `10` modules |
| `Corpus/readable/overlays/BANK_00.prg/ .. BANK_06.prg/` | Cohesive `D3_Mapped` switchable `$8000–$BFFF` UNROM bank (`BANK_00`..`BANK_06`) domain C modules | `253` funcs / `16` modules |
| `Corpus/tiers/{D1_Raw,D2_Structured,D3_Mapped}` | Preserved raw exports (`8` banks / `507` `.c`), sliced C (`68` fragments), and coalesced `D3_Mapped` (`26` modules) | Built by `materialize_decomp_tiers.py` |
| `Corpus/work/lifted_asm/*.s` | Hand-verified 6502 hardware & trampoline assembly (`vectors_and_nmi.s`, `unrom_trampoline.s`, `ppu_joypad_io.s`) | `3` modules |
| `Corpus/readable/compile_commands.json` | LLVM/clangd database targeting `msp430-unknown-none-elf` (`16-bit` pointer ABI) across all `26` modules | Auto-refreshed |
| `Corpus/readable/SYMBOL_MAP.md` | Address-to-symbol quick reference linked to cohesive `D3_Mapped` module paths | Auto-refreshed |
| `Corpus/readable/ARCHITECTURE_WALKTHROUGH.md` | `26`-module domain overview and function-count summary | Auto-refreshed |

*(Note: `v0.2.0` (`D3_Mapped`) completed cohesive coalescing across all `26` domain modules with `0` remaining raw tokens or `_01.._NN.c` slices; function-by-function idiomatic C11 rewriting under `-Wall -Wextra -Wno-unused-parameter` (`D4_CleanSource`) is scheduled for `v0.3.0`.)*

## 2. Opening & Browsing in VS Code / Antigravity

1. Open [IronFrame-OuterFortress-Cart-01-Decomp.code-workspace](../../IronFrame-OuterFortress-Cart-01-Decomp.code-workspace) directly in your IDE.
2. `clangd` uses `Corpus/readable/compile_commands.json` (`--target=msp430-unknown-none-elf`) so `uint16_t` 6502 pointers (`nes_addr_t`), zero-page locals, and hardware register structs resolve cleanly.
3. Cross-reference lifted C routines with the clean-room 6502 modules in `Corpus/work/lifted_asm/`:
   - `vectors_and_nmi.s` — Reset initialization, NMI frame handler, and OAM DMA (`$4014`).
   - `unrom_trampoline.s` — Bus-conflict-safe bank select (`$C932–$C958`) and inline jump dispatch (`$C6B7`).
   - `ppu_joypad_io.s` — VRAM buffer flush (`$2006/$2007`) and dual-controller shift-register reads (`$4016/$4017`).

## 3. Verifying `Corpus/readable/`, Tiers & Assembly Output

After staging your legally obtained `NES-ME-USA` ROM locally in `Corpus/standalone/`, materialize tiers and run the verification scripts from the repository root:

```powershell
python -B Dev/scripts/materialize_decomp_tiers.py
python -B Dev/scripts/build_and_verify_d5.py
python -B Dev/scripts/build_and_verify_d4.py
python -B Dev/scripts/verify_track_d5.py
```
