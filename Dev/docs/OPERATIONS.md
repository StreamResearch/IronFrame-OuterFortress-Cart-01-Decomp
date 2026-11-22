# Operations — IronFrame OuterFortress (Cart) 01 Decomp (`NES-ME-USA`)

> **Clean-Room BYO-ROM, Multi-Tier Materialization, `D4` Normalization, `.decomp` Packaging & Verification Runbook**

This runbook covers clean-room ROM placement, local `Corpus/` isolation, offline `unittest` and `--offline-synthetic` checks, BYO-ROM unpacking, multi-tier snapshot generation, cohesive module coalescing, zero-tell `D4_CleanSource` AST normalization, 6502 byte-exact reassembly, modular C parity compilation, `.decomp` / release packaging, and downstream `reCart` reference boundaries.

---

## 1. Clean-Room BYO-ROM Layout & Containment

- **Strict Corpus Isolation:** Supply your own legally obtained North American `NES-ME-USA` `.nes` image (`131,088` bytes, `CRC32=25ba3d04`, `SHA256=79095355436222161cb3841ff9b5c7a572e77af11461935e433bd6e8dfd0f164`) inside `Corpus/data/rom/` (or pass `--rom` / `--data-dir`).
- **`Corpus/` Topology (Gitignored & Read-Only Baseline):**
  - `Corpus/standalone/` — Sealed read-only extracted ROM layout verified via Standard 18 v2 [standalone_integrity.json](../schemas/standalone_integrity.json): `1` `requiredRomChecksums` BYO-ROM entry (`data/rom/NES-ME-USA.nes`, `131,088` B) + `17` deterministic `extracted/` entries (`3,717,065` B total: `8` `32,768`-B `.prg` banks, `8` `.s` disassemblies, and `nes_bank_layout.json`). Never edit files inside `Corpus/standalone/` (`nes_unrom_unpack.py` refuses `--out-dir` paths targeting it).
  - `Corpus/tiers/` — Preserved multi-tier local C/export snapshots materialized by [materialize_decomp_tiers.py](../scripts/materialize_decomp_tiers.py): `D1_Raw/` (`8` bank export trees, `555` files), `D2_Structured/` (`68` initial `.c` slices, `80` files), `D3_Mapped/` (`26` cohesive domain `.c` modules, `38` files incl. `SYMBOL_MAP.md` & `ARCHITECTURE_WALKTHROUGH.md`, `0` raw tokens), and `D4_CleanSource/` (`26` zero-tell C11 modules, `507` symbols across `34` `.c`/`.h` files, `0` tells, zero-suppression `.clangd`, strict `compile_commands.json`, `36` files).
  - `Corpus/readable/` — Generated zero-tell `D4_CleanSource` C11 source tree synced from `Corpus/tiers/D4_CleanSource/` (`26` domain `.c` modules, `0` `_01.._NN.c` fragments, `8` headers under `include/` with `2,344` `extern`s in `metalgear_globals.h` and fixed-width `s8..u64`-only `ghidra_compat.h`, strict `.clangd`, and `compile_commands.json` targeting `msp430-unknown-none-elf` — `36` files total).
  - `Corpus/work/` — Unpacked outputs (`unpacked/`), lifted hardware `.s` modules (`lifted_asm/`, `551` lines), exported `.decomp` packages (`extracts/`), and build outputs (`build/{le16,host,d5}/`, `asm_d5/`, `zig-cache/`, `libmetal_gear_d4.a`, `d4_parity_runner.exe`, reassembled `.prg` banks, and `IronFrame_D5.nes`).
- **Shared CLI Containment ([nes_cli_common.py](../scripts/nes_cli_common.py)):** All pipeline CLIs accept `--data-dir`, `--out-dir`, and `--log-dir` (or `IRONFRAME_DATA_DIR` / `RD_DECOMP_TOOLS` / `ZIG_EXE` per [decomp_local.example.json](../schemas/decomp_local.example.json)), emitting exit code `2` with structured `MISSING_CORPUS_MEDIA` JSON when local ROM extracts are absent.
- **Verification Schemas & Ephemeral Isolation:** Tracked JSON schemas (including `5` zero-body `Dev/schemas/d4_rewrites/*.json` shards) and v2 reports live in `Dev/schemas/`, while `Corpus/`, `Dev/data/`, and `Dev/logs/` remain strictly local and gitignored.

---

## 2. Verification & Build Commands

### 2.1 Offline Unit Tests & Synthetic Checks (No ROM Required)

Run all `20` offline `unittest` tests (`test_nes_unpack_and_asm.py`, `test_decomp_cleanroom_and_release.py`, `test_scripts_cli_and_schemas.py`, `test_tiers_and_coalesce.py`, backed by `tests/synthetic_d4_fixtures.py`):

```powershell
python -B -m unittest discover -s Dev/scripts/tests -v
```

Run individual tools in zero-ROM `--offline-synthetic` or `--verify-only` mode:

```powershell
python -B Dev/scripts/nes_unrom_unpack.py --offline-synthetic --out-dir Corpus/work/synth_unpacked
python -B Dev/scripts/coalesce_d4_modules.py --offline-synthetic
python -B Dev/scripts/craftsmanship_d4_normalizer.py --offline-synthetic
python -B Dev/scripts/materialize_decomp_tiers.py --offline-synthetic
python -B Dev/scripts/build_and_verify_d5.py --offline-synthetic
python -B Dev/scripts/build_and_verify_d4.py --offline-synthetic
python -B Dev/scripts/gen_d4_globals_and_lifts.py --verify-only
python -B Dev/scripts/reexport_stage3.py --offline-synthetic
python -B Dev/scripts/verify_track_d5.py --offline-synthetic
```

### 2.2 Self-Contained BYO-ROM Unpacker ([nes_unrom_unpack.py](../scripts/nes_unrom_unpack.py))

Validates a user-supplied `NES-ME-USA` `.nes` file against `standalone_integrity.json` (`CRC32=25ba3d04`, `SHA256`), traces Mapper 2 (`UNROM`) control flow via [nes_6502_cfg.py](../scripts/nes_6502_cfg.py), and writes `8` `.prg` files, `8` `.s` files, and `nes_bank_layout.json` into `--out-dir` (default `Corpus/work/unpacked`):

```powershell
python -B Dev/scripts/nes_unrom_unpack.py --rom path/to/NES-ME-USA.nes --out-dir Corpus/work/unpacked --log-dir Dev/logs
```

### 2.3 Clean-Room 6502 Reassembly & `1:1` ROM Match ([build_and_verify_d5.py](../scripts/build_and_verify_d5.py))

Assembles all `8` PRG banks via [asm6502_d5.py](../scripts/asm6502_d5.py), prepends the NES 2.0 `16`-byte header into `IronFrame_D5.nes`, asserts `0` mismatched bytes across all `8 / 8` `.prg` binaries and the `131,088`-byte ROM, and emits Standard 18 v2 [d5_byte_match.json](../schemas/d5_byte_match.json):

```powershell
python -B Dev/scripts/build_and_verify_d5.py --write-report
```

### 2.4 Multi-Tier Materialization, Cohesive Coalescing & `D4` Normalization ([materialize_decomp_tiers.py](../scripts/materialize_decomp_tiers.py), [coalesce_d4_modules.py](../scripts/coalesce_d4_modules.py), [craftsmanship_d4_normalizer.py](../scripts/craftsmanship_d4_normalizer.py))

Populates `Corpus/tiers/{D1_Raw, D2_Structured, D3_Mapped, D4_CleanSource}` (emitting `<= 15s` `\r\x1b[K` heartbeats while preserving read-only `Corpus/standalone/`), coalesces `68` line-split slices into `26` cohesive modules from [d3_module_map.json](../schemas/d3_module_map.json) (`0` raw tokens, `8` synthesized adapters), transforms all `507` symbols (`34` `.c`/`.h` files) into zero-tell `D4_CleanSource` via [craftsmanship_d4_ast_cleaner.py](../scripts/craftsmanship_d4_ast_cleaner.py) and [craftsmanship_d4_helpers.py](../scripts/craftsmanship_d4_helpers.py) (`0` tells, clean fixed-width `s8..u64` `ghidra_compat.h`, zero-suppression `.clangd`, strict `compile_commands.json`), emits `5` zero-body Standard 18 v2 shards into `Dev/schemas/d4_rewrites/`, and syncs `36` files into `Corpus/readable/`:

```powershell
# Materialize all local tier snapshots and sync Corpus/readable/ (supports --tier {all,D1_Raw,D2_Structured,D3_Mapped,D4_CleanSource}, --data-dir, --tools-dir, --log-dir, --offline-synthetic)
python -B Dev/scripts/materialize_decomp_tiers.py --log-dir Dev/logs

# Coalesce any D2 slice directory directly into cohesive D3 modules (supports --data-dir, --src-dir, --out-dir, --log-dir, --offline-synthetic)
python -B Dev/scripts/coalesce_d4_modules.py --src-dir Corpus/tiers/D2_Structured --out-dir Corpus/tiers/D3_Mapped --log-dir Dev/logs

# Normalize D3_Mapped directly into zero-tell D4_CleanSource and Dev/schemas/d4_rewrites/*.json (supports --data-dir, --src-dir, --out-dir, --rewrites-dir, --log-dir, --offline-synthetic)
python -B Dev/scripts/craftsmanship_d4_normalizer.py --src-dir Corpus/tiers/D3_Mapped --out-dir Corpus/tiers/D4_CleanSource --log-dir Dev/logs
```

### 2.5 Dual-Pass Strict C11 Archive & `D4a` Subsystem Parity ([build_and_verify_d4.py](../scripts/build_and_verify_d4.py))

Compiles all `26` `D4_CleanSource` modules under `STRICT_D4_FLAGS` (`zig cc -target msp430-freestanding-none -std=gnu11 -fsigned-char -O1 -ffreestanding -fno-builtin -Wall -Wextra -Wno-unused-parameter`, zero pointer-cast suppressions) into `libmetal_gear_d4.a`, verifies `count_d4_craftsmanship_tells(Corpus/readable) == 0`, links `TARGET_LINK_FUNCS` against the mapped modular `d4_harness/` suite (`parity_harness.h`, `parity_runner_main.c`, `parity_rom_and_mapper_tests.c`, `parity_gameplay_and_audio_tests.c`) for `10/10` `D4a` subsystem parity assertions, and updates v2 [d4_build_report.json](../schemas/d4_build_report.json) and [s4_verify_report.json](../schemas/s4_verify_report.json) (accepts `--zig-exe`, `--host-target`, `--skip-host-parity`, `--update-manifest`):

```powershell
python -B Dev/scripts/build_and_verify_d4.py
```

### 2.6 Unified Track Gate & Static Semantics ([verify_track_d5.py](../scripts/verify_track_d5.py))

Runs all `15/15` full checks (`9/9` with `--offline-synthetic`), verifying schemas (`d3_module_map.json`, `d3_symbol_overrides.json`, `d4_rewrites/*.json`, `gates.D4`, `d4ParityTier: "D4a"`, `preservedTiers`), SLOC caps, Git clean-room hygiene, `26` zero-tell `.c` modules (`0` `_01.._NN.c` splits, `0` raw tokens, `0` craftsmanship tells, zero-suppression `.clangd`), `Corpus/tiers/{D1_Raw,D2_Structured,D3_Mapped,D4_CleanSource}`, `d4_parity_runner`, `asm6502_d5`, and optional external `R&D` `decomp_cli.py verify --tier D4a` (`--tools-dir`):

```powershell
python -B Dev/scripts/verify_track_d5.py
```

Optional static semantic checks (`clangd`) once `Corpus/readable/` is staged locally:

```powershell
clangd --tweaks=-SwapBinaryOperands --compile-commands-dir=Corpus/readable --check=Corpus/readable/include/metalgear_types.h
clangd --tweaks=-SwapBinaryOperands --compile-commands-dir=Corpus/readable --check=Corpus/readable/src/core/core_unrom_and_math.c
```

### 2.7 Portable `.decomp` Export & Release Staging ([export_decomp_bundle.py](../scripts/export_decomp_bundle.py), [package_release.py](../scripts/package_release.py))

Builds and strictly validates `v0.3.0` `IronFrame-OuterFortress-Cart-01.decomp` (`47` entries, including `d4_build_report.json` and the `5` `Dev/schemas/d4_rewrites/*.json` shards while excluding `d4_harness/` and `tests/`) from [decomp_recipe.json](../schemas/decomp_recipe.json) or stages a full 10-invariant clean-room release mirror (`Latest/`, `SHA256SUMS.txt`, wrapped source ZIP, optional `.7z`):

```powershell
python -B Dev/scripts/export_decomp_bundle.py --verify-cleanroom --strict --log-dir Dev/logs
python -B Dev/scripts/package_release.py --out-dir ./release_stage --log-dir Dev/logs
```

---

## 3. Archival Hygiene & Downstream `reCart` Reference

### 3.1 Clean-Room `.7z` Snapshots (Exclude `Corpus/`)

Every archive under `Archive/` must exclude `Corpus/`, `.git/`, `Dev/data/`, `Dev/logs/`, and `Archive/` itself so copyrighted ROM extracts and local configs never enter `.7z` snapshots:

```powershell
7z a -t7z -mx=9 "Archive\IronFrame-OuterFortress-Cart-01-Decomp-v0.3.0-src.7z" ".\*" "-xr!Corpus" "-xr!Corpus\*" "-xr!.git" "-xr!.git\*" "-xr!Archive" "-xr!Archive\*" "-xr!Dev\data" "-xr!Dev\logs"
```

### 3.2 Downstream Recompilation Target (`reCart`)

Downstream recompilation modules (such as `IronFrame-OuterFortress-Cart-01-Recomp` targeting `reCart` `0.1.x` on `reEngine`) consume published `Dev/schemas/`, `Dev/docs/`, and the tracked `IronFrame-OuterFortress-Cart-01.decomp` package built from [decomp_recipe.json](../schemas/decomp_recipe.json) strictly read-only without copying local `Corpus/` media.
