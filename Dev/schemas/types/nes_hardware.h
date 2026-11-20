#ifndef MG_SCHEMAS_NES_HARDWARE_H
#define MG_SCHEMAS_NES_HARDWARE_H

#include <stdbool.h>
#include <stdint.h>

/*
 * NES-ME-USA (UNROM Mapper 2) -- Hardware MMIO, UNROM & OAM/VRAM Types
 *
 * Target ABI: MOS 6502 (pointer_bytes = 2, 16-bit little-endian addresses).
 * Verified against PRG_FIXED_07.s ($C000-$FFFA) and nes_bank_layout.json.
 */

/* PPUCTRL ($2000) bitflags (shadowed in ZP $FF) */
typedef enum NesPpuCtrlFlag {
    PPU_CTRL_NAMETABLE_X   = 0x01, /* Base nametable X bit (2000/2400) */
    PPU_CTRL_NAMETABLE_Y   = 0x02, /* Base nametable Y bit (2000/2800) */
    PPU_CTRL_VRAM_INC_32   = 0x04, /* 0: +1 across, 1: +32 down */
    PPU_CTRL_SPR_PATTERN   = 0x08, /* Sprite pattern table ($0000/$1000) */
    PPU_CTRL_BG_PATTERN    = 0x10, /* Background pattern table ($0000/$1000) */
    PPU_CTRL_SPR_SIZE_8X16 = 0x20, /* 0: 8x8 sprites, 1: 8x16 sprites */
    PPU_CTRL_EXT_SLAVE     = 0x40, /* PPU master/slave select */
    PPU_CTRL_NMI_ENABLE    = 0x80  /* Generate NMI on VBlank */
} NesPpuCtrlFlag;

/* PPUMASK ($2001) bitflags (shadowed in ZP $FE) */
typedef enum NesPpuMaskFlag {
    PPU_MASK_GREYSCALE     = 0x01,
    PPU_MASK_BG_LEFT_8PX   = 0x02,
    PPU_MASK_SPR_LEFT_8PX  = 0x04,
    PPU_MASK_SHOW_BG       = 0x08,
    PPU_MASK_SHOW_SPR      = 0x10,
    PPU_MASK_EMPH_RED      = 0x20,
    PPU_MASK_EMPH_GREEN    = 0x40,
    PPU_MASK_EMPH_BLUE     = 0x80
} NesPpuMaskFlag;

/* PPUSTATUS ($2002) bitflags */
typedef enum NesPpuStatusFlag {
    PPU_STATUS_SPR_OVERFLOW = 0x20,
    PPU_STATUS_SPR0_HIT     = 0x40,
    PPU_STATUS_VBLANK       = 0x80
} NesPpuStatusFlag;

/* Standard NES controller bitmasks (MSB-first shifted in sub_ff32 -> $84/$85) */
typedef enum NesJoypadButton {
    NES_BTN_RIGHT  = 0x01,
    NES_BTN_LEFT   = 0x02,
    NES_BTN_DOWN   = 0x04,
    NES_BTN_UP     = 0x08,
    NES_BTN_START  = 0x10,
    NES_BTN_SELECT = 0x20,
    NES_BTN_B      = 0x40,
    NES_BTN_A      = 0x80
} NesJoypadButton;

/* APU status ($4015) enable mask */
typedef enum NesApuChannelMask {
    APU_ENABLE_PULSE1   = 0x01,
    APU_ENABLE_PULSE2   = 0x02,
    APU_ENABLE_TRIANGLE = 0x04,
    APU_ENABLE_NOISE    = 0x08,
    APU_ENABLE_DMC      = 0x10
} NesApuChannelMask;

/* Mapper 2 (UNROM) 16 KiB PRG-ROM banks ($8000-$BFFF switchable, 07 fixed at $C000) */
typedef enum UnromPrgBank {
    UNROM_BANK_00       = 0x00,
    UNROM_BANK_01       = 0x01,
    UNROM_BANK_02       = 0x02,
    UNROM_BANK_03       = 0x03,
    UNROM_BANK_04       = 0x04,
    UNROM_BANK_05       = 0x05,
    UNROM_BANK_06       = 0x06, /* Audio engine & APU register driver */
    UNROM_BANK_FIXED_07 = 0x07  /* Fixed upper bank ($C000-$FFFF) */
} UnromPrgBank;

/* OAM attribute byte flags */
typedef enum NesOamAttrFlag {
    OAM_ATTR_PALETTE_MASK = 0x03,
    OAM_ATTR_BEHIND_BG    = 0x20,
    OAM_ATTR_FLIP_H       = 0x40,
    OAM_ATTR_FLIP_V       = 0x80
} NesOamAttrFlag;

/* 16-bit 6502 address handle */
typedef uint16_t nes_addr_t;

/* PPU hardware register block ($2000-$2007) */
typedef struct NesPpuRegs {
    uint8_t ppuctrl;   /* +0x00: $2000 PPU control */
    uint8_t ppumask;   /* +0x01: $2001 PPU mask */
    uint8_t ppustatus; /* +0x02: $2002 PPU status (read-only) */
    uint8_t oamaddr;   /* +0x03: $2003 OAM address */
    uint8_t oamdata;   /* +0x04: $2004 OAM data */
    uint8_t ppuscroll; /* +0x05: $2005 X/Y scroll latch */
    uint8_t ppuaddr;   /* +0x06: $2006 VRAM address latch */
    uint8_t ppudata;   /* +0x07: $2007 VRAM data R/W */
} NesPpuRegs; /* 0x08 (8 bytes) */

/* APU pulse channel MMIO registers ($4000-$4003 / $4004-$4007) */
typedef struct NesApuPulseRegs {
    uint8_t duty_env; /* +0x00: Duty, loop/halt, constant vol/envelope */
    uint8_t sweep;    /* +0x01: Sweep unit control */
    uint8_t timer_lo; /* +0x02: Period low 8 bits */
    uint8_t len_hi;   /* +0x03: Length counter load + period high 3 bits */
} NesApuPulseRegs; /* 0x04 (4 bytes) */

/* APU triangle channel MMIO registers ($4008-$400B) */
typedef struct NesApuTriangleRegs {
    uint8_t linear_ctrl; /* +0x00: Control flag + linear counter reload */
    uint8_t unused_4009; /* +0x01: Unused */
    uint8_t timer_lo;    /* +0x02: Period low 8 bits */
    uint8_t len_hi;      /* +0x03: Length counter load + period high 3 bits */
} NesApuTriangleRegs; /* 0x04 (4 bytes) */

/* APU noise channel MMIO registers ($400C-$400F) */
typedef struct NesApuNoiseRegs {
    uint8_t env;         /* +0x00: Loop + constant vol/envelope */
    uint8_t unused_400d; /* +0x01: Unused */
    uint8_t period_mode; /* +0x02: Mode flag + noise period index */
    uint8_t len_load;    /* +0x03: Length counter load */
} NesApuNoiseRegs; /* 0x04 (4 bytes) */

/* APU DMC channel MMIO registers ($4010-$4013) */
typedef struct NesApuDmcRegs {
    uint8_t flags_rate;  /* +0x00: IRQ enable, loop, frequency index */
    uint8_t direct_load; /* +0x01: 7-bit direct DAC load ($4011) */
    uint8_t sample_addr; /* +0x02: Sample address ($C000 + A*64) */
    uint8_t sample_len;  /* +0x03: Sample length (L*16 + 1) */
} NesApuDmcRegs; /* 0x04 (4 bytes) */

/* Full NES APU & I/O MMIO block ($4000-$4017) */
typedef struct NesApuIoRegs {
    NesApuPulseRegs    pulse1;   /* +0x00: $4000-$4003 */
    NesApuPulseRegs    pulse2;   /* +0x04: $4004-$4007 */
    NesApuTriangleRegs triangle; /* +0x08: $4008-$400B */
    NesApuNoiseRegs    noise;    /* +0x0C: $400C-$400F */
    NesApuDmcRegs      dmc;      /* +0x10: $4010-$4013 */
    uint8_t            oamdma;   /* +0x14: $4014 OAM DMA page trigger */
    uint8_t            snd_chn;  /* +0x15: $4015 APU status/channel enable */
    uint8_t            joy1;     /* +0x16: $4016 Controller 1 / strobe */
    uint8_t            joy2_fc;  /* +0x17: $4017 Controller 2 / frame counter */
} NesApuIoRegs; /* 0x18 (24 bytes) */

/* Hardware OAM sprite entry (page $0200-$02FF, 64 entries) */
typedef struct NesOamSprite {
    uint8_t y;    /* +0x00: Y position minus 1 */
    uint8_t tile; /* +0x01: CHR tile index */
    uint8_t attr; /* +0x02: NesOamAttrFlag palette/priority/flip */
    uint8_t x;    /* +0x03: X position */
} NesOamSprite; /* 0x04 (4 bytes) */

/* Full 256-byte OAM shadow page ($0200-$02FF) DMA'd in sub_c06c */
typedef struct NesOamPage {
    NesOamSprite sprites[64]; /* +0x00: 64 hardware sprites */
} NesOamPage; /* 0x100 (256 bytes) */

/* Zero-page hardware & UNROM mapper shadows (PRG_FIXED_07.s) */
typedef struct NesShadowRegs {
    uint8_t active_bank; /* +0x00: ZP $27 active UNROM PRG bank (0..6) */
    uint8_t fds_ctrl;    /* +0x01: ZP $FA leftover $4025 init shadow (0x47) */
    uint8_t scroll_y;    /* +0x02: ZP $FC PPU_SCROLL Y shadow */
    uint8_t scroll_x;    /* +0x03: ZP $FD PPU_SCROLL X shadow */
    uint8_t ppumask;     /* +0x04: ZP $FE PPUMASK shadow */
    uint8_t ppuctrl;     /* +0x05: ZP $FF PPUCTRL shadow */
} NesShadowRegs; /* 0x06 (6 bytes) */

/* Controller polling state updated by sub_ff00 / sub_ff26 / sub_ff32 */
typedef struct NesJoypadState {
    uint8_t p1_held;    /* +0x00: ZP $15 filtered Player 1 held mask */
    uint8_t p2_held;    /* +0x01: ZP $16 filtered Player 2 held mask */
    uint8_t p1_pressed; /* +0x02: ZP $F5 newly pressed Player 1 buttons */
    uint8_t p2_pressed; /* +0x03: ZP $F6 newly pressed Player 2 buttons */
    uint8_t p1_prev;    /* +0x04: ZP $F7 previous frame Player 1 mask */
    uint8_t p2_prev;    /* +0x05: ZP $F8 previous frame Player 2 mask */
} NesJoypadState; /* 0x06 (6 bytes) */

/* NMI VRAM transfer command buffer ($0740-$07BF, written via $1D cursor in sub_d4a4) */
typedef struct NesVramCmdQueue {
    uint8_t write_cursor; /* +0x00: ZP $1D current write index into buffer */
    uint8_t buffer[128];  /* +0x01: $0740-$07BF command/tile stream ($FF/$FE/$FD ops) */
} NesVramCmdQueue; /* 0x81 (129 bytes) */

#endif /* MG_SCHEMAS_NES_HARDWARE_H */
