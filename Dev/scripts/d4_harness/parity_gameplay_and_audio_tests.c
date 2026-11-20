#include <stdio.h>

#include "metalgear_globals.h"
#include "metalgear_functions.h"
#include "parity_harness.h"

static int test_06_self_destruct_countdown(const char *dir, TestResult *r) {
    uint8_t bank0[PRG_BANK_SIZE];
    r->name = "self_destruct_countdown_timer";
    if (!d4_load_prg(dir, "BANK_00.prg", bank0, sizeof(bank0))) {
        snprintf(r->detail, sizeof(r->detail), "missing BANK_00.prg");
        return 0;
    }
    int sig_ok = (bank0[0x3F50u] == 0xA5u) && (bank0[0x3F51u] == 0x67u) &&
                 (bank0[0x3F52u] == 0xC9u) && (bank0[0x3F53u] == 0x07u) &&
                 (bank0[0x3F7Au] == 0x20u) && (bank0[0x3F7Bu] == 0x2Cu) && (bank0[0x3F7Cu] == 0xCAu);
    g_zp_var_0067 = 0u;
    mg_b034_set_timer_state_67(7u);
    int set_ok = (g_zp_var_0067 == 7u);
    g_zp_var_0071 = 1u;
    g_frame_counter = 3u;
    mg_b034_tick_countdown_timer_and_hud();
    int tick_ok = (g_zp_var_0067 == 0u);
    g_state_timer_lo = 2u;
    g_state_timer_hi = 0u;
    uint8_t rem = mg_fxa_tick_state_timer();
    int state_ok = (g_state_timer_lo == 1u) && (rem != 0u);
    snprintf(r->detail, sizeof(r->detail), "sig=%d timer_67=(7->%u) state_lo=%u", sig_ok && set_ok, g_zp_var_0067, g_state_timer_lo);
    return sig_ok && set_ok && tick_ok && state_ok;
}

static int test_07_alert_and_mode_reset(const char *dir, TestResult *r) {
    uint8_t prg7[PRG_BANK_SIZE];
    uint8_t bank0[PRG_BANK_SIZE];
    r->name = "guard_alert_and_mode_reset";
    if (!d4_load_prg(dir, "PRG_FIXED_07.prg", prg7, sizeof(prg7)) ||
        !d4_load_prg(dir, "BANK_00.prg", bank0, sizeof(bank0))) {
        snprintf(r->detail, sizeof(r->detail), "missing PRG binary");
        return 0;
    }
    int rom_ok = (prg7[0x423Fu] != 0xFFu) && (bank0[0x2765u] != 0xFFu) && (bank0[0x2771u] != 0xFFu);
    g_game_submode = 9u;
    g_title_exit_flag = 1u;
    uint8_t rc = mg_fxa_enter_game_mode(4u);
    int m1 = (rc == 0u) && (g_game_mode == 4u) && (g_state_timer_lo == 0x50u) &&
             (g_game_submode == 0u) && (g_title_exit_flag == 0u);
    g_game_submode = 3u;
    mg_fxa_advance_game_mode();
    int m2 = (g_game_mode == 5u) && (g_game_submode == 0u);
    snprintf(r->detail, sizeof(r->detail), "rom=%d enter=%d advance=%u", rom_ok, m1, g_game_mode);
    return rom_ok && m1 && m2;
}

static int test_08_transceiver_codec_lut(const char *dir, TestResult *r) {
    uint8_t bank5[PRG_BANK_SIZE];
    r->name = "transceiver_codec_freq_lut";
    if (!d4_load_prg(dir, "BANK_05.prg", bank5, sizeof(bank5))) {
        snprintf(r->detail, sizeof(r->detail), "missing BANK_05.prg");
        return 0;
    }
    int ptr_ok = 1;
    for (size_t i = 0; i < 64u; ++i) {
        uint16_t lo_ptr = d4_rd16(bank5, 0x3B65u + i * 2u);
        uint16_t hi_ptr = d4_rd16(bank5, 0x3C65u + i * 2u);
        if (lo_ptr < 0x8000u || lo_ptr >= 0xC000u || hi_ptr < 0x8000u || hi_ptr >= 0xC000u) {
            ptr_ok = 0;
        }
    }
    int lut_term = (bank5[0x398Au] == 0xFFu);
    snprintf(r->detail, sizeof(r->detail), "ptr_bounds=%d freq_lut_ff=%d", ptr_ok, lut_term);
    return ptr_ok && lut_term;
}

static int test_09_bank06_audio_pause_mute(const char *dir, TestResult *r) {
    uint8_t bank6[PRG_BANK_SIZE];
    r->name = "bank06_audio_pause_mute_and_fe_loop";
    if (!d4_load_prg(dir, "BANK_06.prg", bank6, sizeof(bank6))) {
        snprintf(r->detail, sizeof(r->detail), "missing BANK_06.prg");
        return 0;
    }
    int note_ok = (d4_rd16(bank6, 0x1923u) == 0x06AEu);
    uint16_t prev = 0xFFFFu;
    for (size_t i = 0; i < 12u; ++i) {
        uint16_t period = d4_rd16(bank6, 0x1923u + i * 2u);
        if (period >= prev || period == 0u) {
            note_ok = 0;
        }
        prev = period;
    }
    int fe_ok = (bank6[0x16E4u] == 0xC9u) && (bank6[0x16E5u] == 0x0Eu) &&
                (bank6[0x1708u] == 0xFEu) && (bank6[0x1709u] == 0xCEu) && (bank6[0x170Au] == 0x03u);

    const uint8_t saved_d8 = 0x41u;
    g_snd_ram_03d8 = saved_d8;
    g_snd_ram_03cc = 0x42u;
    g_snd_ram_0390 = 0x43u;
    g_snd_ram_0396 = 0x44u;
    g_snd_ram_0384 = 0x45u;
    g_snd_ram_039c = 0x46u;
    g_snd_ram_03a2 = 0x47u;
    g_snd_pause_state = 0u;
    g_snd_ram_03ae = 0u;
    g_apu_pulse1_ctrl = 0u;
    g_apu_pulse2_ctrl = 0u;
    g_apu_noise_ctrl = 0u;
    g_apu_pulse1_sweep = 0u;
    g_apu_pulse2_sweep = 0u;
    g_pause_flag = 1u;
    g_zp_var_00ea = 0u;
    g_snd_ram_038a = 0x31u;
    mg_b56_audio_sync_pause_mute();
    int pause_ok = (g_zp_var_00ea == 1u) && (g_snd_pause_state == 0x31u) && (g_snd_pause_backup[0] == saved_d8) &&
                   (g_apu_pulse1_ctrl == 0x30u) && (g_apu_pulse2_ctrl == 0x30u) &&
                   (g_apu_noise_ctrl == 0x30u) && (g_apu_pulse1_sweep == 0x7fu) &&
                   (g_apu_pulse2_sweep == 0x7fu);

    g_snd_ram_03d8 = 0u;
    g_snd_ram_039c = 0u;
    g_snd_ram_03a2 = 0u;
    g_pause_flag = 0u;
    mg_b56_audio_sync_pause_mute();
    int resume_ok = (g_zp_var_00ea == 0u) && (g_snd_pause_state == 0u) &&
                    (g_snd_ram_03d8 == saved_d8) && (g_snd_ram_039c == 0x46u) && (g_snd_ram_03a2 == 0x47u);

    g_snd_ram_0388 = 0u;
    g_zp_var_00eb = 12u;
    g_apu_dmc_dac = 0u;
    mg_b56_audio_ramp_dmc_dac();
    int dmc_ok = (g_zp_var_00eb == 8u) && (g_apu_dmc_dac == 8u);

    snprintf(r->detail, sizeof(r->detail), "note_lut_12=%d fe_loop_sig=%d pause=%d resume=%d dmc=%d",
             note_ok, fe_ok, pause_ok, resume_ok, dmc_ok);
    return note_ok && fe_ok && pause_ok && resume_ok && dmc_ok;
}

static int test_10_room_metatile_bounds(const char *dir, TestResult *r) {
    uint8_t prg7[PRG_BANK_SIZE];
    uint8_t bank[PRG_BANK_SIZE];
    r->name = "room_metatile_pointer_bounds";
    if (!d4_load_prg(dir, "PRG_FIXED_07.prg", prg7, sizeof(prg7))) {
        snprintf(r->detail, sizeof(r->detail), "missing PRG_FIXED_07.prg");
        return 0;
    }
    int ok = 1;
    for (uint8_t b = 1u; b <= 4u; ++b) {
        char fname[32];
        snprintf(fname, sizeof(fname), "BANK_0%u.prg", (unsigned)b);
        if (!d4_load_prg(dir, fname, bank, sizeof(bank)) || bank[0] != b) {
            ok = 0;
            continue;
        }
        uint16_t p0 = d4_rd16(bank, 1u);
        uint16_t p1 = d4_rd16(bank, 3u);
        if (p0 < 0x8000u || p0 >= 0xC000u || p1 < 0x8000u || p1 >= 0xC000u) {
            ok = 0;
        }
    }
    int lut_nonzero = 0;
    for (size_t i = 0; i < 256u; ++i) {
        if (prg7[0x7D00u + i] != 0u || prg7[0x7E00u + i] != 0u) {
            lut_nonzero = 1;
        }
    }
    snprintf(r->detail, sizeof(r->detail), "bank1_4_ptrs_ok=%d fd00_fe00_pop=%d", ok, lut_nonzero);
    return ok && lut_nonzero;
}

int d4_run_gameplay_and_audio_tests(const char *dir, TestResult *results) {
    int passed = 0;
    passed += (results[0].isPassed = test_06_self_destruct_countdown(dir, &results[0]));
    passed += (results[1].isPassed = test_07_alert_and_mode_reset(dir, &results[1]));
    passed += (results[2].isPassed = test_08_transceiver_codec_lut(dir, &results[2]));
    passed += (results[3].isPassed = test_09_bank06_audio_pause_mute(dir, &results[3]));
    passed += (results[4].isPassed = test_10_room_metatile_bounds(dir, &results[4]));
    return passed;
}
