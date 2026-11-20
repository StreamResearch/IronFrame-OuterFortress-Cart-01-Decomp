# Architecture — IronFrame OuterFortress (Cart) 01 Decomp (`NES-ME-USA`)

> **Platform:** 8-bit Cart (`NES / RP2A03`, MOS `6502`) · **Mapper:** `iNES Mapper 2` (`UNROM`) · **Title ID:** `NES-ME-USA`

`IronFrame-OuterFortress-Cart-01-Decomp` houses the clean-room decompilation schemas, hardware-level system specification, self-contained BYO-ROM tooling, `.decomp` package exporter, cohesive `D3_Mapped` C coalescer, multi-tier snapshot builder, and `1:1` byte-exact 6502 reassembly scripts for `NES-ME-USA` (`131,088` bytes, NES 2.0). Source media remains clean-room separated inside the gitignored `Corpus/standalone/` directory (pinned in Standard 18 v2 `standalone_integrity.json` as `1` `requiredRomChecksums` BYO-ROM entry plus `17` deterministic `extracted/` entries), while tracked schemas, verification scripts, modular C parity harness (`d4_harness/`), offline tests (`tests/`), and manuals live under `Dev/`.

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

## 3. Domain & Translation-Unit Topology (`499 / 499` Functions, `26` Cohesive Modules)

In `v0.2.0` (`D3_Mapped`), [coalesce_d4_modules.py](../scripts/coalesce_d4_modules.py) merges all `499` recovered functions out of the `68` historical `D2_Structured` line-split fragments into **`26` cohesive domain C modules** (`10` `src/core/` + `16` `overlays/BANK_00..06.prg/`) governed by [d3_module_map.json](../schemas/d3_module_map.json), resolves all `299` raw global aliases and `44` raw cross-bank calls via [d3_symbol_overrides.json](../schemas/d3_symbol_overrides.json) (`0` remaining raw tokens across `.c` and headers), emits `2,342` resolved `extern` declarations into `include/metalgear_globals.h`, and pairs with `3` lifted hardware assembly modules (`551` lines) under `Corpus/work/lifted_asm/`. Full function-by-function idiomatic C11 rewriting under `-Wall -Wextra -Wno-unused-parameter` (`D4_CleanSource`) is scheduled for `v0.3.0`:

| Domain | Bank Image | Code Bytes | Cohesive `D3` Modules | `D2` Slices | Functions | Bank Globals | Domain Globals |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| **`core`** | `PRG_FIXED_07` (`$C000-$FFFF`) | `12,832` | `10` | `33` | `246` | `1,246` *(resident)* | `1,113` |
| **`bank_00`** | `BANK_00` (`$8000-$BFFF`) | `2,618` | `2` | `5` | `34` | `310` | `310` |
| **`bank_01`** | `BANK_01` (`$8000-$BFFF`) | `715` | `1` | `1` | `2` | `25` | `30` |
| **`bank_02`** | `BANK_02` (`$8000-$BFFF`) | `4,100` | `3` | `12` | `87` | `259` | `274` |
| **`bank_03`** | `BANK_03` (`$8000-$BFFF`) | `2,471` | `3` | `5` | `41` | `100` | `134` |
| **`bank_04`** | `BANK_04` (`$8000-$BFFF`) | `2,046` | `3` | `4` | `32` | `148` | `160` |
| **`bank_05`** | `BANK_05` (`$8000-$BFFF`) | `2,252` | `2` | `4` | `24` | `79` | `82` |
| **`bank_06`** | `BANK_06` (`$8000-$BFFF`) | `2,123` | `2` | `4` | `33` | `157` | `221` |
| **Total** | **`8` PRG Banks (`131,072` B)** | **`29,157`** | **`26`** | **`68`** | **`499`** | **`2,324`** | **`2,324`** |

### 3.1 Cohesive `D3_Mapped` Module Partition (`26` Modules) & `8` Synthesized Adapters

| Module (`Corpus/readable/` & `Corpus/tiers/D3_Mapped/`) | Domain | Funcs | Primary Scope |
| :--- | :--- | ---: | :--- |
| `src/core/core_vectors_boot_and_input.c` | `core` | `15` | Hardware reset/NMI/IRQ vectors, RAM init, joypad polling, pause/timer helpers |
| `src/core/core_game_state_and_cutscenes.c` | `core` | `48` | Top-level game mode state machine, submodes, cutscene stepping, BGM selection |
| `src/core/core_unrom_and_math.c` | `core` | `19` (+`8`) | UNROM bank trampolines, inline jump dispatch, math/PPU text helpers, `8` synthesized `D3` adapters |
| `src/core/core_ppu_and_vram.c` | `core` | `21` | PPU nametable streaming, room/tileset CHR loading, VRAM queue writers |
| `src/core/core_oam_and_metasprites.c` | `core` | `7` | OAM shadow sprite builder, grid/column metasprite emitters, attribute helpers |
| `src/core/core_gameplay_loop_and_rooms.c` | `core` | `28` | Gameplay frame tick, attract-mode demo loop, room decompression, bank-call wrappers |
| `src/core/core_actor_ai.c` | `core` | `34` | Enemy patrol scripts, line-of-sight/chase pathfinding, alert states, actor projectiles |
| `src/core/core_player_and_doors.c` | `core` | `40` | Player movement, collision probes, guard vision/alert, damage handling, door/elevator triggers |
| `src/core/core_weapons_and_bosses.c` | `core` | `26` | Player weapons, mines, projectile collisions, boss damage/spawning, room gimmick dispatch |
| `src/core/core_objectives_and_items.c` | `core` | `8` | Hostage rescue tracking, item pickups, supply refills, pause/ending bank dispatchers |
| `overlays/BANK_00.prg/bank00_hud_and_guards.c` | `bank_00` | `8` | Alert reinforcement guard spawning and HUD status-bar equipment/ammo queue updates |
| `overlays/BANK_00.prg/bank00_hazards_and_countdown.c` | `bank_00` | `26` | Screen shake, laser/pit/bridge/explosion hazards, hazard zones, self-destruct countdown |
| `overlays/BANK_01.prg/bank01_ppu_streams.c` | `bank_01` | `2` | Bank-1 PPU nametable stream batch uploader and zero-page scratch helper |
| `overlays/BANK_02.prg/bank02_intro_menus_and_cutscenes.c` | `bank_02` | `17` | Intro/title sequence packets, VRAM menu rows, cursor input handling, cutscene scroll |
| `overlays/BANK_02.prg/bank02_boss_movement_and_minions.c` | `bank_02` | `33` | Boss state dispatchers, alignment checks, bounded movement, minion/twin-actor updates |
| `overlays/BANK_02.prg/bank02_boss_patterns_and_turrets.c` | `bank_02` | `37` | Polar-orbit boss mechanics, bomb/barrage/quad-shot patterns, twin-turret tracking |
| `overlays/BANK_03.prg/bank03_actors_and_fade.c` | `bank_03` | `6` | Bank-3 palette fades, actor behavior state machine, proximity hits, animation timers |
| `overlays/BANK_03.prg/bank03_password_system.c` | `bank_03` | `25` | Password grid UI, cursor input, 24-character encode/decode, 5-bit checksum validation |
| `overlays/BANK_03.prg/bank03_ppu_boxes_and_vram.c` | `bank_03` | `10` | Direct PPU bordered dialog/menu box drawing, room radio triggers, VRAM queue flusher |
| `overlays/BANK_04.prg/bank04_room_spawns_and_warps.c` | `bank_04` | `10` | Room actor spawning, directional warps, special transitions, ending ascent cutscene |
| `overlays/BANK_04.prg/bank04_homing_actors.c` | `bank_04` | `8` | Binoculars room peek, homing patrol projectiles, bank-4 actor proximity triggers |
| `overlays/BANK_04.prg/bank04_dialog_system.c` | `bank_04` | `14` | Codec/dialog window framing, typewriter text streaming, row clearing, close restoration |
| `overlays/BANK_05.prg/bank05_transceiver_ui.c` | `bank_05` | `11` | Transceiver frequency HUD, incoming call matching, dialog streaming, frame rendering |
| `overlays/BANK_05.prg/bank05_ending_sequence.c` | `bank_05` | `13` | Ending explosion animation, transceiver epilogue calls, frequency sweep, palette fadeout |
| `overlays/BANK_06.prg/bank06_audio_engine.c` | `bank_06` | `14` | APU register writers, pause-mute synchronization, DMC DAC ramp, envelopes, vibrato |
| `overlays/BANK_06.prg/bank06_audio_sequencer.c` | `bank_06` | `19` | BGM/SFX sequence bytecode parser, pitch decoding, control opcodes, track triggers |

- **Synthesized `D3` Adapters (`8` in `src/core/core_unrom_and_math.c`) & `9` Sub-Entry Prototypes:** [d3_symbol_overrides.json](../schemas/d3_symbol_overrides.json) declaratively specifies `3` cross-bank trampolines (`switch_bank6_play_sound_and_restore_bank2` at `$F5AC`, `switch_bank6_and_queue_ppu_stream` at `$FBF5`, `trampoline_bank4_resolve_room_transition` at `$EE2A`) and `5` signature-adapting wrappers (`audio_play_sound_or_bgm` at `$99A8`, `mg_b034_try_spawn_alert_guard_default` at `$A765`, `mg_b034_upload_bank00_ppu_stream_bb3a_ret` at `$BB28`, `mg_b034_bank03_dispatch_actor_default` at `$B83A`, `mg_b034_bank04_dispatch_actor_default` at `$BBE1`), alongside `9` `subEntryDeclarations` prototypes (`$C68B`, `$C7F9`, `$C804`, `$C885`, `$CA2C`, `$D59C`, `$2020`, `$4420`, `$8043`) emitted in `include/metalgear_functions.h`.
- **Call Graph & Curated Anchors:** [call_graph.json](../schemas/call_graph.json) orders all `499` functions into bottom-up waves `0..9` (`max_wave=9`) with `1` nontrivial strongly connected component (`BANK_06.prg@000094ed <-> BANK_06.prg@000096e4`, audio sequencer recursion) and `0` failed functions (`4 -> 0` after `BANK_06` recovery). [anchor_functions.json](../schemas/anchor_functions.json) tracks `39` curated entry/system anchors across `5` export shards.
- **Lifted Hardware Assembly (`551` lines):** `Corpus/work/lifted_asm/` isolates low-level 6502 hardware glue across `ppu_joypad_io.s` (`149` lines), `unrom_trampoline.s` (`218` lines), and `vectors_and_nmi.s` (`184` lines).

---

## 4. Research Directory Contract & Related Documentation

- **Read-Only Media Isolation & Multi-Tier Snapshots:** Local `Corpus/` holds read-only `standalone/` (pinned in [standalone_integrity.json](../schemas/standalone_integrity.json) v2 as `1` BYO-ROM entry + `17` `extracted/` entries totaling `3,717,065` B), preserved `tiers/{D1_Raw, D2_Structured, D3_Mapped}` snapshots (`D1_Raw`: `8` bank trees / `555` files; `D2_Structured`: `68` line-split `.c` slices / `80` files; `D3_Mapped`: `26` cohesive `.c` modules / `38` files with `0` raw tokens), `readable/` (synced to `D3_Mapped`), and `work/`—strictly gitignored and excluded from source and `.decomp` archives.
- **Clean-Room Tooling (`Dev/scripts/` & `Dev/schemas/`):** Organized into shared path/hash helpers (`nes_cli_common.py`), 6502 CFG/UNROM unpacker (`nes_6502_cfg.py`, `nes_unrom_unpack.py`), `D3` schemas (`d3_module_map.json`, `d3_symbol_overrides.json`), cohesive coalescer and tier materializer (`coalesce_d4_modules.py`, `materialize_decomp_tiers.py`), 6502 assembler (`asm6502_d5.py`, `build_and_verify_d5.py`), D4/S4 parity driver (`build_and_verify_d4.py` + 4-file `d4_harness/`), schema/verifier CLIs (`gen_d4_globals_and_lifts.py`, `reexport_stage3.py`, `verify_track_d5.py`), `.decomp`/release packagers (`export_decomp_bundle.py`, `package_release.py`), and `4` offline `unittest` modules (`tests/`, `18` cases).
- **Next Manuals:** [SPECIFICATIONS.md](SPECIFICATIONS.md) | [Symbol & Bank Spoke](specifications/symbol-and-bank-reference.md) | [FINDINGS.md](FINDINGS.md) | [OPERATIONS.md](OPERATIONS.md)
- **Stage Notes:** [Stage 0](stages/00-stage0-triage-and-rom-layout.md) | [Stage 1](stages/01-stage1-call-graph-and-clusters.md) | [Stage 2](stages/02-stage2-structs-globals-and-asm.md) | [Stage 3](stages/03-stage3-function-naming.md) | [Stage 4](stages/04-stage4-readable-codebase-guide.md)
