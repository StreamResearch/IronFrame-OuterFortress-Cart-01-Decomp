# Symbol, Bank & Schema Reference — IronFrame OuterFortress (Cart) 01 Decomp

> **Spoke of [SPECIFICATIONS.md](../SPECIFICATIONS.md)** · Full inventory of `8` PRG domains, `2,324` globals, `499` functions, and `Dev/schemas/` contracts.

---

## 1. Per-Bank & Per-Domain Global / Function Matrix

The table below reconciles code layout (`nes_bank_layout.json`), functional decomposition ([functions_catalog.json](../../schemas/functions_catalog.json)), and symbol ownership ([globals_map.json](../../schemas/globals_map.json)):

| Bank (`32 KiB .prg`) | Domain | Code Bytes | Initial `.c` Slices | Named Funcs | Bank-Scoped Globals | Domain-Tagged Globals |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: |
| `PRG_FIXED_07` (`$C000-$FFFF`) | `core` | `12,832` | `33` | `246` | `1,246` *(resident)* | `1,113` |
| `BANK_00` (`$8000-$BFFF`) | `bank_00` | `2,618` | `5` | `34` | `310` | `310` |
| `BANK_01` (`$8000-$BFFF`) | `bank_01` | `715` | `1` | `2` | `25` | `30` |
| `BANK_02` (`$8000-$BFFF`) | `bank_02` | `4,100` | `12` | `87` | `259` | `274` |
| `BANK_03` (`$8000-$BFFF`) | `bank_03` | `2,471` | `5` | `41` | `100` | `134` |
| `BANK_04` (`$8000-$BFFF`) | `bank_04` | `2,046` | `4` | `32` | `148` | `160` |
| `BANK_05` (`$8000-$BFFF`) | `bank_05` | `2,252` | `4` | `24` | `79` | `82` |
| `BANK_06` (`$8000-$BFFF`) | `bank_06` | `2,123` | `4` | `33` | `157` | `221` |
| **Totals** | **`8` domains** | **`29,157`** | **`68`** | **`499`** | **`2,324`** | **`2,324`** |

- **`resident` vs. `core` Delta (`1,246` vs. `1,113`):** Resident hardware/ZP/WRAM/fixed-ROM symbols (`1,246`) include `133` variables whose logical usage is tagged directly to specific switchable bank domains (`bank_01`..`bank_06`), reconciling both totals cleanly to `2,324`.

---

## 2. Critical Fixed-Bank & Hardware Symbols

| Address | Symbol / Label | Role & Verification Notes |
| :--- | :--- | :--- |
| `$0027` | Active UNROM bank shadow | Preserved and restored across cross-bank trampolines (`$C94C`, `$C958`) |
| `$0080` | Indirect jump target vector | Target pointer for `jmp ($0080)` inside `inline_jump_table_dispatch` (`$C6D2`) |
| `$0200-$02FF` | OAM shadow page | Sprite attribute buffer transferred via `$4014` (`OAMDMA`) during NMI |
| `$0300-$037F` | Actor SoA block (`30` globals) | Entity state, coordinates, timers, and AI fields structured as SoA |
| `$0380-$03FF` | Audio SoA block (`41` globals) | Sound driver per-channel state and control fields |
| `$C001` | `VEC_RESET` | Hardware reset entry in `PRG_FIXED_07` |
| `$C06C` | `VEC_NMI` | VBlank NMI handler entry in `PRG_FIXED_07` |
| `$C0B7` | `VEC_IRQ` | IRQ handler vector in `PRG_FIXED_07` |
| `$C6B7` | `inline_jump_table_dispatch` | Stack-popping `NoReturn` inline `.word[]` dispatcher (`16+` call sites) |
| `$C932..$C94A` | `unrom_select_bank_0..6` | Fixed bank-switch entry points (`4`-byte stride) |
| `$C94C` | `unrom_select_bank_y` / `unrom_select_bank_index` | Variable bank-switch routine writing `$27` and `$FFD0,Y` (`$C94F`) |
| `$C958` | `unrom_restore_active_bank` | Restores bank indexed in `$27`; adjacent to `$C959` helper/LUT |
| `$FFD0-$FFD7` | Bus-conflict identity LUT | `8`-byte `{0, 1, 2, 3, 4, 5, 6, 7}` table (`prg7[0x7FD0+i] == i`) |

---

## 3. Lifted Modules, Anchors & Schema Index

- **Recovered `BANK_06` Audio Sequencer Functions (`4` functions):**
  - `BANK_06` `$9382` — `mg_b56_audio_update_channel`
  - `BANK_06` `$94EA` — `mg_b56_audio_dispatch_seq_mode`
  - `BANK_06` `$94ED` — `mg_b56_audio_parse_seq_event` *(SCC peer with `$96E4`)*
  - `BANK_06` `$96E4` — `mg_b56_audio_exec_control_opcode` *(SCC peer with `$94ED`)*
- **Lifted Assembly Glue (`Corpus/work/lifted_asm/`):**
  - `ppu_joypad_io.s` (`149` lines) — PPU registers, OAM DMA, and controller read routines.
  - `unrom_trampoline.s` (`218` lines) — `$C932..$C958` UNROM bank-select stubs and `$FFD0` LUT references.
  - `vectors_and_nmi.s` (`184` lines) — Hardware `VEC_RESET` / `VEC_NMI` / `VEC_IRQ` entry glue (`551` lines total).
- **Local Symbol Index & Report Schemas:**
  - Consult gitignored `Corpus/readable/SYMBOL_MAP.md` alongside [anchor_functions.json](../../schemas/anchor_functions.json) (`39` anchors across `5` export shards) and [spec_coverage.json](../../schemas/spec_coverage.json) (`22` structs, `22` enums, `0` unresolved fields).
  - Cross-check compilation, parity, and `1:1` ROM match reports in [d4_build_report.json](../../schemas/d4_build_report.json), [s4_verify_report.json](../../schemas/s4_verify_report.json), and [d5_byte_match.json](../../schemas/d5_byte_match.json).
