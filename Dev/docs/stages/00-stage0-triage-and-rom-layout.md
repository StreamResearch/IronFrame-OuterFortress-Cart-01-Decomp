# Stage 0 — Triage & UNROM ROM Layout: IronFrame OuterFortress (Cart) 01 (`NES-ME-USA`)

- **Title ID:** `NES-ME-USA` (8-bit Cart, North America)
- **Media Policy:** User-supplied BYO-ROM image (`131,088` bytes = `16`-byte iNES header + `8 x 16 KiB` PRG-ROM) staged locally in gitignored `Corpus/standalone/`
- **Hashes:** CRC32 `25BA3D04` | MD5 `0E514C68EB8D82342A71A74C6D52499B` | SHA1 `9F7448FDDAEDC1801E2970E50722AC3CFACD19B8`
- **Architecture:** `RP2A03` / MOS `6502` (`6502:LE:16:default`, `2`-byte little-endian pointers)
- **Board / Mapper:** **iNES Mapper 2 (`UNROM`)**, `8 x 16 KiB` PRG banks (`128 KiB`), `CHR-RAM` (`0` CHR-ROM banks), vertical mirroring
- **Hardware Vectors (`PRG_FIXED_07`):** `VEC_NMI = $C06C`, `VEC_RESET = $C001`, `VEC_IRQ = $C0B7`
- **Baseline Seal:** Standard 18 v2 [standalone_integrity.json](../../schemas/standalone_integrity.json) pins `1` `requiredRomChecksums` BYO-ROM entry (`131,088` bytes) plus `17` deterministic `extracted/` files (`3,717,065` bytes: `8` `.prg` banks, `8` `.s` disassemblies, `nes_bank_layout.json`) sealed read-only under `Corpus/standalone/`

## 1. Linked UNROM Bank Images (`32 KiB` CPU Views)

Because standard `6502` disassemblers lack Mapper 2 UNROM overlay conventions compatible with flat `6502:LE:16:default` re-export, the UNROM unpacker pairs each switchable `16 KiB` bank (`$8000-$BFFF`) against fixed bank 7 (`$C000-$FFFF`) and exports disjoint address windows:

| Linked Image | Bank Index | Export Window | Verified Code | Seeded Entries | Primary Role |
| :--- | ---: | :--- | ---: | ---: | :--- |
| `PRG_FIXED_07.prg` | Bank 7 (fixed) | `0xc000-0x10000` | `12,832 B` | `246` | Kernel, NMI/PPU/Joypad, actor loop, bank dispatcher |
| `BANK_00.prg` | Bank 0 | `0x8000-0xc000` | `2,618 B` | `34` | Area/boss/room entity handlers & map tables |
| `BANK_01.prg` | Bank 1 | `0x8000-0xc000` | `715 B` | `2` | Escape / sequence & sprite/tile data tables |
| `BANK_02.prg` | Bank 2 | `0x8000-0xc000` | `4,100 B` | `87` | Enemy, guard, trap & room object logic |
| `BANK_03.prg` | Bank 3 | `0x8000-0xc000` | `2,471 B` | `41` | Transceiver/codec, equipment & inventory menus |
| `BANK_04.prg` | Bank 4 | `0x8000-0xc000` | `2,046 B` | `32` | Title, password, ending & screen routines |
| `BANK_05.prg` | Bank 5 | `0x8000-0xc000` | `2,252 B` | `24` | Boss AI, building transitions & cutscenes |
| `BANK_06.prg` | Bank 6 | `0x8000-0xc000` | `2,123 B` | `33` | Sound/music/SFX engine (`$933C`, `$99A8`) |

## 2. Mapper 2 UNROM Dispatch & Bankswitch ABI

- **Bus-Conflict Identity Table (`$FFD0`):** Bank 7 holds `{00, 01, 02, 03, 04, 05, 06, 07}` at `$FFD0-$FFD7`. Routines `$C932`..`$C94A` (`switch_bank_0`..`switch_bank_6`) and `$C94C` (`switch_bank_y`) save the current bank ID byte read from `$8000` into ZP `$27` before writing `$FFD0,Y`. `$C958` restores `$27`. Bank 6 stays active by default across gameplay so NMI audio (`$933C`) and SFX calls (`$99A8`) avoid extra bank switches.
- **Inline Word-Pointer Jump Trampoline (`JSR $C6B7`):** Callers place a `.word[]` jump table immediately after `JSR $C6B7` (`$C6B7` pops the return address from stack, indexes by `A * 2`, and executes `JMP ($0080)`). Marking `$C6B7` as `NoReturn` lets static analysis decompile all 16 inline dispatch callers cleanly without fallthrough bad-data traps (`499/499` functions indexed with `0` failures).
