/* @module: IronFrame.D4Harness.NesBus */
/* @purpose: Clean-room UNROM Mapper 2 loader, cold-boot reset, CPU bus routing, and IEEE 802.3 CRC32. */
#include <stdio.h>
#include <string.h>

#include "nes_bus.h"

static const uint8_t k_poweron_palette[NES_PAL_SIZE] = {
    0x09u, 0x01u, 0x00u, 0x01u, 0x00u, 0x02u, 0x02u, 0x0Du,
    0x08u, 0x10u, 0x08u, 0x24u, 0x00u, 0x00u, 0x04u, 0x2Cu,
    0x09u, 0x01u, 0x34u, 0x03u, 0x00u, 0x04u, 0x00u, 0x14u,
    0x08u, 0x3Au, 0x00u, 0x02u, 0x00u, 0x20u, 0x2Cu, 0x08u
};

static uint8_t prg_read_raw(const NesBus *bus, uint16_t addr) {
    if (addr < 0xC000u) {
        return bus->prg_banks[bus->prg_bank & 7u][addr & 0x3FFFu];
    }
    return bus->prg_banks[NES_PRG_BANKS - 1u][addr & 0x3FFFu];
}

int nes_bus_load_ines(NesBus *bus, const char *rom_path) {
    if (!bus || !rom_path) {
        return 0;
    }
    FILE *fp = fopen(rom_path, "rb");
    if (!fp) {
        return 0;
    }
    uint8_t hdr[16];
    if (fread(hdr, 1u, sizeof(hdr), fp) != sizeof(hdr) ||
        hdr[0] != 'N' || hdr[1] != 'E' || hdr[2] != 'S' || hdr[3] != 0x1Au) {
        fclose(fp);
        return 0;
    }
    size_t prg_cnt = hdr[4];
    if ((hdr[7] & 0x0Cu) == 0x08u) {
        prg_cnt |= (size_t)(hdr[9] & 0x0Fu) << 8;
    }
    if (prg_cnt == 0u || prg_cnt > NES_PRG_BANKS) {
        fclose(fp);
        return 0;
    }
    if ((hdr[6] & 0x04u) != 0u && fseek(fp, 512L, SEEK_CUR) != 0) {
        fclose(fp);
        return 0;
    }
    memset(bus->prg_banks, 0, sizeof(bus->prg_banks));
    for (size_t i = 0u; i < prg_cnt; ++i) {
        if (fread(bus->prg_banks[i], 1u, NES_PRG_BANK_SIZE, fp) != NES_PRG_BANK_SIZE) {
            fclose(fp);
            return 0;
        }
    }
    fclose(fp);
    /* Mirror shorter synthetic carts so fixed bank 7 maps the final PRG bank. */
    if (prg_cnt < NES_PRG_BANKS) {
        for (size_t i = prg_cnt; i < NES_PRG_BANKS - 1u; ++i) {
            memcpy(bus->prg_banks[i], bus->prg_banks[i % prg_cnt], NES_PRG_BANK_SIZE);
        }
        memcpy(bus->prg_banks[NES_PRG_BANKS - 1u], bus->prg_banks[prg_cnt - 1u], NES_PRG_BANK_SIZE);
    }
    bus->mirroring = (uint8_t)(hdr[6] & 0x01u);
    nes_bus_reset(bus);
    return 1;
}

void nes_bus_reset(NesBus *bus) {
    if (!bus) {
        return;
    }
    memset(&bus->cpu, 0, sizeof(bus->cpu));
    memset(&bus->ppu, 0, sizeof(bus->ppu));
    memset(&bus->apu, 0, sizeof(bus->apu));
    memset(bus->wram, 0, sizeof(bus->wram));
    memset(bus->oam, 0, sizeof(bus->oam));
    memset(bus->chr_ram, 0, sizeof(bus->chr_ram));
    memset(bus->nt_ram, 0, sizeof(bus->nt_ram));
    memcpy(bus->palette, k_poweron_palette, sizeof(bus->palette));
    bus->prg_bank = 0u;
    bus->joy1_latch = 0u;
    bus->joy1_shift = 0u;
    bus->joy_strobe = 0u;
    bus->open_bus = 0u;
    bus->cpu.sp = 0xFDu;
    bus->cpu.status = 0x24u;
    bus->cpu.pc = (uint16_t)nes_bus_read(bus, 0xFFFCu) | ((uint16_t)nes_bus_read(bus, 0xFFFDu) << 8);
    bus->cpu.cycles = 7u;
    bus->ppu.dot = 24;
}

uint8_t nes_bus_read(NesBus *bus, uint16_t addr) {
    uint8_t val = bus->open_bus;
    if (addr < 0x2000u) {
        val = bus->wram[addr & 0x07FFu];
    } else if (addr < 0x4000u) {
        val = nes_ppu_read(bus, (uint16_t)(0x2000u | (addr & 7u)));
    } else if (addr == 0x4015u) {
        return nes_apu_read(bus, addr);
    } else if (addr == 0x4016u) {
        uint8_t bit = 0u;
        if ((bus->joy_strobe & 1u) != 0u) {
            bit = bus->joy1_latch & 1u;
        } else {
            bit = bus->joy1_shift & 1u;
            bus->joy1_shift = (uint8_t)((bus->joy1_shift >> 1) | 0x80u);
        }
        val = (uint8_t)((bus->open_bus & 0xE0u) | bit);
    } else if (addr == 0x4017u) {
        val = (uint8_t)(bus->open_bus & 0xE0u);
    } else if (addr >= 0x8000u) {
        val = prg_read_raw(bus, addr);
    }
    bus->open_bus = val;
    return val;
}

void nes_bus_write(NesBus *bus, uint16_t addr, uint8_t val) {
    bus->open_bus = val;
    if (addr < 0x2000u) {
        bus->wram[addr & 0x07FFu] = val;
    } else if (addr < 0x4000u) {
        nes_ppu_write(bus, (uint16_t)(0x2000u | (addr & 7u)), val);
    } else if (addr == 0x4014u) {
        uint16_t base = (uint16_t)val << 8;
        for (uint16_t i = 0u; i < 256u; ++i) {
            uint8_t b = nes_bus_read(bus, (uint16_t)(base + i));
            bus->oam[bus->ppu.oam_addr] = b;
            bus->ppu.oam_addr = (uint8_t)(bus->ppu.oam_addr + 1u);
        }
        bus->cpu.stall_cycles += (uint32_t)(513u + (bus->cpu.cycles & 1u));
    } else if (addr == 0x4016u) {
        uint8_t next = val & 1u;
        if (next != 0u) {
            bus->joy_strobe = 1u;
            bus->joy1_shift = bus->joy1_latch;
        } else if (bus->joy_strobe != 0u) {
            bus->joy_strobe = 0u;
            bus->joy1_shift = bus->joy1_latch;
        }
    } else if (addr >= 0x4000u && addr <= 0x4017u) {
        nes_apu_write(bus, addr, val);
    } else if (addr >= 0x8000u) {
        bus->prg_bank = (uint8_t)((val & prg_read_raw(bus, addr)) & 7u);
    }
}

uint32_t d4b_crc32(const uint8_t *data, size_t len) {
    uint32_t crc = 0xFFFFFFFFu;
    for (size_t i = 0u; i < len; ++i) {
        crc ^= (uint32_t)data[i];
        for (uint32_t b = 0u; b < 8u; ++b) {
            uint32_t mask = (uint32_t)-(int32_t)(crc & 1u);
            crc = (crc >> 1) ^ (0xEDB88320u & mask);
        }
    }
    return ~crc;
}
