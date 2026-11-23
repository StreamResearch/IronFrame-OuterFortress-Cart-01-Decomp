# Findings — IronFrame OuterFortress (Cart) 01 Decomp (`NES-ME-USA`)

> **Verification Ledger:** `0` Static Decompiler Failures (`499/499` indexed) · `26/26` Zero-Tell `D4_CleanSource` Modules (`507` Symbols, `0` Warnings under `-Wall -Wextra -Wno-unused-parameter`) · `8/8` PRG Banks `1:1` 6502 Assembly Match (`131,088` B, `CRC32=25BA3D04`) · `10/10` `D4a` Assertions · `650/650` `D4b` Lockstep Frames (`mismatchedFrames: 0` vs. Mesen 2.1.1 + `reCart` Witness + `8/8` Linked C Checkpoints) · `unresolvedFieldCount: 0` Across `4` Decoders & `4` Spokes

This document records empirical reverse-engineering discoveries, UNROM bus-conflict mechanics, `BANK_06` sound-sequencer recovery, `D3_Mapped` cohesive coalescing, `D4_CleanSource` AST C11 normalization (`craftsmanship_d4_*`), `D4b` hardware timing lockstep (`NesBus`), Bank `1..4` / `BANK_06` decoder coverage, upstream validator alignment notes, and `1:1` 6502 byte-matching results.

---

## 1. UNROM Bus-Conflict LUT (`$C959` / `$FFD0`) & Trampolines

- **Hardware Constraint:** Discrete `iNES Mapper 2` (`UNROM`) cartridges lack bus-conflict suppression circuitry (`74HC161` latch + `74HC32` OR gate). Writing a bank index to `$8000-$FFFF` corrupts the latch unless the PRG ROM byte at that exact write address equals the written bank number.
- **NES-ME-USA Implementation:** Fixed bank `PRG_FIXED_07` places an `8`-byte identity lookup table `{0, 1, 2, 3, 4, 5, 6, 7}` at `$FFD0-$FFD7` (verified against `PRG_FIXED_07` at offset `0x7FD0 + i == i` by `test_01_vectors_and_unrom` in [parity_rom_and_mapper_tests.c](../scripts/d4_harness/parity_rom_and_mapper_tests.c)), paired with the `$C932..$C958` trampolines and `$C959` adjacent switch table/helper:
  - Fixed per-bank stubs at `$C932..$C94A` (`unrom_select_bank_0`..`6`, `4`-byte stride).
  - Indexed trampoline `$C94C` (`unrom_select_bank_y` / `unrom_select_bank_index`), emitting at `$C94F`: `85 27 B9 D0 FF 99 D0 FF 60` (`STA $27; LDA $FFD0,Y; STA $FFD0,Y; RTS`). Note: static analysis over `PRG_FIXED_07` with `BANK_00` mounted at `$8000` constant-folded `LDA $8000` (`$C94C`) to `0` in early generated C; `test_03_unrom_bank_switch` in [parity_rom_and_mapper_tests.c](../scripts/d4_harness/parity_rom_and_mapper_tests.c) checks exact `$C94C`/`$C958` opcode sequences and live `unrom_select_bank_0`/`6` transitions (`v0.2.0` synthesized `3` cross-bank trampolines + `5` signature adapters and `v0.3.0` normalized `D4_CleanSource` to `D4a` subsystem parity, while multi-frame `D4b` RAM-oracle lockstep awaits `v0.4.0`).
  - Restore stub `$C958` (`unrom_restore_active_bank`), reloading the bank shadowed in Zero Page `$27`.
- **Inline Jump-Table Control Flow (`$C6B7`):**
  - `inline_jump_table_dispatch` (`16+` call sites) reads an inline `.word[]` target immediately following `JSR $C6B7` off the 6502 hardware stack (`$0100+S`), scales accumulator `A * 2`, and executes `jmp ($0080)` (`$C6D2: 6C 80 00`).
  - Marking `$C6B7` as `NoReturn` during static analysis stops the disassembler from decoding trailing inline data tables as 6502 instructions and preserves clean switch semantics across `BANK_00..06` and `PRG_FIXED_07`.

---

## 2. Recovery of 4 `BANK_06` Audio Sequencer Routines

Initial automated decompilation left `4` failed functions concentrated in `BANK_06` audio sequencer recursion (`$94ED <-> $96E4` is the sole nontrivial SCC in [call_graph.json](../schemas/call_graph.json)). Structural control-flow recovery of these `4` routines resolved all export failures (`4 -> 0`, `499 / 499` active functions):

| Address | Function Name | Role in `BANK_06` Audio Driver |
| :--- | :--- | :--- |
| `$9382` | `mg_b56_audio_update_channel` | Per-frame channel envelope, pitch, and timer advance |
| `$94EA` | `mg_b56_audio_dispatch_seq_mode` | Dispatches channel playback state into sequence parser |
| `$94ED` | `mg_b56_audio_parse_seq_event` | Decodes note/rest/control stream events (mutually recursive with `$96E4`) |
| `$96E4` | `mg_b56_audio_exec_control_opcode` | Executes loop, jump, transpose, and instrument control opcodes |

*(Clean-room note: in `v0.1.0`, all embedded retail `BANK_06` C bodies and `READABLE_FIXES` were purged from [gen_d4_globals_and_lifts.py](../scripts/gen_d4_globals_and_lifts.py), leaving a clean-room `2,324`-global mapper and Standard 18 v2 `spec_coverage.json` generator.)*

---

## 3. Cohesive `D3_Mapped` & Zero-Tell `D4_CleanSource` Normalization (`Corpus/readable/`)

Early `D2_Structured` normalization resolved initial syntax blockers across the `68` line-split `.c` fragments without modifying read-only `Corpus/standalone/` (synthesizing `44` missing forward declarations, fixing call-site arity in `core_15.c` and `bank_02_06.c`, normalizing indirect function-pointer casts across `11` `.c` files, label syntax in `bank_05_02.c`, and return emission in `core_32.c`).

In `v0.2.0` (`D3_Mapped`), [coalesce_d4_modules.py](../scripts/coalesce_d4_modules.py) and [materialize_decomp_tiers.py](../scripts/materialize_decomp_tiers.py) consolidated that intermediate baseline into **`26` cohesive domain C modules** (`0` `_01.._NN.c` fragments, `0` remaining raw tokens across `.c` and headers) while preserving `D1_Raw` and `D2_Structured` snapshots:

- **Full Raw Symbol & Call Resolution (`0` Remaining Raw Tokens):** Applied [d3_symbol_overrides.json](../schemas/d3_symbol_overrides.json) and [globals_map.json](../schemas/globals_map.json) to eliminate all `299` raw extern aliases and `44` raw `FUN_*`/`func_0x*` call references, including `1` local label rename (`BYTE_ARRAY_8000_6486_ -> lbl_demo_input_loop`) and `20` initial synthetic/bank-scoped overrides (`2,342` `extern`s at `D3`, expanded in `D4` to `22` entries / `20` deduplicated `g_*` declarations = `2,344` `extern`s).
- **Bank-Scoped Table & Bitwise `&` Precision:** Disambiguated address collisions by explicitly mapping `BYTE_ARRAY_bf00` to `BANK_03.prg` (`g_b03_rom_tbl_bf00`) and `FUN_b622` to `BANK_01.prg` (`g_b01_rom_tbl_b622`), separating indexed `(&DAT_0740)[i]` writes (`g_vram_transfer_queue[i]`) from scalar `DAT_0740` reads (`g_vram_transfer_queue[0]`), and gating address-of `&` stripping so bitwise `&` expressions (`g_frame_counter & g_b00_rom_tbl_b995[0]`) remain intact.
- **Synthesized `8` Bank/Signature Adapters & `9` Sub-Entry Prototypes:** Emitted `3` cross-bank trampolines (`$F5AC`, `$FBF5`, `$EE2A`) and `5` signature-adapting wrappers (`$99A8`, `$A765`, `$BB28`, `$B83A`, `$BBE1`) declaratively into `src/core/core_unrom_and_math.c`, plus `9` `subEntryDeclarations` prototypes in `metalgear_functions.h`.
- **Zero-Tell `D4_CleanSource` AST Normalization (`v0.3.0`, `0` Tells & `0` Warnings):** [craftsmanship_d4_normalizer.py](../scripts/craftsmanship_d4_normalizer.py), [craftsmanship_d4_ast_cleaner.py](../scripts/craftsmanship_d4_ast_cleaner.py), and [craftsmanship_d4_helpers.py](../scripts/craftsmanship_d4_helpers.py) eliminated all `2,874` baseline decompiler idioms from `D3_Mapped` (`craftsmanshipTellCount: 0` across all `34` `.c`/`.h` files and `507` symbols = `499` catalog functions + `8` adapters, `0` `SixTellDetector` findings):
  - Removed dead `[ubcs]Stack0000` variables (`284` `-Wunused-but-set-variable`), renamed and zero-initialized `in_*`/`unaff_retaddr*`, `[ubcs]Var*`, `pbVar*`, and SSA `_00` locals (`199` `-Wuninitialized` + `29` `-Wsometimes-uninitialized`), and renamed `arg0` sub-entry parameters (`factor`, `table_index`) plus header placeholder fields (`mg_player.h`, `nes_hardware.h`).
  - Unrolled all `69` comma-operator `if (...)` conditions while preserving short-circuit `&&`/`||` semantics, parenthesized `55` bitwise `&` inside `|`/`^` expressions (`-Wbitwise-op-parentheses`), lowered `CONCAT11`/`CARRY1`/subpiece byte accesses/`(short)(&g_* + idx)` ROM offsets/`(&g_*)[idx]` scalar-as-array reads (backed by `g_actor_soa_ram[128]` at `$0300` and `g_apu_mmio_regs[24]` at `$4000`), wrapped computed int-to-pointer expressions via `(uintptr_t)(...)`, replaced `while (true)`/`LAB_*`/`joined_r0x*`/`halt_baddata`/Yoda comparisons, stripped Ghidra boilerplate (`WARNING:`, `// Function:`, `@callers`/`@callees none`), and injected `* @symbol` + module headers.
  - Replaced legacy P-code macros in `include/ghidra_compat.h` with fixed-width `s8..u64` typedefs (`#ifndef GHIDRA_COMPAT_FIXED_INTS`), removed all `.clangd` diagnostic suppressions and pointer-cast suppressions (`-Wno-int-to-pointer-cast`), synced `36` files into `Corpus/readable/`, and emitted `5` zero-body Standard 18 v2 shards in [d4_rewrites/](../schemas/d4_rewrites/) (`26` files / `507` symbols).
- **Mapped Modular Host Parity Suite (`10/10` Passing, `D4a` Subsystem Parity):** Compiled `26/26` `D4_CleanSource` modules with `0` errors and `0` warnings under `-std=gnu11 -fsigned-char -O1 -ffreestanding -fno-builtin -Wall -Wextra -Wno-unused-parameter` (`isZeroWarningsVerified: true`, `isZeroDecompilerTellsVerified: true` in [d4_build_report.json](../schemas/d4_build_report.json)), linked against the four `<= 200`-line files under `Dev/scripts/d4_harness/` — [parity_harness.h](../scripts/d4_harness/parity_harness.h), [parity_runner_main.c](../scripts/d4_harness/parity_runner_main.c), [parity_rom_and_mapper_tests.c](../scripts/d4_harness/parity_rom_and_mapper_tests.c), and [parity_gameplay_and_audio_tests.c](../scripts/d4_harness/parity_gameplay_and_audio_tests.c).
- **Parity Scope Progression (`D4a` -> `v0.4.0` `D4b`):** `v0.3.0` established `D4a Subsystem Parity` (`10/10` host assertions + freestanding zero-warning compilation). In `v0.4.0`, [d4_harness/](../scripts/d4_harness/), [d4b_oracle_bridges.py](../scripts/d4b_oracle_bridges.py), and [run_d4b_lockstep.py](../scripts/run_d4b_lockstep.py) advance the repository to verified **`D4b Execution Parity`** (`mismatchedFrames: 0` across `650` frames / `5` gameplay scenes, detailed in Section 5 below).

---

## 4. Clean-Room 6502 Byte-Exact Assembly ([asm6502_d5.py](../scripts/asm6502_d5.py))

[asm6502_d5.py](../scripts/asm6502_d5.py) implements a standalone, zero-external-ROM clean-room MOS 6502 two-pass assembler (`56 / 56` official mnemonics, `151 / 151` opcodes, `13` addressing modes, plus `a:` absolute-encoding override to prevent unwanted zero-page relaxation). Executed via [build_and_verify_d5.py](../scripts/build_and_verify_d5.py):

- **Bank Images:** `8 / 8` `32,768`-byte `.prg` images (`BANK_00`..`BANK_06`, `PRG_FIXED_07`) match standalone SHA-256 digests (`0` byte mismatches; note `PRG_FIXED_07.prg` and `BANK_00.prg` share SHA-256 `96d482df...` because both pair `BANK_00` with `PRG_FIXED_07`).
- **Full Cartridge Image:** Reassembled `131,088`-byte ROM (NES 2.0 header + `8 x 16 KiB` PRG banks) achieves a **`1:1` byte-exact retail match** (`CRC32=25ba3d04`, `MD5=0e514c68eb8d82342a71a74c6d52499b`, `SHA1=9f7448fddaedc1801e2970e50722ac3cfacd19b8`, `SHA256=79095355436222161cb3841ff9b5c7a572e77af11461935e433bd6e8dfd0f164`) recorded in [d5_byte_match.json](../schemas/d5_byte_match.json).

---

## 5. `D4b` Multi-Scene Execution Parity & Hardware Timing Findings

In `v0.4.0`, clean-room C11 [NesBus](../scripts/d4_harness/nes_bus.h) (`nes_bus.c`, `nes_ppu_apu.c`, `nes_cpu_ops.c`, `nes_cpu_exec.c`, `d4b_lockstep_scenes.c`) executed all `650` deterministic frames across `5` gameplay scenes against Mesen 2.1.1 (`--testRunner` Lua tracer) with **`mismatchedFrames: 0`** recorded in [d4b_lockstep_report.json](../schemas/d4b_lockstep_report.json) (`assertionsPassedCount: 7/7`), while simultaneously running `8/8` live `D4_CleanSource` linked C checkpoints and cross-checking the read-only `reCart.Core.dll` `InterpreterOracle` differential witness:

| Scene / Witness Check (`d4b_lockstep_report.json`) | Frame Range | Verification Scope & Observed Result |
| :--- | :--- | :--- |
| `scene_1_boot_and_title` | `1..100` | Cold boot reset (`$C001`) through title idle (`mismatched=0`, digest `e83cf9a209d62203`) |
| `scene_2_intro_to_dock` | `101..220` | Start pulses (`105..109`, `140..144`) through intro transition to dock (`mismatched=0`, digest `57e0058e7548977a`) |
| `scene_3_dock_traversal` | `221..380` | Right (`260..320`) + Up (`325..385`) movement across dock (`mismatched=0`, digest `4a9f2a1a0e9004f0`) |
| `scene_4_transceiver_and_pause` | `381..520` | Select (`410..414`, `460..464`) + Start (`485..489`, `505..509`) transceiver/pause (`mismatched=0`, digest `6807e97dee50d796`) |
| `scene_5_combat_action` | `521..650` | Periodic Up + B bursts every 20 frames (`mismatched=0`, digest `5c13c20f66adbfa9`) |
| `d4_clean_source_checkpoints` | `1, 100, 110, 220, 320, 380, 490, 650` | `8/8` live `D4_CleanSource` C subsystem checkpoints (`unrom_select_bank_0/6`, `mg_fxa_*`, `mg_b034_*`, `mg_b56_audio_*`) |
| `recart_interpreter_oracle_witness` | `1..650` | Read-only `reCart.Core.dll` `InterpreterOracle`: `frames=650`, `transitions=649`, `nonZeroFinalBytes=431`, `bootWramCrc32=f1e8ba9e` (matching Mesen frame `1`), `finalWramCrc32=fbe7de47`, `sha=ce8f4c3a3562a378` |

### Empirical RP2A03 / RP2C02 Lockstep Requirements
- **NMI-Driven Main Loop & Zero Sprite-0 Usage:** Static analysis across all `8` PRG banks confirmed `0` Sprite-0 hit polling loops (`$2002` bit 6) and a pure NMI-driven main loop (`$C069: JMP $C069` + `$C06C` VBlank NMI).
- **Exact PPU Frame & Odd-Frame Timing (`nes_ppu_apu.c`):** Bit-exact `PPU`/`WRAM` parity over `650` frames required scanline `241` dot `1` VBlank NMI edge triggering, scanline `261` dot `1` status flag clearing, the odd-frame dot-`339` pre-render skip when `(frame_count & 1) && (mask & 0x18)`, and capturing frame digests cleanly at scanline `240` (with resume-state checkpointing across instruction boundaries near dot `312` of scanline `239`).
- **RP2A03 CPU & DMA Quirks (`nes_cpu_ops.c`, `nes_cpu_exec.c`, `nes_bus.c`):** Matching Mesen 2.1.1 required RP2A03 binary-only `ADC`/`SBC` (ignoring `P` decimal flag `D`), `JMP ($xxFF)` page-boundary low-byte wrap, `$4014` OAM DMA `513 + (cycles & 1)` cycle stalls, and DMC DMA 3–4 cycle stalls (`$4016` double-clocking when a DMC fetch coincides with controller read).
- **`$0100-$01FF` Hardware Stack Masking:** Zero-masking the 6502 hardware stack page (`$0100-$01FF`) isolates deterministic gameplay WRAM/OAM/PPU/APU equivalence cleanly across C11 `NesBus`, Mesen 2.1.1, and `reCart.Core.dll` without raw memory dumps in tracked JSON reports.

---

## 6. Bank `1..4` / `BANK_06` Decoder Coverage & Upstream Validator Note

- **Complete Clean-Room Decoder Coverage (`unresolvedFieldCount: 0`):** Executing [decode_all_bank_tables.py](../scripts/decode_all_bank_tables.py) (`--write-spec-coverage`) resolves `256` rooms (`165` unique `8x6` grids), `6` metatile/attribute tilesets, `18` door returns, `8` elevators, `17` special warps, `256` adjacency vectors (`235` unique), `51` CHR upload headers, `256` `$FD00/$FE00` room metadata records, `123` patrol pointers (`96` unique), `160` dialog pointer offsets (`144` unique, byte span metadata only with `0` retail strings), `217` room actor spawns (`85` unique), `7` weapon/projectile tables, `4` password layout tables, `7` codec frequencies, `255` room call tables (`75` unique, `116` entries, `72` unique message IDs), `5` volume envelopes, `12` chromatic note periods, `132` audio descriptors (`64` SFX / `68` BGM), and `dmc[0]` (`$FC80`) strictly into gitignored `Corpus/work/decoded_tables/` while validating `4/4` specification spokes in [spec_coverage.json](../schemas/spec_coverage.json).
- **Non-Blocking Upstream `reCartOne` Schema Alignment Finding (`ValidateD5ByteMatchFile`):**
  - **Observation:** Read-only `reCart.Decomp.D4BuildReportValidator.ValidateD4BuildReportFile`, `ValidateResearchManifestFile`, `reCart.Decomp.SixTellDetector.ScanDirectory` (`34` `Corpus/readable` + `34` `D4_CleanSource` files, `Findings=0`), and `reEngine.Core.Decomp.DecompD4StrictnessValidator` (`ValidateWorkspace` & `ValidateDecompArchiveCleanRoom`) all pass (`IsValid=True`), whereas `reCart.Decomp.D4BuildReportValidator.ValidateD5ByteMatchFile` reports `IsValid=False` (`9` schema-key violations: expecting legacy `'matchedBinaries'` and `'relpath'` on entries `#1..#8`).
  - **Root Cause:** `reCartOne` (`D4ReportSchemaHelpers.ValidateD5Core`) still looks only for deprecated Standard 18 v1 field names (`matchedBinaries`, `relpath`/`name`/`path`, `bytes`, `sha256`), whereas `ValidateD4BuildReportFile` and `ValidateResearchManifestFile` in the same assembly already accept Standard 18 v2 aliases.
  - **Disposition:** **`Non-Blocking` for `v0.4.0`.** [d5_byte_match.json](../schemas/d5_byte_match.json) conforms to Standard 18 v2 (`matchedBinaryCount`, `relativePath`, `fileSizeBytes`, `sha256Hex`) and is independently verified across `build_and_verify_d5.py`, `verify_track_d5.py`, `decomp_cli.py`, and `unittest` (`8/8` banks, `mismatchedBytes: 0`, `CRC32=25ba3d04`); follow-up in `reCartOne` will add Standard 18 v2 aliases alongside legacy v1 fallbacks in `ValidateD5Core`.

---

## 7. Related Manuals & Evidence Anchors

- [ARCHITECTURE.md](ARCHITECTURE.md) — UNROM bank topology, `$C6B7` dispatcher, `26` cohesive `D4_CleanSource` modules (`36` files in `Corpus/readable/`), `NesBus` C11 lockstep runtime, and bank decoders.
- [SPECIFICATIONS.md](SPECIFICATIONS.md) — `22` structs, `22` enums, `2,324` globals (`2,344` externs), all `4` [Dev/docs/specifications/](specifications/) format spokes, and Standard 18 v2 verification JSON contracts (`d4b_lockstep_report.json`, `spec_coverage.json`).
- [OPERATIONS.md](OPERATIONS.md) — Clean-room BYO-ROM layout, CLI overrides, tier materialization (`D1_Raw`–`D4_CleanSource`), `D4b` lockstep & bank decoder commands, `.decomp` packaging, and snapshot hygiene.
