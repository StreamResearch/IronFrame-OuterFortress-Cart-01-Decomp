#ifndef MG_SCHEMAS_MG_PLAYER_H
#define MG_SCHEMAS_MG_PLAYER_H

#include <stdbool.h>
#include <stdint.h>

/*
 * NES-ME-USA (UNROM Mapper 2) -- Main Loop, Player State, Rank, Weapons & Inventory
 *
 * Target ABI: MOS 6502 (pointer_bytes = 2, 16-bit little-endian addresses).
 * Grounded in PRG_FIXED_07.s ($C104 mode dispatch, $D758 init, $D7ED gameplay).
 */

/* Top-level engine mode in ZP $10 (dispatched by sub_c104 jump table) */
typedef enum MgGameMode {
    MG_MODE_TITLE_OR_ATTRACT = 0x00,
    MG_MODE_ACTIVE_GAME      = 0x01,
    MG_MODE_PASSWORD_ENTRY   = 0x02,
    MG_MODE_GAME_OVER        = 0x03,
    MG_MODE_ENDING           = 0x04
} MgGameMode;

/* Gameplay sub-state in ZP $2C (dispatched by sub_d7ce jump table) */
typedef enum MgPlaySubState {
    MG_PLAY_NORMAL      = 0x00,
    MG_PLAY_TRANSITION  = 0x01,
    MG_PLAY_EQUIP_MENU  = 0x02, /* Weapon/equipment/transceiver menu (sub_d84e) */
    MG_PLAY_TRANSCEIVER = 0x03,
    MG_PLAY_ROOM_LOAD   = 0x04,
    MG_PLAY_ELEVATOR    = 0x05,
    MG_PLAY_CUTSCENE    = 0x06,
    MG_PLAY_PLAYER_DEAD = 0x07  /* Triggered when $6D health == 0 at $D862 */
} MgPlaySubState;

/* Player rank index in ZP $6E (maps via $D7C9 table {5, 8, 12, 15} to max HP) */
typedef enum MgRank {
    MG_RANK_1_STAR = 0x00, /* Max HP = 5 */
    MG_RANK_2_STAR = 0x01, /* Max HP = 8 */
    MG_RANK_3_STAR = 0x02, /* Max HP = 12 */
    MG_RANK_4_STAR = 0x03  /* Max HP = 15 */
} MgRank;

/* Cardinal facing directions */
typedef enum MgDirection {
    MG_DIR_UP    = 0x00,
    MG_DIR_DOWN  = 0x01,
    MG_DIR_LEFT  = 0x02,
    MG_DIR_RIGHT = 0x03
} MgDirection;

/* Weapon inventory IDs */
typedef enum MgWeaponId {
    MG_WEAPON_NONE             = 0x00,
    MG_WEAPON_HANDGUN          = 0x01,
    MG_WEAPON_SUBMACHINE_GUN   = 0x02,
    MG_WEAPON_GRENADE_LAUNCHER = 0x03,
    MG_WEAPON_ROCKET_LAUNCHER  = 0x04,
    MG_WEAPON_PLASTIC_BOMB     = 0x05,
    MG_WEAPON_LAND_MINE        = 0x06,
    MG_WEAPON_MISSILE          = 0x07
} MgWeaponId;

/* Keycard & key item bitflags (ZP $71 / equipment flags) */
typedef enum MgKeycardMask {
    MG_KEY_CARD_1       = 0x01,
    MG_KEY_CARD_2       = 0x02,
    MG_KEY_CARD_3       = 0x04,
    MG_KEY_CARD_4       = 0x08,
    MG_KEY_CARD_5       = 0x10,
    MG_KEY_CARD_6       = 0x20,
    MG_KEY_CARD_7       = 0x40,
    MG_KEY_CARD_8       = 0x80
} MgKeycardMask;

/* Support equipment bitflags */
typedef enum MgEquipFlag {
    MG_EQUIP_RATIONS      = 0x01,
    MG_EQUIP_GAS_MASK     = 0x02,
    MG_EQUIP_CIGARETTES   = 0x04,
    MG_EQUIP_MINE_DETECT  = 0x08,
    MG_EQUIP_ANTENNA      = 0x10,
    MG_EQUIP_BINOCULARS   = 0x20,
    MG_EQUIP_BODY_ARMOR   = 0x40,
    MG_EQUIP_CARDBOARD    = 0x80
} MgEquipFlag;

/* Core main-loop & NMI timing state (PRG_FIXED_07.s ZP $10-$2B & $07CE-$07CF) */
typedef struct MgMainLoopState {
    uint8_t game_mode;        /* +0x00: ZP $10 top-level MgGameMode */
    uint8_t sub_mode;         /* +0x01: ZP $11 per-mode phase index */
    uint8_t frame_counter;    /* +0x02: ZP $12 incremented each NMI post-hook */
    uint8_t nmi_in_progress;  /* +0x03: ZP $13 re-entrancy guard in sub_c06c */
    uint8_t demo_timer;       /* +0x04: ZP $17 attract/demo cycle counter */
    uint8_t game_active;      /* +0x05: ZP $18 nonzero while game loop running */
    uint8_t ppu_enable_delay; /* +0x06: ZP $1C frames before $FE PPUMASK applies */
    uint8_t title_cursor;     /* +0x07: ZP $1E title/continue menu cursor */
    uint8_t screen_state;     /* +0x08: ZP $1F fade/screen transition state */
    uint8_t wait_lo;          /* +0x09: ZP $2A 16-bit frame wait timer low */
    uint8_t wait_hi;          /* +0x0A: ZP $2B 16-bit frame wait timer high */
    uint8_t play_substate;    /* +0x0B: ZP $2C MgPlaySubState */
    uint8_t intro_step;       /* +0x0C: $07CE intro/transition step (sub_c460) */
    uint8_t bank_init_step;   /* +0x0D: $07CF screen setup phase (sub_c49b) */
} MgMainLoopState; /* 0x0E (14 bytes) */

/* Player vitals, movement & rank state (ZP $35-$3B, $6D-$6E) */
typedef struct MgPlayerState {
    uint8_t health;       /* +0x00: ZP $6D current HP (0 triggers game over) */
    uint8_t rank;         /* +0x01: ZP $6E MgRank (0..3 -> max HP 5/8/12/15) */
    uint8_t max_health;   /* +0x02: Derived from $D7C9[rank] */
    uint8_t spawn_x;      /* +0x03: ZP $35 Player X coordinate on entry */
    uint8_t spawn_y;      /* +0x04: ZP $36 Player Y coordinate on entry */
    uint8_t facing_state; /* +0x05: ZP $38 MgDirection / posture (0x0C init) */
    uint8_t pause_lock;   /* +0x06: ZP $49 blocks pause/equip when nonzero */
    uint8_t input_lock;         /* +0x07: ZP $2F bit 7 blocks Select menu */
    uint8_t player_status_mask; /* +0x08: ZP $78 player status flags (bit 5/6/7) */
    uint8_t hurt_timer;         /* +0x09: ZP $51 invulnerability / damage state */
    bool    is_dead;            /* +0x0A: True when health == 0 */
    uint8_t reserved;           /* +0x0B: Alignment / future flag slot */
} MgPlayerState; /* 0x0C (12 bytes) */

/* Player weapons, keycards & equipment inventory (ZP $70-$77, $07E0) */
typedef struct MgInventoryState {
    uint8_t equipped_weapon;   /* +0x00: ZP $6B active MgWeaponId */
    uint8_t equipped_item;     /* +0x01: ZP $4B active equipment item */
    uint8_t keycards;          /* +0x02: ZP $71 MgKeycardMask bitmask */
    uint8_t item_flags_zp72;   /* +0x03: ZP $72 item/progression bitfield */
    uint8_t item_flags_zp73;   /* +0x04: ZP $73 item/progression bitfield */
    uint8_t item_flags_zp74;   /* +0x05: ZP $74 rescued POW / rank progress */
    uint8_t gear_flags_zp75;   /* +0x06: ZP $75 MgEquipFlag / mission gear */
    uint8_t status_flags_zp76; /* +0x07: ZP $76 uniform/cardboard/status flags */
    uint8_t ammo_counts[8];  /* +0x08: Per-weapon ammo counts */
    uint8_t menu_state;      /* +0x10: $07E0 equipment/menu cursor & page */
    uint8_t rations_count;   /* +0x11: Carried ration count */
} MgInventoryState; /* 0x12 (18 bytes) */

/* Warm-boot / password signature tail preserved across reset ($07F0-$07FF) */
typedef struct MgResetSignature {
    uint8_t magic[16]; /* +0x00: $07F0-$07FF initialized to 0xF0..0xFF at $C031 */
} MgResetSignature; /* 0x10 (16 bytes) */

#endif /* MG_SCHEMAS_MG_PLAYER_H */
