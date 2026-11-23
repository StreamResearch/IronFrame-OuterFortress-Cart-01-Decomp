# Codec Call Tables & `BANK_06` Audio Format

> **Spoke of [SPECIFICATIONS.md](../SPECIFICATIONS.md)** · Structural specification for `BANK_05` transceiver frequencies and room call tables, `BANK_06` volume envelopes, note periods, and `132` sound/BGM descriptors, plus `PRG_FIXED_07` `dmc[0]`. Verified by [decode_codec_and_audio.py](../../scripts/decode_codec_and_audio.py).

---

## 1. `BANK_05` Codec Frequencies & Room Call Tables (`$B97C`, `$BB65/$BC65`)

- **Codec Frequency LUT (`$B97C..$B982`, `7` bytes):** `7` BCD-packed frequency channel bytes `[0x0D, 0x10, 0x5B, 0x30, 0x4F, 0x55, 0x21]` matched against ZP `$46` in `BANK_05` (`$B6F4`, `$B876`), terminated by `$FF` at `$B98A`.
- **Room Call Pointer Tables (`$BB65..$BD62`, `255` pointers):** Split across `$BB65` (`128` entries for rooms `0x00..0x7F`) and `$BC65` (`127` entries for rooms `0x80..0xFE`), deduplicating to `75` unique call tables (`$BD63..$BE69`):
  - **Call Table Record:** `1`-byte `entryCount` (`0` = no incoming/outgoing call triggers), followed by `entryCount` `2`-byte `(headerByte, msgId)` pairs (`116` total entries across `255` rooms, referencing `72` unique `msgId`s in `0x02..0x9F`).
  - **Header Byte Bitfields:** Bits `0..2` (`& 0x07`) select the `1`-based contact slot (`1..7` -> `$B97C` index `slot - 1`), while bits `6..7` (`& 0xC0`) select trigger/auto-ring mode (`0x40` manual, `0x80` / `0xC0` event/auto call).
  - **Message Cross-Reference:** Every `msgId` resolves cleanly into `BANK_00` `$BDFA/$BEFA` (`< 160`) to an `$FF`-terminated byte span without extracting retail prose.

---

## 2. `BANK_06` Volume Envelopes (`$91EE`, `5` Envelopes)

`BANK_06` (`$93EF`) reads `5` little-endian `u16` pointers from `$91EE..$91F7`, masking each frame sample with `& 0x1F` until hitting loop/end marker `>= $FE` (`$FF` terminator across all `5` envelopes):

| Envelope ID | Pointer | Sample Bytes | Terminator |
| :---: | :--- | ---: | :--- |
| `0` | `$B09B` | `8` | `$FF` |
| `1` | `$B5D6` | `10` | `$FF` |
| `2` | `$B1EA` | `63` | `$FF` |
| `3` | `$AAC2` | `10` | `$FF` |
| `4` | `$BA78` | `17` | `$FF` |

---

## 3. `BANK_06` APU Note Period LUT (`$9923`, `12` Chromatic Semitones)

`BANK_06` (`$961D`) reads `12` little-endian `u16` RP2A03 timer periods at `$9923..$993A` (base octave divided by right-shifting in `$962D` by octave index `$03E0,X`):

| Note Index | `0` | `1` | `2` | `3` | `4` | `5` | `6` | `7` | `8` | `9` | `10` | `11` |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **Period (Hex)** | `$06AE` | `$064E` | `$05F4` | `$059E` | `$054E` | `$0501` | `$04B9` | `$0476` | `$0436` | `$03F9` | `$03C0` | `$038A` |
| **Period (Dec)** | `1710` | `1614` | `1524` | `1438` | `1358` | `1281` | `1209` | `1142` | `1078` | `1017` | `960` | `906` |

---

## 4. `BANK_06` Sound & BGM Descriptor Table (`$BC15`, `132` Active Slots)

`BANK_06` (`$99A8`) dispatches `8`-bit sound command IDs against the `3`-byte descriptor array at `$BC15` (`$9954`):

- **Boundary Commands:** ID `$00` and `$86` mute/stop playback (`$9956`); ID `$85` enables the `$ED = $40` soft DMC DAC ramp (`$99BB`); IDs `>= $87` return immediately.
- **Active Descriptors (`$01..$84`, `132` entries at `$BC15 + id * 3`):**
  - Byte `0` (`headerByte`): bits `0..2` select channel (`0..3` BGM Pulse1/Pulse2/Tri/Noise, `4..5` SFX overrides), bits `3..4` (`>> 3 & 3`) specify additional consecutive channel descriptors (`0..3`) loaded together.
  - Bytes `1..2` (`u16` pointer): sequence bytecode address inside `BANK_06` (`$9ABE..$BBF4`).
  - **Priority vs. Unconditional Threshold (`$9A04: CMP #$41`):** IDs `$01..$40` (`64` entries, including `$3D..$40` `4`-channel start jingle) check `$0386,X` channel priority; IDs `$41..$84` (`68` entries) clear `$0389` and start unconditionally.

---

## 5. `PRG_FIXED_07` DMC Sample Descriptor (`$FC80`, `dmc[0]`)

`BANK_06` (`$9A96`) programs the RP2A03 Delta Modulation Channel from the `4`-byte `dmc[0]` descriptor at `$FC80..$FC83`:

| Offset | Value | APU Register Mapping |
| :--- | :--- | :--- |
| `$FC80` | `$0E` | `$4010` (`DMC_FREQ`: IRQ off, loop off, rate index `14`) |
| `$FC81` | `$00` | Padding / unused byte |
| `$FC82` | `$F0` | `$4012` (`DMC_START`: `$C000 + ($F0 * 64) = $FC00`) |
| `$FC83` | `$08` | `$4013` (`DMC_LEN`: `($08 * 16) + 1 = 129` sample bytes across `$FC00..$FC80`) |
