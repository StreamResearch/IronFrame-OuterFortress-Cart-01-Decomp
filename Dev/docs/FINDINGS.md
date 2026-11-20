# Findings — IronFrame OuterFortress (Cart) 01 Decomp (`NES-ME-USA`)

> **Verification Ledger:** `0` Static Decompiler Failures (`499/499` indexed) · `26/26` Cohesive `D3_Mapped` Modules (`0` Raw Tokens) · `8/8` PRG Banks `1:1` 6502 Assembly Match (`131,088` B, `CRC32=25BA3D04`) · `10/10` Mapped Modular Host Parity Assertions

This document records empirical reverse-engineering discoveries, UNROM bus-conflict mechanics, `BANK_06` sound-sequencer recovery, `D3_Mapped` cohesive coalescing and symbol resolution, C11 compilation baseline notes, and `1:1` 6502 byte-matching verification.

---

## 1. UNROM Bus-Conflict LUT (`$C959` / `$FFD0`) & Trampolines

- **Hardware Constraint:** Discrete `iNES Mapper 2` (`UNROM`) cartridges lack bus-conflict suppression circuitry (`74HC161` latch + `74HC32` OR gate). Writing a bank index to `$8000-$FFFF` corrupts the latch unless the PRG ROM byte at that exact write address equals the written bank number.
- **NES-ME-USA Implementation:** Fixed bank `PRG_FIXED_07` places an `8`-byte identity lookup table `{0, 1, 2, 3, 4, 5, 6, 7}` at `$FFD0-$FFD7` (verified against `PRG_FIXED_07` at offset `0x7FD0 + i == i` by `test_01_vectors_and_unrom` in [parity_rom_and_mapper_tests.c](../scripts/d4_harness/parity_rom_and_mapper_tests.c)), paired with the `$C932..$C958` trampolines and `$C959` adjacent switch table/helper:
  - Fixed per-bank stubs at `$C932..$C94A` (`unrom_select_bank_0`..`6`, `4`-byte stride).
  - Indexed trampoline `$C94C` (`unrom_select_bank_y` / `unrom_select_bank_index`), emitting at `$C94F`: `85 27 B9 D0 FF 99 D0 FF 60` (`STA $27; LDA $FFD0,Y; STA $FFD0,Y; RTS`). Note: static analysis over `PRG_FIXED_07` with `BANK_00` mounted at `$8000` constant-folded `LDA $8000` (`$C94C`) to `0` in early generated C; `test_03_unrom_bank_switch` in [parity_rom_and_mapper_tests.c](../scripts/d4_harness/parity_rom_and_mapper_tests.c) checks exact `$C94C`/`$C958` opcode sequences and live `unrom_select_bank_0`/`6` transitions (`v0.2.0` synthesized `3` cross-bank trampolines + `5` signature adapters, while the full bus-aware model awaits `v0.3.0` `D4_CleanSource`).
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

## 3. Cohesive `D3_Mapped` Normalization (`Corpus/readable/`) & Modular Harness

Early `D2_Structured` normalization resolved initial syntax blockers across the `68` line-split `.c` fragments without modifying read-only `Corpus/standalone/` (synthesizing `44` missing forward declarations, fixing call-site arity in `core_15.c` and `bank_02_06.c`, normalizing indirect function-pointer casts across `11` `.c` files, label syntax in `bank_05_02.c`, and return emission in `core_32.c`).

In `v0.2.0` (`D3_Mapped`), [coalesce_d4_modules.py](../scripts/coalesce_d4_modules.py) and [materialize_decomp_tiers.py](../scripts/materialize_decomp_tiers.py) consolidated that intermediate baseline into **`26` cohesive domain C modules** (`0` `_01.._NN.c` fragments, `0` remaining raw tokens across `.c` and headers) while preserving `D1_Raw` and `D2_Structured` snapshots:

- **Full Raw Symbol & Call Resolution (`0` Remaining Raw Tokens):** Applied [d3_symbol_overrides.json](../schemas/d3_symbol_overrides.json) and [globals_map.json](../schemas/globals_map.json) to eliminate all `299` raw extern aliases and `44` raw `FUN_*`/`func_0x*` call references, including `1` local label rename (`BYTE_ARRAY_8000_6486_ -> lbl_demo_input_loop`) and `20` synthetic/bank-scoped overrides deduplicated into `18` `g_*` declarations (`2,342` total `extern`s in `metalgear_globals.h`).
- **Bank-Scoped Table & Bitwise `&` Precision:** Disambiguated address collisions by explicitly mapping `BYTE_ARRAY_bf00` to `BANK_03.prg` (`g_b03_rom_tbl_bf00`) and `FUN_b622` to `BANK_01.prg` (`g_b01_rom_tbl_b622`), separating indexed `(&DAT_0740)[i]` writes (`g_vram_transfer_queue[i]`) from scalar `DAT_0740` reads (`g_vram_transfer_queue[0]`), and gating address-of `&` stripping to assignment/argument/return boundaries so bitwise `&` expressions (`g_frame_counter & g_b00_rom_tbl_b995[0]`) remain intact.
- **Synthesized `8` Bank/Signature Adapters & `9` Sub-Entry Prototypes:** Emitted `3` cross-bank trampolines (`$F5AC`, `$FBF5`, `$EE2A`) and `5` signature-adapting wrappers (`$99A8`, `$A765`, `$BB28`, `$B83A`, `$BBE1`) declaratively into `src/core/core_unrom_and_math.c`, plus `9` `subEntryDeclarations` prototypes in `metalgear_functions.h`.
- **Mapped Modular Host Parity Suite (`10/10` Passing):** Updated the four `<= 200`-line files under `Dev/scripts/d4_harness/` — [parity_harness.h](../scripts/d4_harness/parity_harness.h), [parity_runner_main.c](../scripts/d4_harness/parity_runner_main.c), [parity_rom_and_mapper_tests.c](../scripts/d4_harness/parity_rom_and_mapper_tests.c), and [parity_gameplay_and_audio_tests.c](../scripts/d4_harness/parity_gameplay_and_audio_tests.c) — to bind directly against mapped `g_*` scalar and array globals (`g_fixed_tbl_ff99`, `g_vram_transfer_queue`, `g_wram_0741`, `g_snd_pause_backup`, `g_snd_ram_*`, `g_zp_var_*`).
- **Current Limitation & `v0.3.0` Refactoring:** All `26` cohesive `D3_Mapped` modules compile cleanly (`0` errors, `0` warnings under `zig cc` `gnu11` freestanding), and `0` `_01.._NN.c` fragments or raw Ghidra tokens remain. However, `Corpus/readable/` still contains `2,874` structural decompiler idioms (`craftsmanshipTellCount: 2874` in [d4_build_report.json](../schemas/d4_build_report.json), reflecting the `26` coalesced files + `8` adapter headers) awaiting full human-authored C11 rewriting under `-Wall -Wextra -Wno-unused-parameter` in `v0.3.0` (`D4_CleanSource`).

---

## 4. Clean-Room 6502 Byte-Exact Assembly ([asm6502_d5.py](../scripts/asm6502_d5.py))

[asm6502_d5.py](../scripts/asm6502_d5.py) implements a standalone, zero-external-ROM clean-room MOS 6502 two-pass assembler (`56 / 56` official mnemonics, `151 / 151` opcodes, `13` addressing modes, plus `a:` absolute-encoding override to prevent unwanted zero-page relaxation). Executed via [build_and_verify_d5.py](../scripts/build_and_verify_d5.py):

- **Bank Images:** `8 / 8` `32,768`-byte `.prg` images (`BANK_00`..`BANK_06`, `PRG_FIXED_07`) match standalone SHA-256 digests (`0` byte mismatches; note `PRG_FIXED_07.prg` and `BANK_00.prg` share SHA-256 `96d482df...` because both pair `BANK_00` with `PRG_FIXED_07`).
- **Full Cartridge Image:** Reassembled `131,088`-byte ROM (NES 2.0 header + `8 x 16 KiB` PRG banks) achieves a **`1:1` byte-exact retail match** (`CRC32=25ba3d04`, `MD5=0e514c68eb8d82342a71a74c6d52499b`, `SHA1=9f7448fddaedc1801e2970e50722ac3cfacd19b8`, `SHA256=79095355436222161cb3841ff9b5c7a572e77af11461935e433bd6e8dfd0f164`) recorded in [d5_byte_match.json](../schemas/d5_byte_match.json).

---

## 5. Related Manuals & Evidence Anchors

- [ARCHITECTURE.md](ARCHITECTURE.md) — UNROM bank topology, `$C6B7` dispatcher, `26` cohesive `D3_Mapped` modules, and `8` synthesized adapters.
- [SPECIFICATIONS.md](SPECIFICATIONS.md) — `22` structs, `22` enums, `2,324` globals (`2,342` externs), `D3` mapping schemas, and Standard 18 v2 verification JSON contracts.
- [OPERATIONS.md](OPERATIONS.md) — Clean-room BYO-ROM layout, CLI overrides, tier materialization, `.decomp` packaging, and local verification commands.
