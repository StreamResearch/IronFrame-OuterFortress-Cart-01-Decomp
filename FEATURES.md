# Features — IronFrame OuterFortress (Cart) 01 Decomp

Overview of what this repository supports today (`v0.1.0` `D2/S4/R0` baseline) and what is scheduled across upcoming milestones. See [ROADMAP.md](ROADMAP.md) for the full release plan.

## Feature Summary

| Feature | Status | Target | Primary Code | What It Does |
| :--- | :--- | :--- | :--- | :--- |
| **Clean-Room 6502 Assembler** | `Live` | `v0.1.0` | `Dev/scripts/asm6502_d5.py` | Assembles symbolic 6502 source (`56` mnemonics, `151` opcodes) to `1:1` ROM bytes (`8/8` banks). |
| **Self-Contained BYO-ROM Unpacker** | `Live` | `v0.1.0` | `Dev/scripts/nes_unrom_unpack.py` | Validates `.nes` SHA-256/CRC32, splits Mapper 2 banks, traces CFG (`nes_6502_cfg.py`), and supports `--offline-synthetic`. |
| **Portable `.decomp` Bundle & Packager** | `Live` | `v0.1.0` | `Dev/scripts/export_decomp_bundle.py` | Emits `reCart` (`0.1.x`) validated `IronFrame-OuterFortress-Cart-01.decomp` and 10-invariant release mirrors (`package_release.py`). |
| **Offline Unit Tests & Modular Parity** | `Live` | `v0.1.0` | `Dev/scripts/tests/`, `d4_harness/` | Passes `14/14` offline `unittest` tests, `12/12` `verify_track_d5.py` checks, and `10/10` modular C host parity assertions. |
| **Symbol, Type & Call-Graph Catalog** | `Live` | `v0.1.0` | `Dev/schemas/` | Indexes `499` functions, `2,324` globals, `22` structs, `22` enums (`0` unresolved fields), and `0` retail strings. |
| **Technical Manuals, Emblems & Docs Site** | `Live` | `v0.1.0` | `Dev/docs/`, `Dev/assets/`, `.github/workflows/` | Documents `UNROM` topology, schemas, findings, and operations with CI validation and human-first GitHub Pages generation. |
| **Modular Mapped C Modules** | `Planned` | `v0.2.0` | `Dev/scripts/` | Consolidates `68` legacy fragments into cohesive domain C modules and tier snapshots. |
| **Clean Idiomatic C & Zero Warnings** | `Planned` | `v0.3.0` | `Dev/scripts/`, `Dev/schemas/` | Refactors all `499` functions (`0` tells, `-Wall -Wextra -Wno-unused-parameter`). |
| **Execution Lockstep & Bank Decoders** | `Planned` | `v0.4.0` | `Dev/scripts/`, `Dev/docs/specifications/` | Verifies multi-frame RAM/PPU/APU lockstep and decodes Bank `1..4` and audio tables. |
| **Archival Gold Certification** | `Planned` | `v1.0.0` | `Dev/schemas/`, `Dev/scripts/` | Certifies fresh-clone BYO-ROM round-trip, zero-gap specs, and non-prerelease release status. |

## Capability Details

### Clean-Room 6502 Assembler & BYO-ROM Unpacker
- **What it does:** Implements a pure-stdlib two-pass MOS 6502 assembler (`56` official mnemonics, `151` opcodes, `13` addressing modes, `a:` absolute override) alongside a self-contained UNROM unpacker and CFG tracer (`nes_6502_cfg.py`) that reproduces all `8` PRG banks and the `131,088`-byte image (`CRC32=25BA3D04`) without external archive binaries.
- **Entry Points:** [asm6502_d5.py](Dev/scripts/asm6502_d5.py), [build_and_verify_d5.py](Dev/scripts/build_and_verify_d5.py), [nes_unrom_unpack.py](Dev/scripts/nes_unrom_unpack.py), [nes_6502_cfg.py](Dev/scripts/nes_6502_cfg.py)
- **Verification & Tests:** [d5_byte_match.json](Dev/schemas/d5_byte_match.json), [standalone_integrity.json](Dev/schemas/standalone_integrity.json), [test_nes_unpack_and_asm.py](Dev/scripts/tests/test_nes_unpack_and_asm.py)

### Portable `.decomp` Bundle, Release Packager & Verification CLI
- **What it does:** Exports and verifies deterministic `IronFrame-OuterFortress-Cart-01.decomp` archives validated against `reCart` (`0.1.x`) clean-room rules (`0` retail strings, `0` C function bodies, `0` harness/test leaks), stages 10-invariant release bundles, and enforces `12/12` full verification checks (`7/7` offline synthetic) via shared CLI path overrides (`nes_cli_common.py`).
- **Entry Points:** [export_decomp_bundle.py](Dev/scripts/export_decomp_bundle.py), [package_release.py](Dev/scripts/package_release.py), [verify_track_d5.py](Dev/scripts/verify_track_d5.py), [nes_cli_common.py](Dev/scripts/nes_cli_common.py), [decomp_recipe.json](Dev/schemas/decomp_recipe.json)
- **Tests:** [test_decomp_cleanroom_and_release.py](Dev/scripts/tests/test_decomp_cleanroom_and_release.py), [test_scripts_cli_and_schemas.py](Dev/scripts/tests/test_scripts_cli_and_schemas.py)

### Modular Host C Parity Harness
- **What it does:** Runs `10/10` host behavioral assertions across four modular C translation units (`<= 200` lines each), verifying hardware vectors, `$FFD0-$FFD7` UNROM LUT, `$C6B7` inline jump dispatch, `$C94C`/`$C958` bank-switch save/restore, HUD BCD math, countdown timers, transceiver LUTs, and `BANK_06` pause-mute/DMC ramp behavior.
- **Entry Points:** [build_and_verify_d4.py](Dev/scripts/build_and_verify_d4.py), [parity_harness.h](Dev/scripts/d4_harness/parity_harness.h), [parity_runner_main.c](Dev/scripts/d4_harness/parity_runner_main.c), [parity_rom_and_mapper_tests.c](Dev/scripts/d4_harness/parity_rom_and_mapper_tests.c), [parity_gameplay_and_audio_tests.c](Dev/scripts/d4_harness/parity_gameplay_and_audio_tests.c)
- **Verification Output:** [d4_build_report.json](Dev/schemas/d4_build_report.json), [s4_verify_report.json](Dev/schemas/s4_verify_report.json)

### Symbol, Type & Call-Graph Catalog
- **What it does:** Provides clean-room C headers and JSON registries covering the `NES-ME-USA` memory map, `499` named functions across `8` domains, `2,324` mapped globals, and `5` dependency-ordered shards with zero embedded retail strings or C bodies.
- **Entry Points:** [metalgear_types.h](Dev/schemas/metalgear_types.h), [functions_catalog.json](Dev/schemas/functions_catalog.json), [globals_map.json](Dev/schemas/globals_map.json), [call_graph.json](Dev/schemas/call_graph.json), [spec_coverage.json](Dev/schemas/spec_coverage.json)
- **Sub-Headers:** [nes_hardware.h](Dev/schemas/types/nes_hardware.h), [mg_player.h](Dev/schemas/types/mg_player.h), [mg_world.h](Dev/schemas/types/mg_world.h), [mg_audio.h](Dev/schemas/types/mg_audio.h)

### Research Technical Manuals & Documentation Site
- **What it does:** Captures verified `iNES Mapper 2 / UNROM` bus-conflict mechanics (`$FFD0-$FFD7` LUT), `$C6B7` inline jump-table dispatch, reset/NMI/IRQ vectors, and clean-room operations, compiled into a responsive light/dark human-first GitHub Pages site (`pages.yml`) with clean-room emblems (`Dev/assets/`).
- **Entry Points:** [ARCHITECTURE.md](Dev/docs/ARCHITECTURE.md), [SPECIFICATIONS.md](Dev/docs/SPECIFICATIONS.md), [FINDINGS.md](Dev/docs/FINDINGS.md), [OPERATIONS.md](Dev/docs/OPERATIONS.md), [pages.yml](.github/workflows/pages.yml), [ci.yml](.github/workflows/ci.yml)
- **Spokes:** [symbol-and-bank-reference.md](Dev/docs/specifications/symbol-and-bank-reference.md)

### Modular C & Verification Pipeline (`v0.2.0`–`v1.0.0`)
- **What it does:** Builds upon the completed `v0.1.0` `D2/S4/R0` baseline and validated `IronFrame-OuterFortress-Cart-01.decomp` bundle to coalesce `68` legacy C fragments into domain modules (`v0.2.0`), rewrite all `499` functions into warning-free idiomatic C11 (`v0.3.0`), prove multi-scene RAM/PPU/APU execution lockstep (`v0.4.0`), and certify archival Gold status (`v1.0.0`).
- **Entry Points:** [research.manifest.json](Dev/research.manifest.json), [ROADMAP.md](ROADMAP.md)
