# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-11-20

### Added
- **BYO-ROM UNROM Unpacker & 6502 CFG Tracer (`nes_unrom_unpack.py`, `nes_6502_cfg.py`):** Added a self-contained iNES Mapper 2 validator, recursive-descent 6502 control-flow tracer, bank-call propagator, and `--offline-synthetic` generator requiring zero external archive binaries.
- **Portable `.decomp` Exporter & Release Packager (`export_decomp_bundle.py`, `package_release.py`, `decomp_recipe.json`):** Built deterministic clean-room `.decomp` archive packaging (`IronFrame-OuterFortress-Cart-01.decomp`) validated against `reCart` (`0.1.x`), alongside a 10-invariant clean-room release stage auditor.
- **Shared CLI Infrastructure & Offline Unit Tests (`nes_cli_common.py`, `Dev/scripts/tests/`):** Centralized `--data-dir`, `--out-dir`, `--log-dir`, `--zig-exe`, `--tools-dir`, and `--offline-synthetic` overrides with exit-code `2` `MISSING_CORPUS_MEDIA` reporting, backed by `14/14` passing offline `unittest` cases (`test_nes_unpack_and_asm.py`, `test_decomp_cleanroom_and_release.py`, `test_scripts_cli_and_schemas.py`).
- **Modular C Host Parity Harness (`Dev/scripts/d4_harness/`):** Split the host parity suite into `parity_harness.h`, `parity_runner_main.c`, `parity_rom_and_mapper_tests.c`, and `parity_gameplay_and_audio_tests.c` (`<= 200` lines each, `10/10` passing assertions).
- **Clean-Room Emblems, CI & Human-First Pages Workflow (`Dev/assets/`, `.github/workflows/`):** Added SVG/PNG/ICO emblems, strict offline Python and clean-room `.decomp` CI checks (`ci.yml`), community health templates (`SECURITY.md`, `CONTRIBUTING.md`), and a visibility-gated GitHub Pages static site generator (`pages.yml`) with `.nojekyll`, `404.html`, `robots.txt`, `sitemap.xml`, responsive light/dark layout, sidebar navigation, TOC, and Mermaid diagrams.
- **Baseline Research Catalog, IDE Workspace & 6502 Assembler (`asm6502_d5.py`, `Dev/schemas/`, `Dev/docs/`):** Consolidated the clean-room `NES-ME-USA` workspace (`499` indexed functions, `2,324` mapped globals, `22` structs, `22` enums, `0` unresolved fields, four technical manuals, portable `.code-workspace`, and a two-pass 6502 assembler matching all `8` PRG banks `1:1` across `131,088` bytes).

### Changed
- **Coded Identity & Honest Milestone Baseline (`D2/S4/R0`):** Adopted the `IronFrame-OuterFortress-Cart-01-Decomp` identity targeting `reCart` (`0.1.x`), verified `12/12` full `verify_track_d5.py` checks (`7/7` offline synthetic), and parameterized host Zig target triples (`x86-windows-gnu` / `x86-linux-gnu`) across `build_and_verify_d4.py`.
- **Schema v2 Migration & Documentation Sync:** Upgraded `standalone_integrity.json` (`1` BYO-ROM checksum + `17` deterministic `extracted/` entries), `d4_build_report.json`, `s4_verify_report.json`, `d5_byte_match.json`, and `spec_coverage.json` to normalized v2 schemas and updated root docs, manuals, and stage notes.

### Fixed
- **UNROM Bank-Switch & Audio Mute Parity Tests (`parity_rom_and_mapper_tests.c`, `parity_gameplay_and_audio_tests.c`):** Replaced folded `$8000` constant assumptions in `test_03` with live `$C94C`/`$C958` bank-ID save/restore checks and updated `test_09` to exercise `mg_b56_audio_sync_pause_mute` and `mg_b56_audio_ramp_dmc_dac`.

### Removed
- **Monolithic Harness & Ghidra Internals (`parity_tests.c`, `standalone_integrity.json`):** Deleted monolithic `Dev/scripts/d4_harness/parity_tests.c` and removed internal `ghidra_project/` (`.gpr`/`.rep`) and `ghidra_export/` entries from `standalone_integrity.json`.

### Security
- **Purged Embedded C Bodies, Workstation PII & Trademark Tokens (`gen_d4_globals_and_lifts.py`, `Dev/schemas/`, `README.md`):** Stripped all four embedded `BANK_06` retail C function bodies and `READABLE_FIXES` from `gen_d4_globals_and_lifts.py`, eliminated hardcoded workstation paths across all Python scripts, and scrubbed commercial trademark tokens across tracked headers, catalogs, and public Markdown documentation.
