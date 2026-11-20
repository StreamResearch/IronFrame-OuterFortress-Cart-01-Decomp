# Stage 1 — Call Graph, Waves & Domain Clusters: IronFrame OuterFortress (Cart) 01 (NES-ME-USA)

- **Indexed Functions:** `499` game functions across `8` UNROM banks (`0` SDK functions, `0` failed decompiles)
- **Global Symbols Indexed:** `2,324` (`schemas/globals_index.json`)
- **Topology:** `maxWave = 9` (bottom-up leaf-to-root ordering), `1` nontrivial strongly connected component (`nontrivialSccs = 1`)
- **Auto-`/swarm` Triggers Met:** `binariesCount = 8 (> 1)`

## 1. Domain Breakdown (`schemas/clusters.json`)

| Domain | Binary Scope | Function Count | Responsibilities |
|---|---|---:|---|
| `core` | `PRG_FIXED_07.prg` (`$C000-$FFFA`) | `246` | Reset, NMI, IRQ, PPU DMA/scroll, joypad, UNROM bankswitching, main state loop, entity & collision core |
| `bank_00` | `BANK_00.prg` (`$8000-$BFFF`) | `34` | Room/area handlers, armored mech/boss/hazard logic, area tables |
| `bank_01` | `BANK_01.prg` (`$8000-$BFFF`) | `2` | Escape / sequence handler & bank 1 object routines |
| `bank_02` | `BANK_02.prg` (`$8000-$BFFF`) | `87` | Guard AI, alerts, patrols, trap/trigger & room object handlers |
| `bank_03` | `BANK_03.prg` (`$8000-$BFFF`) | `41` | Transceiver/codec calls, weapon & item equipment sub-menus |
| `bank_04` | `BANK_04.prg` (`$8000-$BFFF`) | `32` | Title screen, password entry, briefing/ending transitions |
| `bank_05` | `BANK_05.prg` (`$8000-$BFFF`) | `24` | Building/elevator transitions, cutscene & boss state handlers |
| `bank_06` | `BANK_06.prg` (`$8000-$BFFF`) | `33` | 6-channel NES sound/BGM/SFX sequencer (`$933C`, `$99A8`) |

## 2. Bottom-Up Wave Distribution (`schemas/call_graph.json`)

| Wave | Functions | Notes |
|---:|---:|---|
| `0` | `212` | Leaf routines: MMIO writes, PRG helpers, math/lookup, sound leaf updates |
| `1` | `134` | Direct 1-hop callers of leaf utilities and bankswitch helpers |
| `2` | `76` | Mid-tier PPU transfer, sprite build, and enemy/item action helpers |
| `3` | `43` | Codec/menu controllers, projectile/collision updaters, audio tick |
| `4` | `19` | Mode sub-dispatchers and screen-transition coordinators |
| `5` | `7` | NMI/frame-level updaters and scene runners |
| `6` | `3` | High-level state orchestrators |
| `7` | `2` | Top-level screen/state dispatch |
| `8` | `1` | Master frame/game controller |
| `9` | `2` | Root entry points (`VEC_RESET`, `VEC_NMI`) |
