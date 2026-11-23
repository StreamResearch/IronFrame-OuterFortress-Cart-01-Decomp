/* @module: IronFrame.D4Harness.NesPpuApu */
/* @purpose: RP2C02 PPU registers/VRAM mirroring, RP2A03 APU/DMC latches, and cycle-synced frame stepper. */
#include <string.h>

#include "nes_bus.h"

typedef struct {
    uint16_t timer, period, addr, cur, len, rem;
    uint8_t bits, has_buf, loop, irq_en, delay;
} DmcState;

static const uint16_t k_dmc_rate[16] = {
    428u, 380u, 340u, 320u, 286u, 254u, 226u, 214u,
    190u, 160u, 142u, 128u, 106u, 84u, 72u, 54u
};
static int s_watch_240 = 0, s_hit_240 = 0, s_has_resume = 0;
static NesBus s_resume_bus;
static const DmcState k_dmc_init = { 419u, 427u, 0xC000u, 0xC000u, 1u, 0u, 8u, 0u, 0u, 0u, 0u };
static DmcState s_dmc = { 419u, 427u, 0xC000u, 0xC000u, 1u, 0u, 8u, 0u, 0u, 0u, 0u };
static DmcState s_resume_dmc;

int nes_ppu_tick_cycle(NesBus *bus);
int nes_ppu_dmc_check_read(NesBus *bus, uint16_t addr);

static void ppu_update_nmi(NesBus *bus) {
    uint8_t line = ((bus->ppu.ctrl & 0x80u) != 0u && (bus->ppu.status & 0x80u) != 0u) ? 1u : 0u;
    if (line != 0u && !bus->ppu.nmi_prev) { bus->cpu.nmi_pending = 1u; }
    bus->ppu.nmi_prev = line;
}

static uint16_t nt_map(const NesBus *bus, uint16_t addr) {
    uint16_t off = addr & 0x0FFFu;
    return (bus->mirroring != 0u) ? (off & 0x07FFu)
        : (uint16_t)(((off & 0x0800u) >> 1) | (off & 0x03FFu));
}

static uint16_t pal_map(uint16_t addr) {
    uint16_t off = addr & 0x1Fu;
    return ((off & 0x13u) == 0x10u) ? (uint16_t)(off & ~0x10u) : off;
}

static uint8_t ppu_vram_rd(const NesBus *bus, uint16_t addr) {
    uint16_t va = addr & 0x3FFFu;
    if (va < 0x2000u) { return bus->chr_ram[va]; }
    if (va < 0x3F00u) { return bus->nt_ram[nt_map(bus, va)]; }
    return bus->palette[pal_map(va)];
}

static void ppu_vram_wr(NesBus *bus, uint16_t addr, uint8_t val) {
    uint16_t va = addr & 0x3FFFu;
    if (va < 0x2000u) { bus->chr_ram[va] = val; return; }
    if (va < 0x3F00u) { bus->nt_ram[nt_map(bus, va)] = val; return; }
    uint8_t c = (uint8_t)(val & 0x3Fu);
    uint16_t p = pal_map(va);
    bus->palette[p] = c;
    if ((p & 0x03u) == 0u) { bus->palette[p ^ 0x10u] = c; }
}

uint8_t nes_ppu_read(NesBus *bus, uint16_t reg) {
    uint8_t r = (uint8_t)(reg & 7u);
    if (r == 2u) {
        uint8_t res = (uint8_t)((bus->ppu.status & 0xE0u) | (bus->open_bus & 0x1Fu));
        bus->ppu.status &= 0x7Fu;
        bus->ppu.w_latch = 0u;
        bus->ppu.nmi_occurred = 0u;
        bus->ppu.nmi_prev = 0u;
        return res;
    }
    if (r == 4u) { return bus->oam[bus->ppu.oam_addr]; }
    if (r == 7u) {
        uint16_t va = bus->ppu.vram_addr & 0x3FFFu;
        uint8_t res;
        if (va >= 0x3F00u) {
            uint8_t pal = bus->palette[pal_map(va)];
            if ((bus->ppu.mask & 0x01u) != 0u) { pal &= 0x30u; }
            res = (uint8_t)((pal & 0x3Fu) | (bus->open_bus & 0xC0u));
            bus->ppu.read_buf = bus->nt_ram[nt_map(bus, (uint16_t)(va & 0x2FFFu))];
        } else {
            res = bus->ppu.read_buf;
            bus->ppu.read_buf = ppu_vram_rd(bus, va);
        }
        bus->ppu.vram_addr = (uint16_t)((bus->ppu.vram_addr + ((bus->ppu.ctrl & 0x04u) ? 32u : 1u)) & 0x7FFFu);
        return res;
    }
    return bus->open_bus;
}

void nes_ppu_write(NesBus *bus, uint16_t reg, uint8_t val) {
    uint8_t r = (uint8_t)(reg & 7u);
    if (r == 0u) {
        bus->ppu.ctrl = val;
        bus->ppu.tmp_addr = (uint16_t)((bus->ppu.tmp_addr & ~0x0C00u) | (((uint16_t)val & 3u) << 10));
        ppu_update_nmi(bus);
    } else if (r == 1u) {
        bus->ppu.mask = val;
    } else if (r == 3u) {
        bus->ppu.oam_addr = val;
    } else if (r == 4u) {
        bus->oam[bus->ppu.oam_addr++] = val;
    } else if (r == 5u) {
        if (!bus->ppu.w_latch) {
            bus->ppu.scroll_x = val; bus->ppu.fine_x = val & 7u;
            bus->ppu.tmp_addr = (uint16_t)((bus->ppu.tmp_addr & ~0x001Fu) | (val >> 3));
        } else {
            bus->ppu.scroll_y = val;
            bus->ppu.tmp_addr = (uint16_t)((bus->ppu.tmp_addr & ~0x73E0u) |
                (((uint16_t)val & 7u) << 12) | (((uint16_t)val & 0xF8u) << 2));
        }
        bus->ppu.w_latch ^= 1u;
    } else if (r == 6u) {
        if (!bus->ppu.w_latch) {
            bus->ppu.tmp_addr = (uint16_t)((bus->ppu.tmp_addr & 0x00FFu) | (((uint16_t)val & 0x3Fu) << 8));
        } else {
            bus->ppu.tmp_addr = (uint16_t)((bus->ppu.tmp_addr & 0xFF00u) | val);
            bus->ppu.vram_addr = bus->ppu.tmp_addr;
        }
        bus->ppu.w_latch ^= 1u;
    } else if (r == 7u) {
        ppu_vram_wr(bus, bus->ppu.vram_addr, val);
        bus->ppu.vram_addr = (uint16_t)((bus->ppu.vram_addr + ((bus->ppu.ctrl & 0x04u) ? 32u : 1u)) & 0x7FFFu);
    }
}

void nes_apu_write(NesBus *bus, uint16_t addr, uint8_t val) {
    if (addr < 0x4000u || addr > 0x4017u) { return; }
    if (addr != 0x4014u && addr != 0x4016u) { bus->apu.regs[addr - 0x4000u] = val; }
    if (addr == 0x4010u) {
        s_dmc.irq_en = val & 0x80u; s_dmc.loop = val & 0x40u;
        s_dmc.period = (uint16_t)(k_dmc_rate[val & 0x0Fu] - 1u);
        if (!s_dmc.irq_en) { bus->apu.dmc_irq = 0u; }
    } else if (addr == 0x4012u) {
        s_dmc.addr = (uint16_t)(0xC000u | ((uint16_t)val << 6));
    } else if (addr == 0x4013u) {
        s_dmc.len = (uint16_t)(((uint16_t)val << 4) | 1u);
    } else if (addr == 0x4015u) {
        bus->apu.status_ctrl = val;
        bus->apu.dmc_irq = 0u;
        if ((val & 0x10u) == 0u) { s_dmc.rem = 0u; }
        else if (s_dmc.rem == 0u) {
            s_dmc.cur = s_dmc.addr; s_dmc.rem = s_dmc.len;
            if (!s_dmc.has_buf) { s_dmc.delay = (uint8_t)((bus->cpu.cycles & 1u) ? 2u : 3u); }
        }
    } else if (addr == 0x4017u) {
        bus->apu.frame_ctrl = val;
        if ((val & 0x40u) != 0u) { bus->apu.frame_irq = 0u; }
    }
}

uint8_t nes_apu_read(NesBus *bus, uint16_t addr) {
    if (addr != 0x4015u) { return bus->open_bus; }
    uint8_t st = (uint8_t)((bus->apu.status_ctrl & 0x1Fu) |
        (bus->apu.frame_irq ? 0x40u : 0u) | (bus->apu.dmc_irq ? 0x80u : 0u));
    bus->apu.frame_irq = 0u;
    return st;
}

static int ppu_dot_step(NesBus *bus) {
    for (int d = 0; d < 3; ++d) {
        if (bus->ppu.scanline == 241 && bus->ppu.dot == 1) {
            bus->ppu.status |= 0x80u; bus->ppu.nmi_occurred = 1u;
            ppu_update_nmi(bus);
        } else if (bus->ppu.scanline == 261 && bus->ppu.dot == 1) {
            bus->ppu.status &= (uint8_t)~0xE0u; bus->ppu.nmi_occurred = 0u; bus->ppu.nmi_prev = 0u;
        }
        if (bus->ppu.scanline == 261 && bus->ppu.dot == 339 &&
            (bus->ppu.frame_count & 1u) != 0u && (bus->ppu.mask & 0x18u) != 0u) {
            bus->ppu.dot = 340;
        }
        if (++bus->ppu.dot >= 341) {
            bus->ppu.dot = 0;
            if (++bus->ppu.scanline >= 262) {
                bus->ppu.scanline = 0; bus->ppu.frame_count++;
            } else if (bus->ppu.scanline == 240 && s_watch_240) {
                s_hit_240 = 1; return 1;
            }
        }
    }
    return 0;
}

static void dmc_clock_one(void) {
    if (s_dmc.timer > 0u) { s_dmc.timer--; return; }
    s_dmc.timer = s_dmc.period;
    if (--s_dmc.bits == 0u) {
        s_dmc.bits = 8u;
        if (s_dmc.has_buf) {
            s_dmc.has_buf = 0u;
            if (s_dmc.rem > 0u && s_dmc.delay == 0u) { s_dmc.delay = 2u; }
        }
    }
}

int nes_ppu_tick_cycle(NesBus *bus) {
    if (s_hit_240 || ppu_dot_step(bus)) { return 1; }
    dmc_clock_one();
    if (s_dmc.delay > 0u) { s_dmc.delay--; }
    return 0;
}

int nes_ppu_dmc_check_read(NesBus *bus, uint16_t addr) {
    if (s_dmc.rem == 0u || s_dmc.has_buf || s_dmc.delay != 0u) { return 0; }
    s_dmc.has_buf = 1u;
    s_dmc.cur = (s_dmc.cur == 0xFFFFu) ? 0x8000u : (uint16_t)(s_dmc.cur + 1u);
    if (--s_dmc.rem == 0u) {
        if (s_dmc.loop) { s_dmc.cur = s_dmc.addr; s_dmc.rem = s_dmc.len; }
        else if (s_dmc.irq_en) { bus->apu.dmc_irq = 1u; }
    }
    /* RP2A03 DMC DMA stalls 3-4 cycles by GET/PUT alignment, double-clocking $4016. */
    if (addr == 0x4016u) { (void)nes_bus_read(bus, addr); }
    int st = ((bus->cpu.cycles & 1u) != 0u) ? 4 : 3;
    for (int k = 0; k < st; ++k) {
        if (nes_ppu_tick_cycle(bus)) { return 1; }
        bus->cpu.cycles++;
    }
    return 0;
}

static void drain_stall(NesBus *bus) {
    while (!s_hit_240 && bus->cpu.stall_cycles > 0u) {
        if (!nes_ppu_tick_cycle(bus)) { bus->cpu.cycles++; bus->cpu.stall_cycles--; }
    }
}

void nes_bus_step_frame(NesBus *bus, uint8_t joy1_mask) {
    if (!bus) { return; }
    if (bus->cpu.cycles == 7u && bus->ppu.scanline == 0) { s_dmc = k_dmc_init; s_has_resume = 0; }
    int resumed = s_has_resume;
    if (s_has_resume) { *bus = s_resume_bus; s_dmc = s_resume_dmc; s_has_resume = 0; }
    bus->joy1_latch = joy1_mask;
    if ((bus->joy_strobe & 1u) != 0u) { bus->joy1_shift = joy1_mask; }
    s_watch_240 = 0; s_hit_240 = 0;
    if (resumed || bus->ppu.scanline == 240) { nes_cpu_step(bus); drain_stall(bus); }
    s_watch_240 = 1;
    while (!s_hit_240) {
        int near_240 = (bus->ppu.scanline == 239 && bus->ppu.dot >= 312);
        if (near_240) { s_resume_bus = *bus; s_resume_dmc = s_dmc; }
        nes_cpu_step(bus);
        drain_stall(bus);
        if (s_hit_240 && near_240) { s_has_resume = 1; }
    }
    s_watch_240 = 0; s_hit_240 = 0;
}
