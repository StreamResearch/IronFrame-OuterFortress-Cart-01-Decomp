# Specifications — IronFrame OuterFortress (Cart) 01 Decomp (`NES-ME-USA`)

> **Schema Baseline:** `22` Structs · `22` Enums · `1` Typedef (`0` unresolved fields) · `2,324` Catalog Globals (`2,344` Header Externs) · `26` `D4_CleanSource` Modules (`507` Symbols, `0` Decompiler Tells) · `1` BYO-ROM + `17` Extracted Entries

This manual defines the recovered C11 type system, 6502 memory map, cartridge header layout, clean-room SHA-256 baseline, and JSON verification schemas for `IronFrame-OuterFortress-Cart-01-Decomp`. Detailed per-bank matrices and address-space tables live in the [Symbol & Bank Reference](specifications/symbol-and-bank-reference.md).

---

## 1. Recovered Type System (`Dev/schemas/types/*.h`)

[spec_coverage.json](../schemas/spec_coverage.json) (`schemaVersion: 2`) records `definedStructCount: 22`, `definedEnumCount: 22`, and `unresolvedFieldCount: 0` across [metalgear_types.h](../schemas/metalgear_types.h) (`14` lines, defining `nes_addr_t` and including all `4` domain type headers):

| Header | Lines | Target Scope |
| :--- | ---: | :--- |
| [nes_hardware.h](../schemas/types/nes_hardware.h) | `185` | `RP2A03` CPU/MMIO registers, PPU control/status/scroll, APU pulse/triangle/noise/DMC registers, UNROM latch, OAM attributes, joypad flags |
| [mg_player.h](../schemas/types/mg_player.h) | `141` | Player agent state, health/rank, equipment & weapon slots, alert/evasion phase, transceiver/codec state |
| [mg_world.h](../schemas/types/mg_world.h) | `99` | Actor Structure-of-Arrays slots, room/building/floor IDs, doors/elevators, guard AI & collision state |
| [mg_audio.h](../schemas/types/mg_audio.h) | `95` | 6-channel sound driver slots, sequencer parse state, note/envelope timers, control opcodes |

Inside `Corpus/readable/include/`, these type headers (including `D4` placeholder-free renames in `mg_player.h` — `player_status_mask`, `*_zp72..76` — and `nes_hardware.h` — `unused_reg_4009_pad`, `unused_reg_400d_pad`) combine with `metalgear_globals.h` (`2,344` `extern` declarations = `2,324` catalog globals + `20` deduplicated synthetic/bank-scoped overrides from `22` entries in [d3_symbol_overrides.json](../schemas/d3_symbol_overrides.json), including `g_actor_soa_ram[128]` and `g_apu_mmio_regs[24]`, `0` raw Ghidra externs), `metalgear_functions.h` (including `8` synthesized `D3` adapters and `9` sub-entry prototypes with clean `factor` / `table_index` parameters), and clean `ghidra_compat.h` (`s8..u64` fixed-width freestanding scalar aliases inside `#ifndef GHIDRA_COMPAT_FIXED_INTS`, zero P-code macros; `8` headers total) to support 16-bit freestanding C11 parity builds across all `26` `D4_CleanSource` C modules under `-Wall -Wextra -Wno-unused-parameter`.

---

## 2. Mapped 6502 Address-Space Globals (`2,324 / 2,324`)

[globals_map.json](../schemas/globals_map.json) and [globals_index.json](../schemas/globals_index.json) classify every global symbol (`100%` of `2,324` referenced labels) across `10` hardware and ROM address bands (augmented by `22` override entries in `d3_symbol_overrides.json`, deduplicated into `20` unique `g_*` declarations in `metalgear_globals.h`):

| Address Range | Memory Region | Mapped Globals | Notes |
| :--- | :--- | ---: | :--- |
| `$0000-$00FF` | **Zero Page (`ZP`)** | `184` | Fast scratch, `$27` active UNROM bank shadow, `$80` indirect jump pointer |
| `$0100-$01FF` | **Hardware Stack** | `7` | 6502 stack page & boot stack top references |
| `$0200-$02FF` | **OAM Shadow Buffer** | `1` | `256`-byte sprite DMA source buffer (`$4014`) |
| `$0300-$037F` | **Actor SoA RAM** | `30` | Parallel arrays for player/enemy/projectile entities |
| `$0380-$03FF` | **Audio SoA RAM** | `41` | Sound driver per-channel state & sequencer cursors |
| `$0400-$07FF` | **General WRAM** | `62` | Room state, flags, map tiles, codec/inventory work buffers |
| `$2000-$2007` | **PPU MMIO** | `8` | `PPUCTRL`..`PPUDATA` hardware registers |
| `$4000-$4025` | **APU / OAM-DMA / IO MMIO** | `23` | APU channels, `$4014` OAMDMA, `$4016/$4017` controller ports |
| `$8000-$BFFF` | **Banked PRG ROM (`BANK_00..06`)** | `1,084` | Switchable lookup tables, room scripts, music sequences, sprites |
| `$C000-$FFFF` | **Fixed PRG ROM (`PRG_FIXED_07`)** | `884` | Dispatch tables, `$FFD0-$FFD7` UNROM LUT, core data & vectors |
| **Total** | **Full 6502 Address Space** | **`2,324`** | **`1,246` resident + `1,078` bank-scoped (`2,324 / 2,324`; `2,344` `extern`s w/ `20` synthetic aliases)** |

---

## 3. Cartridge Binary Spec & Clean-Room SHA-256 Baseline

### 3.1 NES 2.0 16-Byte Header & Reference ROM Digests

- **Reference Image:** North American `NES-ME-USA` cartridge dump — `131,088` bytes (`16`-byte header + `8 x 16,384`-byte PRG banks = `131,072` B PRG).
- **Header Bytes (`0x00..0x0F`):** `4E 45 53 1A 08 00 21 08 20 00 00 07 00 00 00 01`
  - Magic `NES\x1A`, `8` PRG-ROM `16 KiB` units (`128 KiB`), `0` CHR-ROM units, vertical mirroring, Mapper `2` (`UNROM`), NES 2.0 identifier (`bytes[7]&0x0C == 0x08`), `CHR-RAM` (`8 KiB` non-battery).
- **Exact Whole-ROM Digests (Lowercase Hex):**
  - `CRC32`: `25ba3d04`
  - `MD5`: `0e514c68eb8d82342a71a74c6d52499b`
  - `SHA1`: `9f7448fddaedc1801e2970e50722ac3cfacd19b8`
  - `SHA256`: `79095355436222161cb3841ff9b5c7a572e77af11461935e433bd6e8dfd0f164`

### 3.2 Read-Only `Corpus/standalone/` Integrity Contract (Standard 18 v2)

- [standalone_integrity.json](../schemas/standalone_integrity.json) (`schemaVersion: 2`) enforces:
  - **`requiredRomChecksums` (`1` entry):** Pins the user-supplied BYO-ROM `data/rom/NES-ME-USA.nes` (`131,088` bytes, `expectedSha256: 79095355436222161cb3841ff9b5c7a572e77af11461935e433bd6e8dfd0f164`, `crc32Hex: 25ba3d04`).
  - **`entries` (`17` deterministic `extracted/` files totaling `3,717,065` bytes):** Pins the `8` `32,768`-byte `.prg` images, `8` `.s` disassembly files, and `extracted/nes_bank_layout.json` with lowercase hex `sha256Hex` and `crc32Hex` digests (excluding `.gpr`/`.rep` and internal exports).

---

## 4. Verification & Schema Contracts (`Dev/schemas/*.json`)

| Artifact | Purpose & Current State |
| :--- | :--- |
| [d3_module_map.json](../schemas/d3_module_map.json) | Standard 18 v2 deterministic `26`-module partition (`10` `src/core/` + `16` `overlays/BANK_00..06.prg/`) assigning all `499/499` functions with `0` `_01.._NN.c` fragments |
| [d3_symbol_overrides.json](../schemas/d3_symbol_overrides.json) | Standard 18 v2 clean-room symbol registry (`1` `localRenames`, `22` `syntheticGlobals` -> `20` deduplicated externs incl. `g_actor_soa_ram[128]` & `g_apu_mmio_regs[24]`, `44` `functionCallOverrides`, `8` `trampolineDeclarations`, `9` `subEntryDeclarations` w/ `factor` & `table_index` params, `0` trademark tokens or C bodies) |
| [d4_rewrites/](../schemas/d4_rewrites/) | `5` Standard 18 v2 zero-body rewrite shards (`core_runtime.json`, `core_gameplay.json`, `overlays_b00_b02.json`, `overlays_b03_b04.json`, `overlays_b05_b06.json`) indexing `26` files and `507` symbols (`0` C bodies, `0` `"cBody"`/`"functionBody"` keys, `0` trademark/PII leaks) |
| [d4_build_report.json](../schemas/d4_build_report.json) | Standard 18 v2 C11 build telemetry (`26/26` `D4_CleanSource` modules compiled under `-Wall -Wextra -Wno-unused-parameter`, `0` errors/warnings, `craftsmanshipTellCount: 0`, `isZeroWarningsVerified: true`, `isZeroDecompilerTellsVerified: true`, `10/10` `D4a` subsystem parity assertions passed; included in `v0.3.0` `.decomp`) |
| [s4_verify_report.json](../schemas/s4_verify_report.json) | Standard 18 v2 host behavioral parity report (`10/10` `D4a` subsystem parity assertions passing via mapped `g_*` globals in modular `d4_harness/` under strict flags) |
| [d5_byte_match.json](../schemas/d5_byte_match.json) | Standard 18 v2 `asm6502_d5.py` SHA-256 verification across `8/8` PRG binaries + `131,088`-byte reassembled ROM (`0` mismatched bytes) |
| [spec_coverage.json](../schemas/spec_coverage.json) | Standard 18 v2 coverage summary (`499/499` functions, `2,324/2,324` globals, `definedStructCount: 22`, `definedEnumCount: 22`, `unresolvedFieldCount: 0`) |
| [decomp_recipe.json](../schemas/decomp_recipe.json) | Clean-room `.decomp` recipe (`engineId: reCart`, `0.1.x`, `targetDecompTier: D4`, `packageVersion: 0.3.0`, `decompSchemaVersion: 1.0.0`, `excludedFiles: []`, packaging `47` entries incl. `d4_build_report.json` & `d4_rewrites/*.json` while excluding `d4_harness/` & `tests/`) |
| [decomp_local.example.json](../schemas/decomp_local.example.json) | Template documenting `--data-dir`, `--out-dir`, `--tools-dir`, `--log-dir`, `--zig-exe`, and env overrides (`IRONFRAME_DATA_DIR`, `RD_DECOMP_TOOLS`, `ZIG_EXE`) |
| [functions_catalog.json](../schemas/functions_catalog.json) | Complete `499`-function metadata catalog (`0` SDK, `0` failed) across `core` + `bank_00..06` |
| [clusters.json](../schemas/clusters.json) | Domain clustering mapping functions, module splits, and cross-bank edges |
| [call_graph.json](../schemas/call_graph.json) | Dependency waves `0..9` (`max_wave=9`), nontrivial SCC registry (`$94ED <-> $96E4`), and zero embedded strings (`strings: []`) |
| [research.manifest.json](../research.manifest.json) | Research manifest (`schemaVersion: 2`, `version: 0.3.0`) locking `D4 / S4 / R0` (`d4ParityTier: "D4a"`, `preservedTiers: ["D1_Raw", "D2_Structured", "D3_Mapped", "D4_CleanSource"]`, `metrics.readableFiles: 36`, `gates.D4.passed: true`) and targeting `D5 / S5 / R3` (`reCart` `0.1.x`) |
