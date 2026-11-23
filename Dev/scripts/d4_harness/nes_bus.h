/*
 * @module: IronFrame.D4Harness.NesBus
 * @purpose: Clean-room C11 NES UNROM bus, PPU/APU register, and 6502 execution contract for D4b lockstep.
 */
#ifndef D4B_NES_BUS_H
#define D4B_NES_BUS_H

#include <stddef.h>
#include <stdint.h>

#define NES_WRAM_SIZE     2048u
#define NES_OAM_SIZE       256u
#define NES_CHR_SIZE      8192u
#define NES_NT_SIZE       2048u
#define NES_PAL_SIZE        32u
#define NES_PRG_BANK_SIZE 16384u
#define NES_PRG_BANKS        8u

#define NES_BTN_A      0x01u
#define NES_BTN_B      0x02u
#define NES_BTN_SELECT 0x04u
#define NES_BTN_START  0x08u
#define NES_BTN_UP     0x10u
#define NES_BTN_DOWN   0x20u
#define NES_BTN_LEFT   0x40u
#define NES_BTN_RIGHT  0x80u

typedef struct {
    uint8_t a;
    uint8_t x;
    uint8_t y;
    uint8_t sp;
    uint8_t status;
    uint16_t pc;
    uint8_t nmi_pending;
    uint8_t irq_pending;
    uint32_t stall_cycles;
    uint64_t cycles;
} NesCpuState;

typedef struct {
    uint8_t ctrl;
    uint8_t mask;
    uint8_t status;
    uint8_t oam_addr;
    uint8_t scroll_x;
    uint8_t scroll_y;
    uint8_t w_latch;
    uint16_t vram_addr;
    uint16_t tmp_addr;
    uint8_t fine_x;
    uint8_t read_buf;
    int16_t scanline;
    int16_t dot;
    uint64_t frame_count;
    uint8_t nmi_occurred;
    uint8_t nmi_prev;
} NesPpuState;

typedef struct {
    uint8_t regs[24];
    uint8_t frame_ctrl;
    uint8_t status_ctrl;
    uint8_t dmc_irq;
    uint8_t frame_irq;
} NesApuState;

typedef struct {
    NesCpuState cpu;
    NesPpuState ppu;
    NesApuState apu;
    uint8_t wram[NES_WRAM_SIZE];
    uint8_t oam[NES_OAM_SIZE];
    uint8_t chr_ram[NES_CHR_SIZE];
    uint8_t nt_ram[NES_NT_SIZE];
    uint8_t palette[NES_PAL_SIZE];
    uint8_t prg_banks[NES_PRG_BANKS][NES_PRG_BANK_SIZE];
    uint8_t prg_bank;
    uint8_t mirroring;
    uint8_t joy1_latch;
    uint8_t joy1_shift;
    uint8_t joy_strobe;
    uint8_t open_bus;
} NesBus;

int nes_bus_load_ines(NesBus *bus, const char *rom_path);
void nes_bus_reset(NesBus *bus);
uint8_t nes_bus_read(NesBus *bus, uint16_t addr);
void nes_bus_write(NesBus *bus, uint16_t addr, uint8_t val);

uint8_t nes_ppu_read(NesBus *bus, uint16_t reg);
void nes_ppu_write(NesBus *bus, uint16_t reg, uint8_t val);
void nes_apu_write(NesBus *bus, uint16_t addr, uint8_t val);
uint8_t nes_apu_read(NesBus *bus, uint16_t addr);

int nes_cpu_step(NesBus *bus);
void nes_cpu_nmi(NesBus *bus);
void nes_bus_step_frame(NesBus *bus, uint8_t joy1_mask);

uint32_t d4b_crc32(const uint8_t *data, size_t len);
int d4b_run_lockstep_cli(const char *rom_path, const char *out_json_path);

#endif
