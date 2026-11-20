#ifndef MG_SCHEMAS_MG_AUDIO_H
#define MG_SCHEMAS_MG_AUDIO_H

#include <stdbool.h>
#include <stdint.h>

/*
 * NES-ME-USA (UNROM Mapper 2) -- Commercial Sound Driver & Channel/SFX State
 *
 * Target ABI: MOS 6502 (pointer_bytes = 2, 16-bit little-endian addresses).
 * Verified against BANK_06.s ($91F8-$99A8 driver, $0384-$03FF RAM, ZP $EA-$ED).
 */

/* Logical 6-channel commercial sound driver indices (X = 0..5) */
typedef enum MgAudioChannelId {
    MG_AUD_CH_PULSE1   = 0x00, /* BGM Pulse 1 ($4000-$4003) */
    MG_AUD_CH_PULSE2   = 0x01, /* BGM Pulse 2 ($4004-$4007) */
    MG_AUD_CH_TRIANGLE = 0x02, /* BGM Triangle ($4008-$400B) */
    MG_AUD_CH_NOISE    = 0x03, /* BGM Noise ($400C-$400F) */
    MG_AUD_CH_SFX1     = 0x04, /* SFX Pulse 1 override ($4000-$4003) */
    MG_AUD_CH_SFX2     = 0x05  /* SFX Pulse 2 / Noise override */
} MgAudioChannelId;

/* Sound / music command codes passed in A to sub_99a8 (BANK_06) */
typedef enum MgSoundCommandId {
    MG_SND_NONE          = 0x00,
    MG_SND_PAUSE_CHIME   = 0x33, /* Called in sub_ff5d on Start pause */
    MG_SND_GAME_START    = 0x3D, /* Called in sub_c189 on mode 1 start */
    MG_SND_PLAYER_DEATH  = 0x61  /* Called in sub_d862 when $6D HP == 0 */
} MgSoundCommandId;

/* Channel status bitflags in $03AA,X (checked against #$41 in sub_9202) */
typedef enum MgAudioChannelFlag {
    MG_AUD_FLAG_MUTED   = 0x01, /* Channel silenced / overridden by SFX */
    MG_AUD_FLAG_SLUR    = 0x02,
    MG_AUD_FLAG_ENV_END = 0x40  /* Checked with 0x41 mask in sub_9202 */
} MgAudioChannelFlag;

/*
 * Commercial sound driver 6-channel SoA RAM ($0384-$03F7, 116 bytes).
 * Indexed by X = 0..5 (6 channels) in BANK_06.s:
 *   $0386/$0387: pulse 1/2 active mode (0x81 triggers sweep init)
 *   $0388:       triangle/DAC active flag (sub_9322)
 *   $038A:       active SFX override flag
 *   $038C,X:     APU timer low ($4002,Y)
 *   $0392,X:     APU timer high / length ($4003,Y)
 *   $03AA,X:     channel flags (AND #$41 in sub_9202)
 *   $03D4,X:     duty/control bits OR'd with $03E6,X
 *   $03E6,X:     envelope/volume register ($4000,Y)
 */
typedef struct MgAudioChannelSoa {
    uint8_t base_0384[2];      /* +0x00: $0384-$0385 BGM/driver header bytes */
    uint8_t pulse_mode[2];     /* +0x02: $0386-$0387 Pulse 1/2 init/mode (0x81) */
    uint8_t dmc_ramp_active;   /* +0x04: $0388 Triangle/DMC ramp flag */
    uint8_t driver_misc_0389;  /* +0x05: $0389 driver scratch */
    uint8_t sfx_active_flag;   /* +0x06: $038A active SFX flag (0x31 pause) */
    uint8_t driver_misc_038b;  /* +0x07: $038B driver scratch */
    uint8_t timer_lo[6];       /* +0x08: $038C-$0391 APU period low per ch */
    uint8_t timer_hi[6];       /* +0x0E: $0392-$0397 APU period high per ch */
    uint8_t track_ptrs_lo[6];  /* +0x14: $0398-$039D sequence pointer low */
    uint8_t track_ptrs_hi[6];  /* +0x1A: $039E-$03A3 sequence pointer high */
    uint8_t note_timers[6];    /* +0x20: $03A4-$03A9 note duration counters */
    uint8_t channel_flags[6];  /* +0x26: $03AA-$03AF MgAudioChannelFlag per ch */
    uint8_t env_state_block[36]; /* +0x2C: $03B0-$03D3 pitch/envelope/loop */
    uint8_t duty_bits[6];      /* +0x50: $03D4-$03D9 duty cycle bits ($4000,Y) */
    uint8_t env_vol_extra[12]; /* +0x56: $03DA-$03E5 extra env/volume */
    uint8_t volume_env[6];     /* +0x62: $03E6-$03EB volume/envelope ($4000,Y) */
    uint8_t tail_03ec[12];     /* +0x68: $03EC-$03F7 vibrato/tail work RAM */
} MgAudioChannelSoa; /* 0x74 (116 bytes) */

/* Pause state snapshot at $03F8-$03FF (saved/restored by sub_9295 / sub_92c5) */
typedef struct MgAudioPauseBackup {
    uint8_t saved_03d8;       /* +0x00: $03F8 backup of $03D8 */
    uint8_t saved_03cc;       /* +0x01: $03F9 backup of $03CC */
    uint8_t saved_0390;       /* +0x02: $03FA backup of $0390 */
    uint8_t saved_0396;       /* +0x03: $03FB backup of $0396 */
    uint8_t saved_0384;       /* +0x04: $03FC backup of $0384 */
    uint8_t saved_039c;       /* +0x05: $03FD backup of $039C */
    uint8_t saved_03a2;       /* +0x06: $03FE backup of $03A2 */
    uint8_t pause_magic_03ff; /* +0x07: $03FF 0x31 when paused */
} MgAudioPauseBackup; /* 0x08 (8 bytes) */

/* Zero-page audio state ($25, $EA-$ED) + driver work RAM ($0384-$03FF) */
typedef struct MgAudioDriverState {
    uint8_t            req_pause;    /* +0x00: ZP $25 requested pause/mute */
    uint8_t            cur_pause;    /* +0x01: ZP $EA active pause/mute shadow */
    uint8_t            dac_level;    /* +0x02: ZP $EB $4011 soft-ramp DAC level */
    uint8_t            sweep_shadow; /* +0x03: ZP $EC $4001 sweep register val */
    uint8_t            dmc_enabled;  /* +0x04: ZP $ED enables $4011 ramp in sub_9322 */
    uint8_t            reserved;     /* +0x05: Alignment padding */
    MgAudioChannelSoa  channels;     /* +0x06: $0384-$03F7 channel SoA RAM */
    MgAudioPauseBackup pause_backup; /* +0x7A: $03F8-$03FF pause snapshot */
} MgAudioDriverState; /* 0x82 (130 bytes) */

#endif /* MG_SCHEMAS_MG_AUDIO_H */
