# Rooms, Metatiles, Adjacency & CHR Upload Format

> **Spoke of [SPECIFICATIONS.md](../SPECIFICATIONS.md)** · Structural specification for `BANK_05` room layouts, `BANK_04` metatiles/attributes/adjacency, `BANK_00..03` CHR-RAM stream headers, and `PRG_FIXED_07` `$FD00/$FE00` room metadata. Verified by [decode_rooms_and_metatiles.py](../../scripts/decode_rooms_and_metatiles.py).

---

## 1. PRG Window Slicing Convention (`32 KiB .prg`)

Each extracted bank image under `Corpus/standalone/extracted/*.prg` is `32,768` bytes (`0x8000`) pairing a switchable bank with `PRG_FIXED_07`:

| Image | Active Window (`16 KiB`) | File Byte Offset | Role |
| :--- | :--- | :--- | :--- |
| `BANK_00.prg`..`BANK_06.prg` | `$8000-$BFFF` | `0x0000..0x3FFF` | Switchable UNROM bank data and routines |
| `PRG_FIXED_07.prg` | `$C000-$FFFF` | `0x4000..0x7FFF` | Permanently resident vectors, drivers, `$FD00/$FE00` tables |

---

## 2. `BANK_05` Room Layout Table (`$8001`, `256` Rooms / `165` Unique)

- **Pointer Table (`$8001..$8200`):** `256` little-endian `u16` pointers (`$8201..$A0C1`) indexed by room ID (`0x00..0xFF`), deduplicating to `165` distinct grids.
- **Room Grid Record (`48` bytes):** Fixed `8 x 6` grid of `32 x 32`-pixel metatile indices (`6` rows x `8` columns = `48` bytes per room) unpacked into `$0700` work buffers before rendering.

---

## 3. `BANK_04` Metatile & Attribute Tilesets (`$8003`, `$800F`)

`PRG_FIXED_07` (`$D98C`, `$D9E5`) shifts `(tilesetIndex << 1)` to index two `6`-entry `u16` tables (`tileset 0..5`):

| Tileset ID | Metatile Ptr (`$8003`) | Attr Ptr (`$800F`) | Metatile Count | Metatile Bytes (`16 B/entry`) | Attr Bytes (`1 B/entry`) |
| :---: | :--- | :--- | ---: | ---: | ---: |
| `0` | `$90AC` | `$9BCC` | `178` | `2,848` | `178` |
| `1` | `$9C7E` | `$A36E` | `111` | `1,776` | `111` |
| `2` | `$A3DD` | `$AB2D` | `117` | `1,872` | `117` |
| `3` | `$ABA2` | `$B192` | `95` | `1,520` | `95` |
| `4` | `$B1F1` | `$B321` | `19` | `304` | `256` *(padded span)* |
| `5` | `$B421` | `$BB21` | `112` | `1,792` | `112` |

- Each metatile occupies `16` consecutive `8 x 8` CHR tile indices arranged as `4 x 4` tiles (`32 x 32` pixels), paired with `1` nametable attribute byte (`2`-bit palette selector per `16 x 16` quadrant).

---

## 4. `BANK_04` Room Adjacency & Transitions (`$8A8E..$90A8`)

Screen-edge, door, stair, and elevator transitions execute inside `BANK_04` (`$8153..$8224`):

| Table Address | Entry Count | Structure & Purpose |
| :--- | ---: | :--- |
| `$8A8E` / `$8AA0` | `18` | `u8` source room ID list (`$8A8E`) matched to `u8` destination room ID (`$8AA0`) for direct door/stair returns |
| `$8AB2` / `$8ABA` | `8` | Elevator room IDs (`$8AB2`) + `u16` floor-list pointers (`$8ABA`) indexed by `(floor_state & 0x07)` |
| `$8ADC` / `$8AED` | `17` | Special warp room IDs (`$8ADC`, `$EE..$FE`) + `u16` pointers (`$8AED`) to `3`-byte destination tuples (`$8B0F..$8B2F`) |
| `$8B30` / `$8C30` | `256` | Split `u16` pointer tables (`0..127` at `$8B30`, `128..255` at `$8C30`) targeting `235` unique `8`-byte neighbor vectors (`$8D30..$90A8`; `$FF` = blocked) |

---

## 5. `BANK_00..03` CHR-RAM Upload Headers (`$8001`, `51` Streams)

Because the cartridge uses `8 KiB` `CHR-RAM` with `0` CHR-ROM banks, `PRG_FIXED_07` (`$D4A4`, `$D513`) reads `u16` pointer tables starting at `$8001` in `BANK_00..03`:

| Bank | Stream Count | Terminator | Header / Payload Format |
| :--- | ---: | :--- | :--- |
| `BANK_00` | `18` | `$FFFF` at `$8025` | `4`-byte big-endian header `[ppuHi, ppuLo, lenHi, lenLo]` + raw `len` tile bytes |
| `BANK_01` | `27` | `$FFFF` at `$8037` | Contiguous `4 + len` records (`$8056..$9371`) |
| `BANK_02` | `3` | *(3-slot fixed)* | `3 x 4,096`-byte pattern banks (`$8007`, `$900B`, `$A00F`) targeting PPU `$0000` |
| `BANK_03` | `3` | *(3-slot fixed)* | `3 x 4,096`-byte pattern banks (`$8106`, `$910A`, `$A10E`) targeting PPU `$0000` |

---

## 6. `PRG_FIXED_07` Room Metadata Arrays (`$FD00` / `$FE00`, `256` Entries)

| Table | Indexing | Bitfield Breakdown (`8` bits per room `0x00..0xFF`) |
| :--- | :--- | :--- |
| `$FD00,Y` | `roomId` (`0..255`) | Bits `0..4` (`& 0x1F`): palette index (`0..26`); Bits `6..7` (`>> 6 & 3`): CHR variant (`0..3`) |
| `$FE00,Y` | `roomId` (`0..255`) | Bits `0..1` (`& 3`): pattern bank select (`0..1`); Bits `2..3` (`>> 2 & 3`): CHR slot (`0..1`); Bits `4..6` (`>> 4 & 7`): `BANK_04` tileset (`0..5`) |
