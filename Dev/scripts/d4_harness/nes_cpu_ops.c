/* @module: IronFrame.D4Harness.NesCpuOps */
/* @purpose: Clean-room 56-mnemonic/151-opcode RP2A03 6502 decoder tables and ALU/RMW/flag operations. */
#include "nes_bus.h"

enum {
    OP_ILL = 0, OP_ADC = 1, OP_AND = 2, OP_ASL = 3, OP_BCC = 4, OP_BCS = 5, OP_BEQ = 6, OP_BIT = 7,
    OP_BMI = 8, OP_BNE = 9, OP_BPL = 10, OP_BRK = 11, OP_BVC = 12, OP_BVS = 13, OP_CLC = 14, OP_CLD = 15,
    OP_CLI = 16, OP_CLV = 17, OP_CMP = 18, OP_CPX = 19, OP_CPY = 20, OP_DEC = 21, OP_DEX = 22, OP_DEY = 23,
    OP_EOR = 24, OP_INC = 25, OP_INX = 26, OP_INY = 27, OP_JMP = 28, OP_JSR = 29, OP_LDA = 30, OP_LDX = 31,
    OP_LDY = 32, OP_LSR = 33, OP_NOP = 34, OP_ORA = 35, OP_PHA = 36, OP_PHP = 37, OP_PLA = 38, OP_PLP = 39,
    OP_ROL = 40, OP_ROR = 41, OP_RTI = 42, OP_RTS = 43, OP_SBC = 44, OP_SEC = 45, OP_SED = 46, OP_SEI = 47,
    OP_STA = 48, OP_STX = 49, OP_STY = 50, OP_TAX = 51, OP_TAY = 52, OP_TSX = 53, OP_TXA = 54, OP_TXS = 55,
    OP_TYA = 56
};

static const uint8_t k_op[256] = {
    11, 35,  0,  0,  0, 35,  3,  0, 37, 35,  3,  0,  0, 35,  3,  0,
    10, 35,  0,  0,  0, 35,  3,  0, 14, 35,  0,  0,  0, 35,  3,  0,
    29,  2,  0,  0,  7,  2, 40,  0, 39,  2, 40,  0,  7,  2, 40,  0,
     8,  2,  0,  0,  0,  2, 40,  0, 45,  2,  0,  0,  0,  2, 40,  0,
    42, 24,  0,  0,  0, 24, 33,  0, 36, 24, 33,  0, 28, 24, 33,  0,
    12, 24,  0,  0,  0, 24, 33,  0, 16, 24,  0,  0,  0, 24, 33,  0,
    43,  1,  0,  0,  0,  1, 41,  0, 38,  1, 41,  0, 28,  1, 41,  0,
    13,  1,  0,  0,  0,  1, 41,  0, 47,  1,  0,  0,  0,  1, 41,  0,
     0, 48,  0,  0, 50, 48, 49,  0, 23,  0, 54,  0, 50, 48, 49,  0,
     4, 48,  0,  0, 50, 48, 49,  0, 56, 48, 55,  0,  0, 48,  0,  0,
    32, 30, 31,  0, 32, 30, 31,  0, 52, 30, 51,  0, 32, 30, 31,  0,
     5, 30,  0,  0, 32, 30, 31,  0, 17, 30, 53,  0, 32, 30, 31,  0,
    20, 18,  0,  0, 20, 18, 21,  0, 27, 18, 22,  0, 20, 18, 21,  0,
     9, 18,  0,  0,  0, 18, 21,  0, 15, 18,  0,  0,  0, 18, 21,  0,
    19, 44,  0,  0, 19, 44, 25,  0, 26, 44, 34,  0, 19, 44, 25,  0,
     6, 44,  0,  0,  0, 44, 25,  0, 46, 44,  0,  0,  0, 44, 25,  0
};

static const uint8_t k_am[256] = {
     0, 10,  0,  0,  0,  3,  3,  0,  0,  2,  1,  0,  0,  6,  6,  0,
    12, 11,  0,  0,  0,  4,  4,  0,  0,  8,  0,  0,  0,  7,  7,  0,
     6, 10,  0,  0,  3,  3,  3,  0,  0,  2,  1,  0,  6,  6,  6,  0,
    12, 11,  0,  0,  0,  4,  4,  0,  0,  8,  0,  0,  0,  7,  7,  0,
     0, 10,  0,  0,  0,  3,  3,  0,  0,  2,  1,  0,  6,  6,  6,  0,
    12, 11,  0,  0,  0,  4,  4,  0,  0,  8,  0,  0,  0,  7,  7,  0,
     0, 10,  0,  0,  0,  3,  3,  0,  0,  2,  1,  0,  9,  6,  6,  0,
    12, 11,  0,  0,  0,  4,  4,  0,  0,  8,  0,  0,  0,  7,  7,  0,
     0, 10,  0,  0,  3,  3,  3,  0,  0,  0,  0,  0,  6,  6,  6,  0,
    12, 11,  0,  0,  4,  4,  5,  0,  0,  8,  0,  0,  0,  7,  0,  0,
     2, 10,  2,  0,  3,  3,  3,  0,  0,  2,  0,  0,  6,  6,  6,  0,
    12, 11,  0,  0,  4,  4,  5,  0,  0,  8,  0,  0,  7,  7,  8,  0,
     2, 10,  0,  0,  3,  3,  3,  0,  0,  2,  0,  0,  6,  6,  6,  0,
    12, 11,  0,  0,  0,  4,  4,  0,  0,  8,  0,  0,  0,  7,  7,  0,
     2, 10,  0,  0,  3,  3,  3,  0,  0,  2,  0,  0,  6,  6,  6,  0,
    12, 11,  0,  0,  0,  4,  4,  0,  0,  8,  0,  0,  0,  7,  7,  0
};

void nes_cpu_decode_op(uint8_t opcode, uint8_t *out_op, uint8_t *out_mode);
uint8_t nes_cpu_zn(NesBus *bus, uint8_t v);
void nes_cpu_alu(NesBus *bus, uint8_t op, uint8_t val);
uint8_t nes_cpu_rmw(NesBus *bus, uint8_t op, uint8_t val);
int nes_cpu_branch_cond(const NesBus *bus, uint8_t op);
void nes_cpu_reg_op(NesBus *bus, uint8_t op);

void nes_cpu_decode_op(uint8_t opcode, uint8_t *out_op, uint8_t *out_mode) {
    *out_op = k_op[opcode];
    *out_mode = k_am[opcode];
}

uint8_t nes_cpu_zn(NesBus *bus, uint8_t v) {
    uint8_t st = (uint8_t)(bus->cpu.status & ~0x82u);
    if (v == 0u) {
        st |= 0x02u;
    }
    if ((v & 0x80u) != 0u) {
        st |= 0x80u;
    }
    bus->cpu.status = st;
    return v;
}

static void set_flag(NesBus *bus, uint8_t mask, int on) {
    if (on) {
        bus->cpu.status |= mask;
    } else {
        bus->cpu.status &= (uint8_t)~mask;
    }
}

void nes_cpu_alu(NesBus *bus, uint8_t op, uint8_t val) {
    if (op == OP_LDA) {
        bus->cpu.a = nes_cpu_zn(bus, val);
    } else if (op == OP_LDX) {
        bus->cpu.x = nes_cpu_zn(bus, val);
    } else if (op == OP_LDY) {
        bus->cpu.y = nes_cpu_zn(bus, val);
    } else if (op == OP_ORA) {
        bus->cpu.a = nes_cpu_zn(bus, (uint8_t)(bus->cpu.a | val));
    } else if (op == OP_AND) {
        bus->cpu.a = nes_cpu_zn(bus, (uint8_t)(bus->cpu.a & val));
    } else if (op == OP_EOR) {
        bus->cpu.a = nes_cpu_zn(bus, (uint8_t)(bus->cpu.a ^ val));
    } else if (op == OP_BIT) {
        set_flag(bus, 0x02u, (bus->cpu.a & val) == 0u);
        set_flag(bus, 0x40u, (val & 0x40u) != 0u);
        set_flag(bus, 0x80u, (val & 0x80u) != 0u);
    } else if (op == OP_ADC || op == OP_SBC) {
        /* RP2A03 omits BCD decimal mode: ADC and SBC always compute binary arithmetic. */
        uint8_t rhs = (op == OP_SBC) ? (uint8_t)~val : val;
        uint16_t sum = (uint16_t)bus->cpu.a + (uint16_t)rhs + (uint16_t)(bus->cpu.status & 1u);
        set_flag(bus, 0x01u, sum > 0xFFu);
        set_flag(bus, 0x40u, ((~(bus->cpu.a ^ rhs) & (bus->cpu.a ^ sum)) & 0x80u) != 0u);
        bus->cpu.a = nes_cpu_zn(bus, (uint8_t)sum);
    } else {
        uint8_t lhs = (op == OP_CPX) ? bus->cpu.x : ((op == OP_CPY) ? bus->cpu.y : bus->cpu.a);
        set_flag(bus, 0x01u, lhs >= val);
        nes_cpu_zn(bus, (uint8_t)(lhs - val));
    }
}

uint8_t nes_cpu_rmw(NesBus *bus, uint8_t op, uint8_t val) {
    if (op == OP_ASL) {
        set_flag(bus, 0x01u, (val & 0x80u) != 0u);
        return nes_cpu_zn(bus, (uint8_t)(val << 1));
    }
    if (op == OP_LSR) {
        set_flag(bus, 0x01u, (val & 0x01u) != 0u);
        return nes_cpu_zn(bus, (uint8_t)(val >> 1));
    }
    if (op == OP_ROL) {
        uint8_t cin = (uint8_t)(bus->cpu.status & 0x01u);
        set_flag(bus, 0x01u, (val & 0x80u) != 0u);
        return nes_cpu_zn(bus, (uint8_t)((val << 1) | cin));
    }
    if (op == OP_ROR) {
        uint8_t cin = (uint8_t)((bus->cpu.status & 0x01u) << 7);
        set_flag(bus, 0x01u, (val & 0x01u) != 0u);
        return nes_cpu_zn(bus, (uint8_t)((val >> 1) | cin));
    }
    if (op == OP_INC) {
        return nes_cpu_zn(bus, (uint8_t)(val + 1u));
    }
    return nes_cpu_zn(bus, (uint8_t)(val - 1u));
}

int nes_cpu_branch_cond(const NesBus *bus, uint8_t op) {
    uint8_t s = bus->cpu.status;
    if (op == OP_BCC) { return (s & 0x01u) == 0u; }
    if (op == OP_BCS) { return (s & 0x01u) != 0u; }
    if (op == OP_BEQ) { return (s & 0x02u) != 0u; }
    if (op == OP_BNE) { return (s & 0x02u) == 0u; }
    if (op == OP_BMI) { return (s & 0x80u) != 0u; }
    if (op == OP_BPL) { return (s & 0x80u) == 0u; }
    if (op == OP_BVS) { return (s & 0x40u) != 0u; }
    return (s & 0x40u) == 0u;
}

void nes_cpu_reg_op(NesBus *bus, uint8_t op) {
    if (op == OP_TAX) { bus->cpu.x = nes_cpu_zn(bus, bus->cpu.a); }
    else if (op == OP_TAY) { bus->cpu.y = nes_cpu_zn(bus, bus->cpu.a); }
    else if (op == OP_TXA) { bus->cpu.a = nes_cpu_zn(bus, bus->cpu.x); }
    else if (op == OP_TYA) { bus->cpu.a = nes_cpu_zn(bus, bus->cpu.y); }
    else if (op == OP_TSX) { bus->cpu.x = nes_cpu_zn(bus, bus->cpu.sp); }
    else if (op == OP_TXS) { bus->cpu.sp = bus->cpu.x; }
    else if (op == OP_DEX) { bus->cpu.x = nes_cpu_zn(bus, (uint8_t)(bus->cpu.x - 1u)); }
    else if (op == OP_DEY) { bus->cpu.y = nes_cpu_zn(bus, (uint8_t)(bus->cpu.y - 1u)); }
    else if (op == OP_INX) { bus->cpu.x = nes_cpu_zn(bus, (uint8_t)(bus->cpu.x + 1u)); }
    else if (op == OP_INY) { bus->cpu.y = nes_cpu_zn(bus, (uint8_t)(bus->cpu.y + 1u)); }
    else if (op == OP_CLC) { set_flag(bus, 0x01u, 0); }
    else if (op == OP_SEC) { set_flag(bus, 0x01u, 1); }
    else if (op == OP_CLI) { set_flag(bus, 0x04u, 0); }
    else if (op == OP_SEI) { set_flag(bus, 0x04u, 1); }
    else if (op == OP_CLV) { set_flag(bus, 0x40u, 0); }
    else if (op == OP_CLD) { set_flag(bus, 0x08u, 0); }
    else if (op == OP_SED) { set_flag(bus, 0x08u, 1); }
}
