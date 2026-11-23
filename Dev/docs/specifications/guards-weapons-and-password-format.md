# Guards, Spawns, Weapons & Password Format

> **Spoke of [SPECIFICATIONS.md](../SPECIFICATIONS.md)** · Structural specification for `BANK_00` patrol scripts and dialog pointer offsets, `BANK_04` room actor spawns, `BANK_06` weapon/projectile/explosion tables, `BANK_03` password layout tables, and `PRG_FIXED_07` spawn/rank/weapon dispatch tables. Verified by [decode_guards_and_weapons.py](../../scripts/decode_guards_and_weapons.py).

---

## 1. `BANK_00` Patrol Scripts (`$8048..$83A5`)

`PRG_FIXED_07` (`$DCF1`) indexes `u16` patrol pointers from `BANK_00` `$8048`:

- **Pointer Table (`$8048..$813D`):** `123` little-endian `u16` pointers (`$8048 + id * 2`) terminating right before the first script body at `$813E`, indexing `96` unique patrol scripts.
- **Script Stream (`$813E..$83A5`):** Variable-length sequence of `2`-byte `(command, duration)` steps terminated by `$FF`. When `$FF` is read, the patrol cursor resets to offset `0` for continuous looping.

---

## 2. `BANK_00` Dialog Pointer Offsets (`$BDFA` / `$BEFA`, Clean-Room Layout Only)

`BANK_04` dialog initialization reads a `16`-bit pointer from `BANK_00` (`$BDFA` for IDs `0..127`, `$BEFA` for IDs `128+` via `(id << 1)`) before switching to `BANK_01` (when room mode is `5` or `12`) or `BANK_05` to stream bytes:

| Table Region | Slot Count | ID Range | Target Bank Resolution | Termination |
| :--- | ---: | :--- | :--- | :--- |
| `$BDFA..$BEF9` | `128` | `0..127` | `< $A000` -> `BANK_01`; `>= $A000` -> `BANK_05` | `$FF`-terminated (`$FE` = line break) |
| `$BEFA..$BF39` | `32` | `128..159` | `< $A000` -> `BANK_01`; `>= $A000` -> `BANK_05` | Stops cleanly before `sub_bf3a` at `$BF3A` |

*(Clean-room boundary: tooling extracts pointer addresses, target banks, line-break counts, and byte lengths only—never retail text strings.)*

---

## 3. `BANK_04` Room Actor Spawn Table (`$8592`, `217` Rooms)

`BANK_04` (`$801C`) clamps room IDs `< $D9` (`0..216`, `217` rooms) across split pointer tables `$8592` (`0..127`) and `$8692` (`128..216`), resolving `85` unique spawn scripts (`$8744..$8A37`):

- **Empty Room Sentinel:** Leading header byte with bit `7` set (`$FF`, `1` byte total) skips actor spawning.
- **Populated Room Script:** `1`-byte actor group header followed by `N` `3`-byte tuples `(patrolOrSlotId, posY, posX)` terminated by `$FF`.

---

## 4. `BANK_06` Weapon, Projectile & Explosion Tables (`$89F0..$8B67`)

When firing or stepping projectiles in `PRG_FIXED_07` (`$EF1F..$F326`), `7` numeric lookup tables live in `BANK_06`:

| Address | Size (B) | Shape | Purpose |
| :--- | ---: | :--- | :--- |
| `$89F0..$89F3` | `4` | `u8[4]` | Facing base angle index `{0, 8, 12, 4}` for Up/Down/Left/Right |
| `$89F4..$8A13` | `32` | `u8[4][8]` | `8`-step spread angle table indexed by `(facing * 8 + shotIndex)` |
| `$8A14..$8A1B` | `8` | `s8[4][2]` | Signed `(dy, dx)` projectile spawn offsets per facing |
| `$8A1C..$8B1B` | `256` | `s8[4][64]` | `4`-quadrant `64`-step fractional horizontal delta LUT |
| `$8B1C..$8B23` | `8` | `u8[8]` | Projectile entity type ID indexed by `MgWeaponId` (`0..7`) |
| `$8B24..$8B27` | `4` | `u8[4]` | Explosion stage entity IDs (`0x34, 0x35, 0x36, 0x00`) |
| `$8B28..$8B67` | `64` | `s8[56] + u8[8]` | Projectile/explosion bounding-box bounds (`$8B28..$8B5F`) + directional launcher entity IDs (`$8B60..$8B67`) |

---

## 5. `BANK_03` Password Screen Layout Tables (`$B9DF`, `$BAAD`, `$BBB3`, `$BDC0`)

| Table | Bytes | Structural Content (Numeric Layout Only) |
| :--- | ---: | :--- |
| `$B9DF..$B9E7` | `9` | `8` banner tile indices + `$FF` terminator written to PPU `$206C` |
| `$BAAD..$BAB7` | `11` | `2`-byte PPU target (`$216C`) + `8` error-banner tile indices + `$FF` terminator |
| `$BBB3..$BC24` | `114` | `57` little-endian `u16` PPU nametable addresses (`25` `5x5` slot cells + `32` selection cells) |
| `$BDC0..$BDF5` | `54` | `2`-byte layout header + `32` indexed glyph slots + `5` row offsets + `5` row PPU addresses |

---

## 6. `PRG_FIXED_07` Spawn, Rank HP & Weapon Dispatch (`$D7B8..$D7CD`, `$EE6A`)

- **`$D7B8..$D7C9` (`18` bytes):** Parallel `6`-entry arrays for start/continue spawn `roomId` (`$D7B8..$D7BD`), `posY` (`$D7BE..$D7C3`), and `posX` (`$D7C4..$D7C9`).
- **`$D7CA..$D7CD` (`4` bytes):** Maximum HP lookup `{5, 8, 12, 15}` indexed by player rank `1..4` (`$D76A`).
- **`$EE6A..$EE79` (`16` bytes):** `8`-entry inline `u16` jump table dispatched via `$C6B7` for `MgWeaponId` (`0..7`), targeting `$EE57..$EF1F`.
