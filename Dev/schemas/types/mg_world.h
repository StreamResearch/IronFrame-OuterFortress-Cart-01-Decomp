#ifndef MG_SCHEMAS_MG_WORLD_H
#define MG_SCHEMAS_MG_WORLD_H

#include <stdbool.h>
#include <stdint.h>

/*
 * NES-ME-USA (UNROM Mapper 2) -- World/Room, Transceiver & 32-Slot Entity/Actor Pool
 *
 * Target ABI: MOS 6502 (pointer_bytes = 2, 16-bit little-endian addresses).
 * Grounded in PRG_FIXED_07.s ($D2E2 entity renderer, $0300-$037F SoA pool, $30 room).
 */

/* Building / zone identifiers */
typedef enum MgBuildingId {
    MG_BLDG_OUTER_HEAVEN_EXT = 0x00, /* Fortress Exterior */
    MG_BLDG_BUILDING_1       = 0x01,
    MG_BLDG_BUILDING_2       = 0x02,
    MG_BLDG_BUILDING_3       = 0x03,
    MG_BLDG_UNDERGROUND      = 0x04
} MgBuildingId;

/* Alert state */
typedef enum MgAlertState {
    MG_ALERT_NONE      = 0x00,
    MG_ALERT_SUSPICION = 0x01, /* Single exclamation / patrol check */
    MG_ALERT_COMBAT    = 0x02  /* Double exclamation / reinforcements */
} MgAlertState;

/* Transceiver / Codec contact frequencies */
typedef enum MgCodecContact {
    MG_CODEC_BIG_BOSS    = 0x00, /* Commander contact (120.85) */
    MG_CODEC_SCHNEIDER   = 0x01, /* Field contact A (120.79) */
    MG_CODEC_DIANE       = 0x02, /* Field contact B (120.91) */
    MG_CODEC_JENNIFER    = 0x03, /* Field contact C (120.48) */
    MG_CODEC_PETROVICH   = 0x04  /* Technical specialist contact */
} MgCodecContact;

/* Special room / encounter dispatch values in ZP $3A */
typedef enum MgSpecialRoomMode {
    MG_ROOM_STANDARD   = 0x00,
    MG_ROOM_BOSS_OR_TX = 0x0B /* Checked at $D801 -> BANK_03/04 dispatch */
} MgSpecialRoomMode;

/* Entity pool type-byte high bit ($0300,X) */
typedef enum MgEntityStateBit {
    MG_ENT_ACTIVE_BIT = 0x80 /* Bit 7 selects $CCBB vs $CBBB sprite table */
} MgEntityStateBit;

/*
 * Structure-of-Arrays (SoA) Entity/Actor Pool ($0300-$037F, 32 slots = 0x20).
 * Verified in sub_d2e2 (CPX #$20):
 *   - $0300,X: entity type/state (slots 0..7 reserved; 8..31 enemies/objects)
 *   - $0320,X: screen X coordinate
 *   - $0340,X: screen Y coordinate
 *   - $0360,X: sprite/attribute/facing flags
 */
typedef struct MgEntitySoaPool {
    uint8_t type_state[32]; /* +0x00: $0300-$031F entity kind + active bit 7 */
    uint8_t pos_x[32];      /* +0x20: $0320-$033F screen X positions */
    uint8_t pos_y[32];      /* +0x40: $0340-$035F screen Y positions */
    uint8_t flags_attr[32]; /* +0x60: $0360-$037F OAM attrs / sub-state */
} MgEntitySoaPool; /* 0x80 (128 bytes) */

/* Logical unpacked view of a single entity slot */
typedef struct MgEntitySlotView {
    uint8_t slot_index; /* +0x00: Index 0..31 into MgEntitySoaPool */
    uint8_t type_state; /* +0x01: $0300,X type ID and active flags */
    uint8_t pos_x;      /* +0x02: $0320,X screen X coordinate */
    uint8_t pos_y;      /* +0x03: $0340,X screen Y coordinate */
    uint8_t flags_attr; /* +0x04: $0360,X facing / OAM attributes */
    bool    active;     /* +0x05: True if slot is currently occupied */
} MgEntitySlotView; /* 0x06 (6 bytes) */

/* Active screen/room, building & transceiver state (ZP $30-$60 & $07D7-$07DF) */
typedef struct MgWorldState {
    uint8_t room_id;          /* +0x00: ZP $30 current room/screen index */
    uint8_t prev_room_id;     /* +0x01: Previous room before transition */
    uint8_t building_id;      /* +0x02: MgBuildingId current zone */
    uint8_t special_mode;     /* +0x03: ZP $3A MgSpecialRoomMode (0x0B = special) */
    uint8_t alert_state;      /* +0x04: MgAlertState current alarm level */
    uint8_t alert_timer;      /* +0x05: ZP $EF / alarm countdown */
    uint8_t spawn_table_idx;  /* +0x06: Room spawn configuration index */
    uint8_t scroll_dir;       /* +0x07: Screen transition scroll direction */
    uint8_t codec_freq_lo;    /* +0x08: $07D7 transceiver frequency/HUD byte */
    uint8_t codec_freq_hi;    /* +0x09: $07D8 transceiver frequency/HUD byte */
    uint8_t codec_call_state; /* +0x0A: $07D9 active incoming call state */
    uint8_t room_flags_7de;   /* +0x0B: $07DE room state / door lock flags */
    uint8_t room_flags_7df;   /* +0x0C: $07DF room clear / event flags */
    uint8_t boss_hp;          /* +0x0D: Active boss health when engaged */
    uint16_t room_ptr;        /* +0x0E: ZP $80/$81 16-bit room data pointer */
} MgWorldState; /* 0x10 (16 bytes) */

/* Cleared per-room zero-page scratch block ($3F-$6C cleared by sub_d7a5) */
typedef struct MgRoomScratchBlock {
    uint8_t bytes[46]; /* +0x00: ZP $3F-$6C (0x2E bytes cleared on room init) */
} MgRoomScratchBlock; /* 0x2E (46 bytes) */

#endif /* MG_SCHEMAS_MG_WORLD_H */
