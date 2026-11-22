# Features — IronFrame OuterFortress (Cart) 01 Decomp

Overview of what this repository supports today (`v0.3.0` zero-tell idiomatic C11 and `D4a` subsystem parity baseline) and what is scheduled across upcoming milestones. See [ROADMAP.md](ROADMAP.md) for the full release plan.

## Feature Summary

| Feature | Status | Target | Primary Code | What It Does |
| :--- | :--- | :--- | :--- | :--- |
| **Clean-Room 6502 Assembler** | `Live` | `v0.1.0` | `Dev/scripts/asm6502_d5.py` | Assembles symbolic 6502 source (`56` mnemonics, `151` opcodes) to `1:1` ROM bytes (`8/8` banks). |
| **Self-Contained BYO-ROM Unpacker** | `Live` | `v0.1.0` | `Dev/scripts/nes_unrom_unpack.py` | Validates `.nes` SHA-256/CRC32, splits Mapper 2 banks, traces CFG (`nes_6502_cfg.py`), and supports `--offline-synthetic`. |
| **Cohesive Domain C Modules & Tiers** | `Live` | `v0.2.0` | `Dev/scripts/coalesce_d4_modules.py`, `Dev/scripts/materialize_decomp_tiers.py` | Consolidates `68` line-split fragments into `26` domain C modules (`499/499` functions), resolves all `299` raw globals & `44` raw calls (`0` raw tokens, `8` synthesized adapters), and preserves `D1_Raw`–`D4_CleanSource` local tiers. |
| **Clean Idiomatic C & Zero Warnings** | `Live` | `v0.3.0` | `Dev/scripts/craftsmanship_d4_{helpers,ast_cleaner,normalizer}.py` | Eliminates all decompiler tells across `34` C/header files (`507` symbols), compiles `26/26` modules with `0` errors/warnings under `-Wall -Wextra -Wno-unused-parameter`, emits `5` zero-body `d4_rewrites/*.json` shards, and syncs `36` files into `Corpus/readable/`. |
| **Portable `.decomp` Bundle & Packager** | `Live` | `v0.3.0` | `Dev/scripts/export_decomp_bundle.py` | Emits `reCart` (`0.1.x`) validated `v0.3.0` `IronFrame-OuterFortress-Cart-01.decomp` (`47` entries including `d4_build_report.json` and `5` `d4_rewrites/*.json` shards) and 10-invariant release mirrors (`package_release.py`). |
| **Offline Unit Tests & Modular Parity** | `Live` | `v0.3.0` | `Dev/scripts/tests/`, `d4_harness/` | Passes `20/20` offline `unittest` tests (`-W error`), `15/15` `verify_track_d5.py` checks (`9/9` synthetic), and `10/10` `D4a` subsystem parity assertions (`26/26` compiled modules, `0` warnings). |
| **Symbol, Module & Call-Graph Catalog** | `Live` | `v0.3.0` | `Dev/schemas/` | Indexes `507` symbols across `26` domain modules (`499` functions + `8` adapters), `2,324` mapped globals (`2,344` header externs), `44` call overrides, `22` structs, `22` enums (`0` unresolved fields), `5` rewrite shards, and `0` retail strings. |
| **Technical Manuals, Emblems & Docs Site** | `Live` | `v0.1.0` | `Dev/docs/`, `Dev/assets/`, `.github/workflows/` | Documents `UNROM` topology, schemas, findings, and operations with CI validation and human-first GitHub Pages generation. |
| **Execution Lockstep & Bank Decoders** | `Planned` | `v0.4.0` | `Dev/scripts/`, `Dev/docs/specifications/` | Verifies multi-frame RAM/PPU/APU oracle lockstep (`D4b`) and decodes Bank `1..4` and audio tables. |
| **Archival Gold Certification** | `Planned` | `v1.0.0` | `Dev/schemas/`, `Dev/scripts/` | Certifies fresh-clone BYO-ROM round-trip, zero-gap specs, and non-prerelease release status. |

## Capability Details

### Clean Idiomatic C11 Normalizer & Zero-Body Rewrite Shards
- **What it does:** Transforms all `26` cohesive C modules (`507` symbols = `499` catalog functions + `8` synthesized adapters across `34` C/header files) into zero-tell idiomatic C11 (`0` decompiler tells, `0` warnings under `-Wall -Wextra -Wno-unused-parameter`): removes dead stack locals, zero-initializes and renames register/SSA locals, unrolls `69` comma-operator `if` conditions, parenthesizes `55` bitwise `&` expressions, lowers P-code macros and typed pointer/array accesses (`g_actor_soa_ram[128]`, `g_apu_mmio_regs[24]`), emits clean fixed-width `ghidra_compat.h` (`s8..u64` only) plus zero-suppression `.clangd` and `compile_commands.json`, syncs `36` files into `Corpus/readable/`, and generates `5` dependency-grouped zero-body JSON shards under `Dev/schemas/d4_rewrites/`.
- **Entry Points:** [craftsmanship_d4_helpers.py](Dev/scripts/craftsmanship_d4_helpers.py), [craftsmanship_d4_ast_cleaner.py](Dev/scripts/craftsmanship_d4_ast_cleaner.py), [craftsmanship_d4_normalizer.py](Dev/scripts/craftsmanship_d4_normalizer.py), [d4_rewrites/](Dev/schemas/d4_rewrites/)
- **Verification & Tests:** [test_tiers_and_coalesce.py](Dev/scripts/tests/test_tiers_and_coalesce.py), [synthetic_d4_fixtures.py](Dev/scripts/tests/synthetic_d4_fixtures.py), [d4_build_report.json](Dev/schemas/d4_build_report.json)

### Cohesive Domain C Coalescer & Multi-Tier Snapshots
- **What it does:** Merges all `499` functions out of `68` line-split fragments into `26` domain-grouped C modules (`10` fixed-bank core modules + `16` switchable-bank overlay modules), resolves `1` local label, `22` synthetic/bank-scoped alias entries (`20` deduplicated externs), and `44` raw cross-bank function calls with `0` remaining raw tokens, synthesizes `8` clean-room bank/signature adapters and `9` sub-entry prototypes (`factor`, `table_index`), and materializes preserved `D1_Raw`, `D2_Structured`, `D3_Mapped`, and `D4_CleanSource` local snapshot tiers (`36` synced files in `Corpus/readable/`).
- **Entry Points:** [coalesce_d4_modules.py](Dev/scripts/coalesce_d4_modules.py), [materialize_decomp_tiers.py](Dev/scripts/materialize_decomp_tiers.py), [d3_module_map.json](Dev/schemas/d3_module_map.json), [d3_symbol_overrides.json](Dev/schemas/d3_symbol_overrides.json)
- **Verification & Tests:** [test_tiers_and_coalesce.py](Dev/scripts/tests/test_tiers_and_coalesce.py), [d4_build_report.json](Dev/schemas/d4_build_report.json)

### Clean-Room 6502 Assembler & BYO-ROM Unpacker
- **What it does:** Implements a pure-stdlib two-pass MOS 6502 assembler (`56` official mnemonics, `151` opcodes, `13` addressing modes, `a:` absolute override) alongside a self-contained UNROM unpacker and CFG tracer (`nes_6502_cfg.py`) that reproduces all `8` PRG banks and the `131,088`-byte image (`CRC32=25BA3D04`) without external archive binaries.
- **Entry Points:** [asm6502_d5.py](Dev/scripts/asm6502_d5.py), [build_and_verify_d5.py](Dev/scripts/build_and_verify_d5.py), [nes_unrom_unpack.py](Dev/scripts/nes_unrom_unpack.py), [nes_6502_cfg.py](Dev/scripts/nes_6502_cfg.py)
- **Verification & Tests:** [d5_byte_match.json](Dev/schemas/d5_byte_match.json), [standalone_integrity.json](Dev/schemas/standalone_integrity.json), [test_nes_unpack_and_asm.py](Dev/scripts/tests/test_nes_unpack_and_asm.py)

### Portable `.decomp` Bundle, Release Packager & Verification CLI
- **What it does:** Exports and verifies deterministic `v0.3.0` `IronFrame-OuterFortress-Cart-01.decomp` archives (`47` entries, including `d4_build_report.json` and the `5` `d4_rewrites/*.json` shards) validated against `reCart` (`0.1.x`) clean-room rules (`0` retail strings, `0` C function bodies, `0` harness/test leaks), stages 10-invariant release bundles, and enforces `15/15` full verification checks (`9/9` offline synthetic) via shared CLI path overrides (`nes_cli_common.py`).
- **Entry Points:** [export_decomp_bundle.py](Dev/scripts/export_decomp_bundle.py), [package_release.py](Dev/scripts/package_release.py), [verify_track_d5.py](Dev/scripts/verify_track_d5.py), [nes_cli_common.py](Dev/scripts/nes_cli_common.py), [decomp_recipe.json](Dev/schemas/decomp_recipe.json)
- **Tests:** [test_decomp_cleanroom_and_release.py](Dev/scripts/tests/test_decomp_cleanroom_and_release.py), [test_scripts_cli_and_schemas.py](Dev/scripts/tests/test_scripts_cli_and_schemas.py)

### Modular Host C Parity Harness
- **What it does:** Compiles all `26` `D4_CleanSource` domain C modules under `-Wall -Wextra -Wno-unused-parameter` (`0` errors, `0` warnings, `0` decompiler tells, zero pointer-cast suppressions) and runs `10/10` `D4a` subsystem parity assertions across four modular C translation units (`<= 200` lines each), verifying hardware vectors, `$FFD0-$FFD7` UNROM LUT, `$C6B7` inline jump dispatch, `$C94C`/`$C958` bank-switch save/restore, HUD BCD math, countdown timers, transceiver LUTs, and `BANK_06` pause-mute/DMC ramp behavior using mapped `g_*` globals.
- **Entry Points:** [build_and_verify_d4.py](Dev/scripts/build_and_verify_d4.py), [parity_harness.h](Dev/scripts/d4_harness/parity_harness.h), [parity_runner_main.c](Dev/scripts/d4_harness/parity_runner_main.c), [parity_rom_and_mapper_tests.c](Dev/scripts/d4_harness/parity_rom_and_mapper_tests.c), [parity_gameplay_and_audio_tests.c](Dev/scripts/d4_harness/parity_gameplay_and_audio_tests.c)
- **Verification Output:** [d4_build_report.json](Dev/schemas/d4_build_report.json), [s4_verify_report.json](Dev/schemas/s4_verify_report.json)

### Symbol, Type & Call-Graph Catalog
- **What it does:** Provides clean-room C headers and JSON registries covering the `NES-ME-USA` memory map, `499` named functions across `8` domains and `26` modules (`507` symbols with `8` synthesized adapters), `2,324` mapped globals (`2,344` header externs), `22` synthetic/bank-scoped symbol overrides, `44` cross-bank call mappings, and `5` zero-body rewrite shards (`core_runtime.json`, `core_gameplay.json`, `overlays_b00_b02.json`, `overlays_b03_b04.json`, `overlays_b05_b06.json`) with zero embedded retail strings or C bodies.
- **Entry Points:** [metalgear_types.h](Dev/schemas/metalgear_types.h), [functions_catalog.json](Dev/schemas/functions_catalog.json), [globals_map.json](Dev/schemas/globals_map.json), [d3_module_map.json](Dev/schemas/d3_module_map.json), [d3_symbol_overrides.json](Dev/schemas/d3_symbol_overrides.json), [d4_rewrites/](Dev/schemas/d4_rewrites/), [call_graph.json](Dev/schemas/call_graph.json), [spec_coverage.json](Dev/schemas/spec_coverage.json)
- **Sub-Headers:** [nes_hardware.h](Dev/schemas/types/nes_hardware.h), [mg_player.h](Dev/schemas/types/mg_player.h), [mg_world.h](Dev/schemas/types/mg_world.h), [mg_audio.h](Dev/schemas/types/mg_audio.h)

### Research Technical Manuals & Documentation Site
- **What it does:** Captures verified `iNES Mapper 2 / UNROM` bus-conflict mechanics (`$FFD0-$FFD7` LUT), `$C6B7` inline jump-table dispatch, reset/NMI/IRQ vectors, `26`-module `D4_CleanSource` layout, and clean-room operations, compiled into a responsive light/dark human-first GitHub Pages site (`pages.yml`) with clean-room emblems (`Dev/assets/`).
- **Entry Points:** [ARCHITECTURE.md](Dev/docs/ARCHITECTURE.md), [SPECIFICATIONS.md](Dev/docs/SPECIFICATIONS.md), [FINDINGS.md](Dev/docs/FINDINGS.md), [OPERATIONS.md](Dev/docs/OPERATIONS.md), [pages.yml](.github/workflows/pages.yml), [ci.yml](.github/workflows/ci.yml)
- **Spokes:** [symbol-and-bank-reference.md](Dev/docs/specifications/symbol-and-bank-reference.md)

### Execution Lockstep & Gold Pipeline (`v0.4.0`–`v1.0.0`)
- **What it does:** Builds upon the completed `v0.3.0` zero-tell, warning-free `D4_CleanSource` codebase and validated `47`-entry `IronFrame-OuterFortress-Cart-01.decomp` bundle to prove multi-scene WRAM/OAM/PPU/APU execution lockstep (`v0.4.0`, `D4b`) alongside Bank `1..4` and audio table decoders, and certify archival Gold status (`v1.0.0`).
- **Entry Points:** [research.manifest.json](Dev/research.manifest.json), [ROADMAP.md](ROADMAP.md)
