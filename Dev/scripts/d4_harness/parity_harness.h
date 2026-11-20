#ifndef D4_PARITY_HARNESS_H
#define D4_PARITY_HARNESS_H

#include <stddef.h>
#include <stdint.h>

#define PRG_BANK_SIZE 32768u

typedef struct {
    const char *name;
    int isPassed;
    char detail[192];
} TestResult;

uint16_t d4_rd16(const uint8_t *buf, size_t off);
int d4_load_prg(const char *dir, const char *file, uint8_t *out, size_t sz);
int d4_run_rom_and_mapper_tests(const char *dir, TestResult *results);
int d4_run_gameplay_and_audio_tests(const char *dir, TestResult *results);

#endif
