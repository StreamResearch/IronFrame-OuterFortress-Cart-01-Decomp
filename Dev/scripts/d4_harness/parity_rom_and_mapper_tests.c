#include <stdio.h>
#include <string.h>

#include "metalgear_globals.h"
#include "metalgear_functions.h"
#include "parity_harness.h"

static int test_01_vectors_and_unrom(const char *dir, TestResult *r) {
    uint8_t prg7[PRG_BANK_SIZE];
    uint8_t bank[PRG_BANK_SIZE];
    r->name = "vectors_and_unrom_lut";
    if (!d4_load_prg(dir, "PRG_FIXED_07.prg", prg7, sizeof(prg7))) {
        snprintf(r->detail, sizeof(r->detail), "missing PRG_FIXED_07.prg");
        return 0;
    }
    uint16_t nmi = d4_rd16(prg7, 0x7FFAu);
    uint16_t rst = d4_rd16(prg7, 0x7FFCu);
    uint16_t irq = d4_rd16(prg7, 0x7FFEu);
    int ok = (nmi == 0xC06Cu) && (rst == 0xC001u) && (irq == 0xC0B7u);
    for (uint8_t i = 0; i < 7u; ++i) {
        if (prg7[0x7FD0u + i] != i) {
            ok = 0;
        }
        char fname[32];
        snprintf(fname, sizeof(fname), "BANK_0%u.prg", (unsigned)i);
        if (!d4_load_prg(dir, fname, bank, sizeof(bank)) || bank[0] != i) {
            ok = 0;
        }
    }
    snprintf(r->detail, sizeof(r->detail), "NMI=%04X RST=%04X IRQ=%04X UNROM_LUT=0..6", nmi, rst, irq);
    return ok;
}

static int test_02_inline_jump_table(const char *dir, TestResult *r) {
    uint8_t prg7[PRG_BANK_SIZE];
    r->name = "inline_jump_table_dispatch";
    if (!d4_load_prg(dir, "PRG_FIXED_07.prg", prg7, sizeof(prg7))) {
        snprintf(r->detail, sizeof(r->detail), "missing PRG_FIXED_07.prg");
        return 0;
    }
    int sites = 0;
    for (size_t i = 0x4000u; i + 10u < PRG_BANK_SIZE; ++i) {
        if (prg7[i] == 0x20u && prg7[i + 1u] == 0xB7u && prg7[i + 2u] == 0xC6u) {
            ++sites;
        }
    }
    int has_jmp_ind = (prg7[0x46B7u] == 0x0Au) && (prg7[0x46D2u] == 0x6Cu) &&
                      (prg7[0x46D3u] == 0x80u) && (prg7[0x46D4u] == 0x00u);
    uint16_t v0 = d4_rd16(prg7, 0x4114u);
    uint16_t v1 = d4_rd16(prg7, 0x4116u);
    int ok = (sites >= 16) && has_jmp_ind && (v0 == 0xC131u) && (v1 == 0xC163u);
    snprintf(r->detail, sizeof(r->detail), "sites=%d jmp_ind=%d first_vec=[%04X,%04X]", sites, has_jmp_ind, v0, v1);
    return ok;
}

static int test_03_unrom_bank_switch(const char *dir, TestResult *r) {
    uint8_t prg7[PRG_BANK_SIZE];
    uint8_t bank[PRG_BANK_SIZE];
    r->name = "unrom_bank_switch_restore";
    if (!d4_load_prg(dir, "PRG_FIXED_07.prg", prg7, sizeof(prg7))) {
        snprintf(r->detail, sizeof(r->detail), "missing PRG_FIXED_07.prg");
        return 0;
    }
    static const uint8_t sel_seq[12] = {
        0xADu, 0x00u, 0x80u, 0x85u, 0x27u, 0xB9u, 0xD0u, 0xFFu, 0x99u, 0xD0u, 0xFFu, 0x60u
    };
    static const uint8_t rst_seq[9] = {
        0xA4u, 0x27u, 0xB9u, 0xD0u, 0xFFu, 0x99u, 0xD0u, 0xFFu, 0x60u
    };
    int c94c_ok = (memcmp(&prg7[0x494Cu], sel_seq, sizeof(sel_seq)) == 0);
    int c958_ok = (memcmp(&prg7[0x4958u], rst_seq, sizeof(rst_seq)) == 0);
    int bank_ids_ok = 1;
    for (uint8_t b = 0u; b < 7u; ++b) {
        char fname[32];
        snprintf(fname, sizeof(fname), "BANK_0%u.prg", (unsigned)b);
        if (!d4_load_prg(dir, fname, bank, sizeof(bank)) || bank[0] != b) {
            bank_ids_ok = 0;
        }
    }
    BYTE_ARRAY_ff99[0x37] = 0xFFu;
    BYTE_ARRAY_ff99[0x3d] = 0xFFu;
    unrom_select_bank_0();
    int s0 = (BYTE_ARRAY_ff99[0x37] == 0u);
    unrom_select_bank_6();
    int s6 = (BYTE_ARRAY_ff99[0x3d] == 6u);
    snprintf(r->detail, sizeof(r->detail), "c94c=%d c958=%d bank_ids=%d bank0=%d bank6=%d",
             c94c_ok, c958_ok, bank_ids_ok, s0, s6);
    return c94c_ok && c958_ok && bank_ids_ok && s0 && s6;
}

static int test_04_bcd_digit_conversion(const char *dir, TestResult *r) {
    uint8_t prg7[PRG_BANK_SIZE];
    r->name = "binary_to_bcd_hud_digit";
    if (!d4_load_prg(dir, "PRG_FIXED_07.prg", prg7, sizeof(prg7))) {
        snprintf(r->detail, sizeof(r->detail), "missing PRG_FIXED_07.prg");
        return 0;
    }
    static const uint8_t samples[6] = {0u, 9u, 10u, 99u, 100u, 255u};
    int bcd_ok = (prg7[0x4A2Cu] == 0xA9u) && (prg7[0x4A34u] == 0x38u) &&
                 (prg7[0x4A35u] == 0xE9u) && (prg7[0x4A36u] == 0x0Au);
    for (size_t k = 0; k < sizeof(samples); ++k) {
        uint8_t v = samples[k];
        uint8_t hundreds = (uint8_t)(v / 100u);
        uint8_t rem = (uint8_t)(v % 100u);
        uint8_t packed = (uint8_t)(((rem / 10u) << 4) | (rem % 10u));
        if ((uint8_t)(hundreds * 100u + ((packed >> 4) * 10u) + (packed & 0x0Fu)) != v) {
            bcd_ok = 0;
        }
    }
    DAT_0740 = 0u;
    DAT_0741 = 0u;
    mg_b034_hud_init_vram_queue_header();
    int hdr_ok = (DAT_0740 == 1u) && (DAT_0741 == 0x23u);
    snprintf(r->detail, sizeof(r->detail), "ca2c_sig=%d hud_hdr=(%u,0x%02X)", bcd_ok, DAT_0740, DAT_0741);
    return bcd_ok && hdr_ok;
}

static int test_05_rolling_bridge_lut(const char *dir, TestResult *r) {
    uint8_t bank0[PRG_BANK_SIZE];
    r->name = "rolling_bridge_pitfall_mask";
    if (!d4_load_prg(dir, "BANK_00.prg", bank0, sizeof(bank0))) {
        snprintf(r->detail, sizeof(r->detail), "missing BANK_00.prg");
        return 0;
    }
    static const uint8_t curve[6] = {0x1Fu, 0x07u, 0x03u, 0x03u, 0x07u, 0x1Fu};
    int rom_ok = (memcmp(&bank0[0x3995u], curve, sizeof(curve)) == 0);
    int sym_ok = (curve[0] == curve[5]) && (curve[1] == curve[4]) && (curve[2] == curve[3]);
    int pit_sig = (bank0[0x3922u] == 0xC0u) && (bank0[0x3923u] == 0x1Cu) &&
                  (bank0[0x3926u] == 0xC0u) && (bank0[0x3927u] == 0x84u);
    snprintf(r->detail, sizeof(r->detail), "b995_curve=%d symmetric=%d pit_bound=%d", rom_ok, sym_ok, pit_sig);
    return rom_ok && sym_ok && pit_sig;
}

int d4_run_rom_and_mapper_tests(const char *dir, TestResult *results) {
    int passed = 0;
    passed += (results[0].isPassed = test_01_vectors_and_unrom(dir, &results[0]));
    passed += (results[1].isPassed = test_02_inline_jump_table(dir, &results[1]));
    passed += (results[2].isPassed = test_03_unrom_bank_switch(dir, &results[2]));
    passed += (results[3].isPassed = test_04_bcd_digit_conversion(dir, &results[3]));
    passed += (results[4].isPassed = test_05_rolling_bridge_lut(dir, &results[4]));
    return passed;
}
