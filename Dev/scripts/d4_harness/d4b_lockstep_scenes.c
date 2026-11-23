/* @module: IronFrame.D4Harness.D4bLockstepScenes */
/* @purpose: 650-frame 5-scene lockstep driver, subsystem CRC32 hashing, and clean-source checkpoints. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "metalgear_globals.h"
#include "metalgear_functions.h"
#include "parity_harness.h"
#include "nes_bus.h"

typedef struct {
    const char *name;
    uint32_t frame;
    int is_passed;
    char detail[128];
} D4bCheckpoint;

static NesBus s_lockstep_bus;

static uint8_t scene_input_mask(uint32_t f) {
    uint8_t m = 0u;
    if ((f >= 105u && f <= 109u) || (f >= 140u && f <= 144u)) {
        m |= (uint8_t)NES_BTN_START;
    }
    if (f >= 260u && f <= 320u) {
        m |= (uint8_t)NES_BTN_RIGHT;
    }
    if (f >= 325u && f <= 385u) {
        m |= (uint8_t)NES_BTN_UP;
    }
    if ((f >= 410u && f <= 414u) || (f >= 460u && f <= 464u)) {
        m |= (uint8_t)NES_BTN_SELECT;
    }
    if ((f >= 485u && f <= 489u) || (f >= 505u && f <= 509u)) {
        m |= (uint8_t)NES_BTN_START;
    }
    if (f >= 521u && f <= 650u && (f % 20u) < 4u) {
        m |= (uint8_t)(NES_BTN_UP | NES_BTN_B);
    }
    return m;
}

static void run_checkpoint(uint32_t f, const NesBus *bus, D4bCheckpoint *cps, size_t *cp_cnt) {
    D4bCheckpoint *cp = &cps[*cp_cnt];
    if (f == 1u) {
        unrom_select_bank_0();
        cp->name = "cp_1_boot_unrom_bank0";
        cp->frame = f;
        cp->is_passed = (bus->cpu.pc >= 0xC000u) ? 1 : 0;
        snprintf(cp->detail, sizeof(cp->detail), "pc=%04X bank=%u", bus->cpu.pc, bus->prg_bank);
        (*cp_cnt)++;
    } else if (f == 100u) {
        g_frame_counter = bus->wram[0x0012u];
        g_game_mode = bus->wram[0x0010u];
        g_state_timer_lo = 2u;
        g_state_timer_hi = 0u;
        uint8_t rem = mg_fxa_tick_state_timer();
        cp->name = "cp_2_title_state_timer";
        cp->frame = f;
        cp->is_passed = (g_state_timer_lo == 1u && rem != 0u) ? 1 : 0;
        snprintf(cp->detail, sizeof(cp->detail), "mode=%u fc=%u rem=%u", g_game_mode, g_frame_counter, rem);
        (*cp_cnt)++;
    } else if (f == 110u) {
        g_game_mode = bus->wram[0x0010u];
        g_game_submode = bus->wram[0x0011u];
        g_title_exit_flag = bus->wram[0x001Bu];
        uint8_t rc = mg_fxa_enter_game_mode(g_game_mode);
        cp->name = "cp_3_enter_game_mode";
        cp->frame = f;
        cp->is_passed = (rc == 0u && g_state_timer_lo == 0x50u &&
                         g_game_submode == 0u && g_title_exit_flag == 0u) ? 1 : 0;
        snprintf(cp->detail, sizeof(cp->detail), "mode=%u timer=%02X", g_game_mode, g_state_timer_lo);
        (*cp_cnt)++;
    } else if (f == 220u) {
        uint8_t prev = bus->wram[0x0010u];
        g_game_mode = prev;
        g_game_submode = bus->wram[0x0011u];
        mg_fxa_advance_game_mode();
        cp->name = "cp_4_advance_game_mode";
        cp->frame = f;
        cp->is_passed = (g_game_mode == (uint8_t)(prev + 1u) && g_game_submode == 0u) ? 1 : 0;
        snprintf(cp->detail, sizeof(cp->detail), "mode=%u->%u", prev, g_game_mode);
        (*cp_cnt)++;
    } else if (f == 320u) {
        g_wram_0741 = bus->wram[0x0741u];
        mg_b034_hud_init_vram_queue_header();
        cp->name = "cp_5_hud_vram_header";
        cp->frame = f;
        cp->is_passed = (g_wram_0741 == 0x23u) ? 1 : 0;
        snprintf(cp->detail, sizeof(cp->detail), "wram_0741=0x%02X", g_wram_0741);
        (*cp_cnt)++;
    } else if (f == 380u) {
        unrom_select_bank_6();
        cp->name = "cp_6_unrom_bank6_audio";
        cp->frame = f;
        cp->is_passed = (bus->wram[0x0012u] != 0u) ? 1 : 0;
        snprintf(cp->detail, sizeof(cp->detail), "fc=%u bank=%u", bus->wram[0x0012u], bus->prg_bank);
        (*cp_cnt)++;
    } else if (f == 490u) {
        g_zp_var_0067 = 0u;
        mg_b034_set_timer_state_67(7u);
        g_zp_var_0071 = 1u;
        g_frame_counter = 3u;
        mg_b034_tick_countdown_timer_and_hud();
        g_apu_pulse1_ctrl = bus->apu.regs[0];
        g_apu_pulse1_sweep = bus->apu.regs[1];
        g_apu_pulse2_ctrl = bus->apu.regs[4];
        g_apu_pulse2_sweep = bus->apu.regs[5];
        g_apu_noise_ctrl = bus->apu.regs[12];
        g_pause_flag = 1u;
        mg_b56_audio_sync_pause_mute();
        cp->name = "cp_7_pause_mute_countdown";
        cp->frame = f;
        cp->is_passed = (g_zp_var_0067 == 0u && g_apu_pulse1_ctrl == 0x30u &&
                         g_apu_pulse2_ctrl == 0x30u && g_apu_noise_ctrl == 0x30u &&
                         g_apu_pulse1_sweep == 0x7Fu && g_apu_pulse2_sweep == 0x7Fu) ? 1 : 0;
        snprintf(cp->detail, sizeof(cp->detail), "zp67=%u p1=%02X sw=%02X",
                 g_zp_var_0067, g_apu_pulse1_ctrl, g_apu_pulse1_sweep);
        (*cp_cnt)++;
    } else if (f == 650u) {
        uint8_t dac = bus->apu.regs[0x11u];
        g_apu_dmc_dac = dac;
        mg_b56_audio_ramp_dmc_dac();
        cp->name = "cp_8_combat_dmc_ramp";
        cp->frame = f;
        cp->is_passed = (g_apu_dmc_dac == dac) ? 1 : 0;
        snprintf(cp->detail, sizeof(cp->detail), "dmc_dac=%02X", g_apu_dmc_dac);
        (*cp_cnt)++;
    }
}

static void write_frame_json(FILE *fp, uint32_t f, const NesBus *bus) {
    uint8_t wram_masked[NES_WRAM_SIZE];
    memcpy(wram_masked, bus->wram, NES_WRAM_SIZE);
    memset(&wram_masked[0x0100u], 0, 0x0100u);
    uint32_t wram_crc = d4b_crc32(wram_masked, NES_WRAM_SIZE);
    uint32_t oam_crc = d4b_crc32(bus->oam, NES_OAM_SIZE);

    uint16_t t = bus->ppu.tmp_addr;
    uint8_t ppu_buf[4u + NES_PAL_SIZE];
    ppu_buf[0] = (uint8_t)((bus->ppu.ctrl & 0xFCu) | ((t >> 10) & 3u));
    ppu_buf[1] = bus->ppu.mask;
    ppu_buf[2] = (uint8_t)(((t & 0x1Fu) << 3) | (bus->ppu.fine_x & 7u));
    ppu_buf[3] = (uint8_t)((((t >> 5) & 0x1Fu) << 3) | ((t >> 12) & 7u));
    memcpy(&ppu_buf[4], bus->palette, NES_PAL_SIZE);
    uint32_t ppu_crc = d4b_crc32(ppu_buf, sizeof(ppu_buf));
    uint32_t apu_crc = d4b_crc32(bus->apu.regs, 24u);

    fprintf(fp, "%s{\"frame\":%u,\"wramCrc32\":\"%08x\",\"oamCrc32\":\"%08x\","
                "\"ppuCrc32\":\"%08x\",\"apuCrc32\":\"%08x\"}",
            (f > 1u) ? "," : "", f, wram_crc, oam_crc, ppu_crc, apu_crc);
}

int d4b_run_lockstep_cli(const char *rom_path, const char *out_json_path) {
    if (!rom_path || !out_json_path || !nes_bus_load_ines(&s_lockstep_bus, rom_path)) {
        return 1;
    }
    FILE *fp = fopen(out_json_path, "wb");
    if (!fp) {
        return 1;
    }
    D4bCheckpoint cps[8];
    memset(cps, 0, sizeof(cps));
    size_t cp_cnt = 0u;

    fprintf(fp, "{\"schemaVersion\":2,\"totalFrames\":650,\"frames\":[");
    for (uint32_t f = 1u; f <= 650u; ++f) {
        nes_bus_step_frame(&s_lockstep_bus, scene_input_mask(f));
        write_frame_json(fp, f, &s_lockstep_bus);
        run_checkpoint(f, &s_lockstep_bus, cps, &cp_cnt);
    }
    fprintf(fp, "],\"checkpoints\":[");
    for (size_t i = 0u; i < cp_cnt; ++i) {
        fprintf(fp, "%s{\"name\":\"%s\",\"frame\":%u,\"isPassed\":%s,\"detail\":\"%s\"}",
                (i > 0u) ? "," : "", cps[i].name, cps[i].frame,
                cps[i].is_passed ? "true" : "false", cps[i].detail);
    }
    fprintf(fp, "]}\n");
    return (fclose(fp) == 0) ? 0 : 1;
}
