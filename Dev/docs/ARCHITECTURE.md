# Architecture — IronFrame OuterFortress (Cart) 01 Decomp (`NES-ME-USA`)

> **Platform:** 8-bit Cart (`NES / RP2A03`, MOS `6502`) · **Mapper:** `iNES Mapper 2` (`UNROM`) · **Title ID:** `NES-ME-USA`

`IronFrame-OuterFortress-Cart-01-Decomp` houses the clean-room decompilation schemas, hardware-level system specification, self-contained BYO-ROM tooling, `.decomp` package exporter, and `1:1` byte-exact 6502 reassembly scripts for `NES-ME-USA` (`131,088` bytes, NES 2.0). Source media remains clean-room separated inside the gitignored `Corpus/standalone/` directory (pinned in Standard 18 v2 `standalone_integrity.json` as `1` `requiredRomChecksums` BYO-ROM entry plus `17` deterministic `extracted/` entries), while tracked schemas, verification scripts, modular C parity harness (`d4_harness/`), offline tests (`tests/`), and manuals live under `Dev/`.

---

## 1. Cartridge & UNROM Bank Topology (`iNES Mapper 2`)

| Segment / Window | CPU Address Range | Size | Mapping Behavior | Contents / Role |
| :--- | :--- | ---: | :--- | :--- |
| **NES 2.0 Header** | *(file offset `0x0000..0x000F`)* | `16` B | Static ROM header | `4E45531A 08 00 21 08 20 00 00 07 00 00 00 01` |
| **Switchable PRG Window** | `$8000-$BFFF` | `16,384` B (`7` banks) | Mapped via UNROM `$8000-$FFFF` latch (`BANK_00`..`BANK_06`) | Gameplay, maps, transceiver dialogs, sound sequencer |
| **Fixed PRG Bank (`PRG_FIXED_07`)** | `$C000-$FFFF` | `16,384` B | Permanently mapped to final `16 KiB` PRG bank (`bank 7`) | Reset/NMI/IRQ vectors, PPU/APU drivers, UNROM trampolines, core loop |
| **CHR Memory (`CHR-RAM`)** | PPU `$0000-$1FFF` | `8,192` B RAM | `0` CHR-ROM banks (`CHR-RAM` dynamically populated from PRG) | Tiles/patterns streamed by `PRG_FIXED_07` and switchable banks |
| **CPU Work RAM (`WRAM` / `ZP`)** | `$0000-$07FF` | `2,048` B | Internal 2 KiB SRAM + `256`-B page mirrors | Zero Page, `0x0100` stack, `0x0200` OAM, `0x0300` Actor/Audio SoA |

> **32 KiB `.prg` Extraction Convention:** Each linked `.prg` bank image under `Corpus/standalone/extracted/` is `32,768` bytes (`$8000-$FFFF`), pairing a switchable bank (`BANK_00`..`BANK_06`) with fixed `PRG_FIXED_07`. `PRG_FIXED_07.prg` pairs `BANK_00` with `PRG_FIXED_07`, giving it the exact same SHA-256 (`96d482df...`) as `BANK_00.prg` in [d5_byte_match.json](../schemas/d5_byte_match.json).

### Hardware Entry Vectors (`PRG_FIXED_07`, `$FFFA-$FFFF`)

- **`VEC_NMI` (`$C06C`)**: VBlank PPU/OAM/scroll commit and per-frame tick entry.
- **`VEC_RESET` (`$C001`)**: Cold-boot hardware init, WRAM clear, and main loop handoff.
- **`VEC_IRQ` (`$C0B7`)**: Interrupt vector stub in fixed bank `7`.

---

## 2. Core Control-Flow & Bank-Switching Primitives

### 2.1 Inline Jump-Table Dispatch (`$C6B7`)

- **Routine:** `inline_jump_table_dispatch` at `$C6B7` (`16+` call sites).
- **Mechanism:** Pulls the caller's return address from the 6502 hardware stack (`$0100+S`), scales accumulator `A` by `2` to index an inline `.word[]` target table stored immediately after the `JSR $C6B7`, writes the resolved target into Zero Page pointer `$0080`, and transfers control via `jmp ($0080)` (`$C6D2`: `6C 80 00`).
- **Decompiler Boundary:** Marked `NoReturn` during static analysis so callers terminate cleanly after `JSR $C6B7` rather than attempting to decode inline pointer tables as instructions.

### 2.2 UNROM Bank-Switch Trampolines (`$C932..$C958`) & Bus-Conflict LUT

Discrete `UNROM` hardware requires the value written to ROM latch space (`$8000-$FFFF`) to equal the byte stored in ROM at the write address to avoid bus contention:

- **`$C932..$C94A` (`unrom_select_bank_0` .. `unrom_select_bank_6`):** Fixed `4`-byte spaced bank-select entry points in `PRG_FIXED_07`.
- **`$C94C` (`unrom_select_bank_y` / `unrom_select_bank_index`):** Stores active bank index in Zero Page `$27`, then executes `85 27 B9 D0 FF 99 D0 FF 60` (`STA $27; LDA $FFD0,Y; STA $FFD0,Y; RTS` starting at `$C94F`) through the `$FFD0-$FFD7` identity table `{0..7}`.
- **`$C958` (`unrom_restore_active_bank`):** Restores the active bank shadowed in Zero Page `$27`, adjacent to the `$C959` bank-switch helper/LUT region.

---

## 3. Domain & Translation-Unit Topology (`499 / 499` Functions, `8` Domains)

Every function recovered across the `8` PRG banks is named, typed, and indexed across `8` logical bank domains (`68` initial line-split C fragments + `globals_defs.c` in `Corpus/readable/`, plus `3` lifted hardware assembly modules under `Corpus/work/lifted_asm/`). Coalescing the `68` initial fragments into modular domain C files and refactoring all `499` functions into warning-free idiomatic C11 is scheduled for `v0.2.0`–`v0.3.0`:

| Domain | Bank Image | Code Bytes | Initial `.c` Slices | Functions | Bank Globals | Domain Globals |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: |
| **`core`** | `PRG_FIXED_07` (`$C000-$FFFF`) | `12,832` | `33` | `246` | `1,246` *(resident)* | `1,113` |
| **`bank_00`** | `BANK_00` (`$8000-$BFFF`) | `2,618` | `5` | `34` | `310` | `310` |
| **`bank_01`** | `BANK_01` (`$8000-$BFFF`) | `715` | `1` | `2` | `25` | `30` |
| **`bank_02`** | `BANK_02` (`$8000-$BFFF`) | `4,100` | `12` | `87` | `259` | `274` |
| **`bank_03`** | `BANK_03` (`$8000-$BFFF`) | `2,471` | `5` | `41` | `100` | `134` |
| **`bank_04`** | `BANK_04` (`$8000-$BFFF`) | `2,046` | `4` | `32` | `148` | `160` |
| **`bank_05`** | `BANK_05` (`$8000-$BFFF`) | `2,252` | `4` | `24` | `79` | `82` |
| **`bank_06`** | `BANK_06` (`$8000-$BFFF`) | `2,123` | `4` | `33` | `157` | `221` |
| **Total** | **`8` PRG Banks (`131,072` B)** | **`29,157`** | **`68` (+`1` defs)** | **`499`** | **`2,324`** | **`2,324`** |

- **Call Graph & Curated Anchors:** [call_graph.json](../schemas/call_graph.json) orders all `499` functions into bottom-up waves `0..9` (`max_wave=9`) with `1` nontrivial strongly connected component (`BANK_06.prg@000094ed <-> BANK_06.prg@000096e4`, audio sequencer recursion) and `0` failed functions (`4 -> 0` after `BANK_06` recovery). [anchor_functions.json](../schemas/anchor_functions.json) tracks `39` curated entry/system anchors across `5` export shards.
- **Lifted Hardware Assembly (`551` lines):** `Corpus/work/lifted_asm/` isolates low-level 6502 hardware glue across `ppu_joypad_io.s` (`149` lines), `unrom_trampoline.s` (`218` lines), and `vectors_and_nmi.s` (`184` lines).

---

## 4. Research Directory Contract & Related Documentation

- **Read-Only Media Isolation:** Local `Corpus/` holds `standalone/` (pinned in [standalone_integrity.json](../schemas/standalone_integrity.json) v2 as `1` BYO-ROM entry + `17` `extracted/` entries totaling `3,717,065` B), `readable/`, and `work/`—strictly gitignored and excluded from source and `.decomp` archives.
- **Clean-Room Tooling (`Dev/scripts/`):** Organized into shared path/hash helpers (`nes_cli_common.py`), 6502 CFG/UNROM unpacker (`nes_6502_cfg.py`, `nes_unrom_unpack.py`), 6502 assembler (`asm6502_d5.py`, `build_and_verify_d5.py`), D4/S4 parity driver (`build_and_verify_d4.py` + 4-file `d4_harness/`), schema/verifier CLIs (`gen_d4_globals_and_lifts.py`, `reexport_stage3.py`, `verify_track_d5.py`), `.decomp`/release packagers (`export_decomp_bundle.py`, `package_release.py`), and `3` offline `unittest` modules (`tests/`).
- **Next Manuals:** [SPECIFICATIONS.md](SPECIFICATIONS.md) | [Symbol & Bank Spoke](specifications/symbol-and-bank-reference.md) | [FINDINGS.md](FINDINGS.md) | [OPERATIONS.md](OPERATIONS.md)
- **Stage Notes:** [Stage 0](stages/00-stage0-triage-and-rom-layout.md) | [Stage 1](stages/01-stage1-call-graph-and-clusters.md) | [Stage 2](stages/02-stage2-structs-globals-and-asm.md) | [Stage 3](stages/03-stage3-function-naming.md) | [Stage 4](stages/04-stage4-readable-codebase-guide.md)
