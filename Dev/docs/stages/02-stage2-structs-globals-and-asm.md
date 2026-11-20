# Stage 2 — Structs, Globals & Annotated 6502 Assembly: IronFrame OuterFortress (Cart) 01

- **Target ABI:** `6502_2a03` (`pointer_bytes = 2`, little-endian)
- **Type Headers (`Dev/schemas/types/*.h`):** `22` structs, `22` enums, `1` typedef (`nes_addr_t`), parsed with `0` errors
- **Umbrella Header:** [metalgear_types.h](../../schemas/metalgear_types.h) (`14` lines)
- **Mapped Globals:** Initial `166` seed entries expanded to `2,324 / 2,324` mapped symbols in [globals_map.json](../../schemas/globals_map.json) (`0` size/overlap errors)
- **Seeded Anchor Functions:** `39` root/hardware/bankswitch/dispatcher/audio functions in [anchor_functions.json](../../schemas/anchor_functions.json)
- **Clean-Room Lifted Assembly:** `3` modules in local `Corpus/work/lifted_asm/*.s` (`551` total annotated lines)

## 1. Domain Type Architecture (`Dev/schemas/types/*.h`)

| Header | Lines | Core Types & Enums |
| :--- | ---: | :--- |
| [nes_hardware.h](../../schemas/types/nes_hardware.h) | `185` | `NesPpuMmio`, `NesApuMmio`, `NesJoypadState`, `NesOamEntry`, `NesVramXferCmd`, `UnromBankState` |
| [mg_player.h](../../schemas/types/mg_player.h) | `141` | `MgGameMode`, `MgPlaySubState`, `MgWeaponId`, `MgEquipId`, `MgPlayerState`, `MgInventoryState` |
| [mg_world.h](../../schemas/types/mg_world.h) | `99` | `MgEntityPool` (`$0300-$037F` 32-slot SoA), `MgRoomState`, `MgTransceiverState`, `MgRoomZpScratch` |
| [mg_audio.h](../../schemas/types/mg_audio.h) | `95` | `MgAudioChannelPool` (`$0384-$03F7` 6-channel sound driver SoA), `MgAudioPauseBackup`, `MgAudioZpState` |

## 2. Memory Map & Mapped Globals ([globals_map.json](../../schemas/globals_map.json))

- **Zero-Page (`$00-$FF`):** `184` mapped symbols (`78` initial seed entries) covering NMI reentry (`$13`), joypad hold/edge (`$15-$16`, `$F5-$F8`), game/room mode (`$30`, `$65-$66`), previous UNROM bank (`$27`), PPU shadow registers (`$FC-$FF`), indirect work pointer `$80-$81`, and audio driver ZP state.
- **OAM Shadow (`$0200-$02FF`):** `g_oam_dma_shadow` (`uint8_t[256]`) flushed via `PPU_OAM_DMA` (`$4014`) on every VBlank.
- **Actor & Audio SoA RAM (`$0300-$03FF`):** `71` total mapped symbols splitting `$0300-$037F` (`32`-slot object X/Y/type/state) from `$0380-$03FF` (`6`-channel sound driver state + pause backup).
- **WRAM & VRAM Buffers (`$0400-$07FF`):** `62` entries including `g_room_layout_buf` (`$0400`, `768 B`) and `g_vram_transfer_queue` (`$0740`, `64 B`).
- **MMIO & UNROM Fixed Tables:** `8` PPU (`$2000-$2007`), `23` APU/DMA/Joypad/IO (`$4000-$4025`), plus fixed lookup tables `$C8A6`, `$FD00`, `$FE00`, `$FFD0`.

## 3. Lifted 6502 Reference Modules (`Corpus/work/lifted_asm/*.s`)

- `vectors_and_nmi.s` (`184` lines): Cold boot reset (`$C001`), WRAM clear & warm-boot check (`$07F0-$07FF`), VBlank OAM/VRAM NMI handler (`$C06C`), and `RTI` IRQ stub (`$C0B7`).
- `unrom_trampoline.s` (`218` lines): Bus-conflict identity switchers (`$C932-$C960`), dynamic bank/pointer loaders (`$C983-$CA2B`), and the stack-popping inline word-table jump dispatcher (`$C6B7-$C6D4`).
- `ppu_joypad_io.s` (`149` lines): PPU/APU initialization (`$C0B8`), nametable/scroll sync (`$C0D7`), screen blanking (`$C0F7`), and dual-read strobe controller polling (`$FF00-$FF5C`).
