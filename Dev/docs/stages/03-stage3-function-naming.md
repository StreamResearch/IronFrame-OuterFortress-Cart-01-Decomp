# IronFrame OuterFortress (Cart) 01 — Stage 3 Function Naming & Classification

- **Title ID:** `NES-ME-USA`
- **Platform / Mapper:** `6502_2a03` / `iNES Mapper 2` (`UNROM`) — `8 x 16 KiB` PRG banks
- **Completion Target:** `499 / 499` game functions named (`0` SDK functions, `0` placeholders, `0` duplicates)

## 1. Anchor vs. Sharded Function Naming Split

| Source File | Bank Scope | Prefix / Role | Count | Status |
| :--- | :--- | :--- | :---: | :--- |
| [anchor_functions.json](../../schemas/anchor_functions.json) | All banks (`PRG_FIXED_07` + `BANK_00`..`06`) | Reset/NMI/MMIO/Trampoline/Dispatch anchors | `39` | Verified |
| [stage3_shard_1.json](../../schemas/shards/stage3_shard_1.json) | `PRG_FIXED_07.prg` (low `$C000–$DF00`) | `mg_fxa_*` (core loop, input, map/tile, HUD) | `104` | Verified |
| [stage3_shard_2.json](../../schemas/shards/stage3_shard_2.json) | `PRG_FIXED_07.prg` (high `$DF00–$FFF9`) | `mg_fxb_*` (combat, collisions, codec, scroll) | `105` | Verified |
| [stage3_shard_3.json](../../schemas/shards/stage3_shard_3.json) | `BANK_01.prg`, `BANK_02.prg` | `mg_b12_*` (bank 1 stubs, boss/enemy AI bank 2) | `89` | Verified |
| [stage3_shard_4.json](../../schemas/shards/stage3_shard_4.json) | `BANK_00.prg`, `BANK_03.prg`, `BANK_04.prg` | `mg_b034_*` (weapons/items, codec/story, world rooms) | `107` | Verified |
| [stage3_shard_5.json](../../schemas/shards/stage3_shard_5.json) | `BANK_05.prg`, `BANK_06.prg` | `mg_b56_*` (APU music/SFX driver, credits/ending) | `55` | Verified |
| **Total Merged Catalog** | **All 8 UNROM Banks** | [functions_catalog.json](../../schemas/functions_catalog.json) | **`499`** | **100%** |

## 2. Engine Naming Taxonomy

1. **Vector & Hardware Anchors (`mg_vec_*`, `mg_ppu_*`, `mg_joy_*`, `mg_apu_*`):**
   - Reset (`$C001`), NMI (`$C06C`), IRQ/BRK (`$C0B7`), PPU OAM DMA (`$4014`), joypad strobe (`$4016`), and bus-conflict-safe UNROM bankswitch helpers (`$C932–$C958`).
2. **Inline Jump-Table & Cross-Bank Trampolines (`mg_dispatch_*`, `mg_trampoline_*`):**
   - The `JSR $C6B7` (`mg_dispatch_inline_jump_table`) primitive consumes the 16-bit index/pointer following the return address on the stack; marked `NoReturn` during static analysis so downstream callers terminate cleanly.
3. **Bank-Prefixed Gameplay Subsystems (`mg_fxa_*`, `mg_fxb_*`, `mg_b12_*`, `mg_b034_*`, `mg_b56_*`):**
   - Distinct module prefixes guarantee zero symbol collisions across the 7 switchable `$8000–$BFFF` banks in [functions_catalog.json](../../schemas/functions_catalog.json) and flat-linked C builds.

## 3. Re-Export & Bundle Verification

- **Bundler Output:** Produced `Corpus/work/ghidra_stage_bundle.json` and [functions_catalog.json](../../schemas/functions_catalog.json) with `total: 499`, `non_sdk_total: 499`, `missing: 0`, `sdk_reserved: 0`.
- **Single-JVM Headless Re-Export:** [reexport_stage3.py](../../scripts/reexport_stage3.py) runs headless export across all `8` `.prg` programs using temporary staging in `Corpus/work/_ghidra_stage3_tmp/`, emitting fresh C, labels, globals, and call graphs into `Corpus/work/ghidra_reexport/` (`8/8` programs, `499` functions exported).
