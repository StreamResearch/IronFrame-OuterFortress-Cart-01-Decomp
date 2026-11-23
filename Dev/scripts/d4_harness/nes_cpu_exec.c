/* @module: IronFrame.D4Harness.NesCpuExec */
/* @purpose: Cycle-accurate RP2A03 6502 addressing, stack/interrupt dispatch, and step engine. */
#include "nes_bus.h"

enum {
    OP_ILL = 0, OP_ASL = 3, OP_BCC = 4, OP_BRK = 11, OP_BVS = 13, OP_DEC = 21, OP_INC = 25,
    OP_JMP = 28, OP_JSR = 29, OP_LSR = 33, OP_PHA = 36, OP_PHP = 37, OP_PLA = 38, OP_PLP = 39,
    OP_ROL = 40, OP_ROR = 41, OP_RTI = 42, OP_RTS = 43, OP_STA = 48, OP_STX = 49, OP_STY = 50
};
enum {
    AM_IMP = 0, AM_ACC = 1, AM_IMM = 2, AM_ZP = 3, AM_ZPX = 4, AM_ZPY = 5, AM_ABS = 6,
    AM_ABX = 7, AM_ABY = 8, AM_IND = 9, AM_IDX = 10, AM_IDY = 11, AM_REL = 12
};

int nes_ppu_tick_cycle(NesBus *bus);
int nes_ppu_dmc_check_read(NesBus *bus, uint16_t addr);
void nes_cpu_decode_op(uint8_t opcode, uint8_t *out_op, uint8_t *out_mode);
uint8_t nes_cpu_zn(NesBus *bus, uint8_t v);
void nes_cpu_alu(NesBus *bus, uint8_t op, uint8_t val);
uint8_t nes_cpu_rmw(NesBus *bus, uint8_t op, uint8_t val);
int nes_cpu_branch_cond(const NesBus *bus, uint8_t op);
void nes_cpu_reg_op(NesBus *bus, uint8_t op);

static int s_aborted = 0;

static uint8_t cpu_rd(NesBus *bus, uint16_t addr) {
    if (s_aborted || nes_ppu_tick_cycle(bus) || nes_ppu_dmc_check_read(bus, addr)) {
        s_aborted = 1;
        return 0u;
    }
    bus->cpu.cycles++;
    return nes_bus_read(bus, addr);
}

static void cpu_wr(NesBus *bus, uint16_t addr, uint8_t val) {
    if (s_aborted || nes_ppu_tick_cycle(bus)) {
        s_aborted = 1;
        return;
    }
    bus->cpu.cycles++;
    nes_bus_write(bus, addr, val);
}

static uint8_t fetch8(NesBus *bus) {
    uint8_t v = cpu_rd(bus, bus->cpu.pc);
    if (!s_aborted) { bus->cpu.pc++; }
    return v;
}

static uint16_t fetch16(NesBus *bus) {
    uint8_t lo = fetch8(bus);
    uint8_t hi = fetch8(bus);
    return (uint16_t)(lo | ((uint16_t)hi << 8));
}

static void push8(NesBus *bus, uint8_t val) {
    cpu_wr(bus, (uint16_t)(0x0100u | bus->cpu.sp), val);
    if (!s_aborted) { bus->cpu.sp--; }
}

static uint8_t pop8(NesBus *bus) {
    uint8_t v = cpu_rd(bus, (uint16_t)(0x0100u | (uint8_t)(bus->cpu.sp + 1u)));
    if (!s_aborted) { bus->cpu.sp++; }
    return v;
}

static void push16(NesBus *bus, uint16_t val) {
    push8(bus, (uint8_t)(val >> 8));
    push8(bus, (uint8_t)(val & 0xFFu));
}

static uint16_t pop16(NesBus *bus) {
    uint8_t lo = pop8(bus);
    uint8_t hi = pop8(bus);
    return (uint16_t)(lo | ((uint16_t)hi << 8));
}

static void service_interrupt(NesBus *bus, uint16_t vec_addr) {
    cpu_rd(bus, bus->cpu.pc);
    cpu_rd(bus, bus->cpu.pc);
    push16(bus, bus->cpu.pc);
    push8(bus, (uint8_t)((bus->cpu.status | 0x20u) & ~0x10u));
    if (s_aborted) { return; }
    bus->cpu.status |= 0x04u;
    uint16_t target = (uint16_t)cpu_rd(bus, vec_addr) | ((uint16_t)cpu_rd(bus, (uint16_t)(vec_addr + 1u)) << 8);
    if (!s_aborted) { bus->cpu.pc = target; }
}

void nes_cpu_nmi(NesBus *bus) {
    if (bus) {
        s_aborted = 0;
        service_interrupt(bus, 0xFFFAu);
    }
}

static uint16_t resolve_addr(NesBus *bus, uint8_t mode, int force_dummy) {
    if (mode == AM_ZP) { return fetch8(bus); }
    if (mode == AM_ZPX || mode == AM_ZPY) {
        uint8_t zp = fetch8(bus);
        cpu_rd(bus, zp);
        return (uint8_t)(zp + (mode == AM_ZPX ? bus->cpu.x : bus->cpu.y));
    }
    if (mode == AM_ABS) { return fetch16(bus); }
    if (mode == AM_ABX || mode == AM_ABY) {
        uint16_t base = fetch16(bus);
        uint16_t eff = (uint16_t)(base + (mode == AM_ABX ? bus->cpu.x : bus->cpu.y));
        if (force_dummy || (base & 0xFF00u) != (eff & 0xFF00u)) {
            cpu_rd(bus, (uint16_t)((base & 0xFF00u) | (eff & 0x00FFu)));
        }
        return eff;
    }
    if (mode == AM_IDX) {
        uint8_t base = fetch8(bus);
        cpu_rd(bus, base);
        uint8_t ptr = (uint8_t)(base + bus->cpu.x);
        return (uint16_t)cpu_rd(bus, ptr) | ((uint16_t)cpu_rd(bus, (uint8_t)(ptr + 1u)) << 8);
    }
    if (mode == AM_IDY) {
        uint8_t ptr = fetch8(bus);
        uint16_t base = (uint16_t)cpu_rd(bus, ptr) | ((uint16_t)cpu_rd(bus, (uint8_t)(ptr + 1u)) << 8);
        uint16_t eff = (uint16_t)(base + bus->cpu.y);
        if (force_dummy || (base & 0xFF00u) != (eff & 0xFF00u)) {
            cpu_rd(bus, (uint16_t)((base & 0xFF00u) | (eff & 0x00FFu)));
        }
        return eff;
    }
    /* AM_IND: replicate 6502 page-boundary wrap on JMP ($xxFF). */
    uint16_t ptr = fetch16(bus);
    uint8_t lo = cpu_rd(bus, ptr);
    uint16_t hi_p = (uint16_t)((ptr & 0xFF00u) | ((ptr + 1u) & 0x00FFu));
    return (uint16_t)(lo | ((uint16_t)cpu_rd(bus, hi_p) << 8));
}

static void exec_control_or_stack(NesBus *bus, uint8_t op, uint8_t mode) {
    if (op == OP_JMP) {
        uint16_t tgt = resolve_addr(bus, mode, 0);
        if (!s_aborted) { bus->cpu.pc = tgt; }
    } else if (op == OP_JSR) {
        uint8_t lo = fetch8(bus);
        cpu_rd(bus, (uint16_t)(0x0100u | bus->cpu.sp));
        push16(bus, bus->cpu.pc);
        uint8_t hi = cpu_rd(bus, bus->cpu.pc);
        if (!s_aborted) { bus->cpu.pc = (uint16_t)(lo | ((uint16_t)hi << 8)); }
    } else if (op == OP_RTS) {
        cpu_rd(bus, bus->cpu.pc);
        cpu_rd(bus, (uint16_t)(0x0100u | bus->cpu.sp));
        uint16_t ret = (uint16_t)(pop16(bus) + 1u);
        cpu_rd(bus, (uint16_t)(ret - 1u));
        if (!s_aborted) { bus->cpu.pc = ret; }
    } else if (op == OP_RTI) {
        cpu_rd(bus, bus->cpu.pc);
        cpu_rd(bus, (uint16_t)(0x0100u | bus->cpu.sp));
        uint8_t st = (uint8_t)((pop8(bus) & ~0x10u) | 0x20u);
        uint16_t pc = pop16(bus);
        if (!s_aborted) { bus->cpu.status = st; bus->cpu.pc = pc; }
    } else if (op == OP_BRK) {
        fetch8(bus);
        push16(bus, bus->cpu.pc);
        push8(bus, (uint8_t)(bus->cpu.status | 0x30u));
        uint16_t vec = (uint16_t)cpu_rd(bus, 0xFFFEu) | ((uint16_t)cpu_rd(bus, 0xFFFFu) << 8);
        if (!s_aborted) { bus->cpu.status |= 0x04u; bus->cpu.pc = vec; }
    } else if (op == OP_PHA || op == OP_PHP) {
        cpu_rd(bus, bus->cpu.pc);
        push8(bus, (op == OP_PHA) ? bus->cpu.a : (uint8_t)(bus->cpu.status | 0x30u));
    } else if (op == OP_PLA || op == OP_PLP) {
        cpu_rd(bus, bus->cpu.pc);
        cpu_rd(bus, (uint16_t)(0x0100u | bus->cpu.sp));
        uint8_t v = pop8(bus);
        if (!s_aborted) {
            if (op == OP_PLA) { bus->cpu.a = nes_cpu_zn(bus, v); }
            else { bus->cpu.status = (uint8_t)((v & ~0x10u) | 0x20u); }
        }
    }
}

static int is_rmw_op(uint8_t op) {
    return op == OP_ASL || op == OP_LSR || op == OP_ROL || op == OP_ROR || op == OP_INC || op == OP_DEC;
}

int nes_cpu_step(NesBus *bus) {
    if (!bus) { return 0; }
    s_aborted = 0;
    uint64_t start_cyc = bus->cpu.cycles;
    if (bus->cpu.nmi_pending != 0u) {
        bus->cpu.nmi_pending = 0u;
        service_interrupt(bus, 0xFFFAu);
        return (int)(bus->cpu.cycles - start_cyc);
    }
    if (bus->cpu.irq_pending != 0u && (bus->cpu.status & 0x04u) == 0u) {
        bus->cpu.irq_pending = 0u;
        service_interrupt(bus, 0xFFFEu);
        return (int)(bus->cpu.cycles - start_cyc);
    }
    uint8_t opcode = fetch8(bus);
    if (s_aborted) { return (int)(bus->cpu.cycles - start_cyc); }
    uint8_t op = 0u, mode = 0u;
    nes_cpu_decode_op(opcode, &op, &mode);
    if (op == OP_ILL) {
        cpu_rd(bus, bus->cpu.pc);
    } else if (mode == AM_REL) {
        int8_t off = (int8_t)fetch8(bus);
        if (!s_aborted && nes_cpu_branch_cond(bus, op)) {
            cpu_rd(bus, bus->cpu.pc);
            uint16_t tgt = (uint16_t)(bus->cpu.pc + (uint16_t)(int16_t)off);
            if ((bus->cpu.pc & 0xFF00u) != (tgt & 0xFF00u)) {
                cpu_rd(bus, (uint16_t)((bus->cpu.pc & 0xFF00u) | (tgt & 0x00FFu)));
            }
            if (!s_aborted) { bus->cpu.pc = tgt; }
        }
    } else if (op == OP_JMP || op == OP_JSR || op == OP_RTS || op == OP_RTI || op == OP_BRK ||
               op == OP_PHA || op == OP_PHP || op == OP_PLA || op == OP_PLP) {
        exec_control_or_stack(bus, op, mode);
    } else if (mode == AM_ACC) {
        cpu_rd(bus, bus->cpu.pc);
        if (!s_aborted) { bus->cpu.a = nes_cpu_rmw(bus, op, bus->cpu.a); }
    } else if (mode == AM_IMP) {
        cpu_rd(bus, bus->cpu.pc);
        if (!s_aborted) { nes_cpu_reg_op(bus, op); }
    } else if (op == OP_STA || op == OP_STX || op == OP_STY) {
        uint16_t addr = resolve_addr(bus, mode, 1);
        cpu_wr(bus, addr, (op == OP_STA) ? bus->cpu.a : ((op == OP_STX) ? bus->cpu.x : bus->cpu.y));
    } else if (is_rmw_op(op)) {
        uint16_t addr = resolve_addr(bus, mode, 1);
        uint8_t orig = cpu_rd(bus, addr);
        cpu_wr(bus, addr, orig);
        if (!s_aborted) { cpu_wr(bus, addr, nes_cpu_rmw(bus, op, orig)); }
    } else {
        uint8_t val = (mode == AM_IMM) ? fetch8(bus) : cpu_rd(bus, resolve_addr(bus, mode, 0));
        if (!s_aborted) { nes_cpu_alu(bus, op, val); }
    }
    return (int)(bus->cpu.cycles - start_cyc);
}
