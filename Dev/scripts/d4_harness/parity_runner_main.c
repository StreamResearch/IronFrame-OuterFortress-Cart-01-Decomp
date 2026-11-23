/* @module: IronFrame.D4Harness.ParityRunnerMain */
/* @purpose: Native host parity CLI runner for D4a subsystem checks and D4b --lockstep verification. */
#include <stdio.h>
#include <string.h>

#include "parity_harness.h"

uint16_t d4_rd16(const uint8_t *buf, size_t off) {
    return (uint16_t)buf[off] | ((uint16_t)buf[off + 1u] << 8);
}

int d4_load_prg(const char *dir, const char *file, uint8_t *out, size_t sz) {
    char path[512];
    int n = snprintf(path, sizeof(path), "%s/%s", dir, file);
    if (n < 0 || (size_t)n >= sizeof(path)) {
        return 0;
    }
    FILE *fp = fopen(path, "rb");
    if (!fp) {
        return 0;
    }
    size_t got = fread(out, 1u, sz, fp);
    fclose(fp);
    return got == sz;
}

static void print_json_str(const char *s) {
    putchar('"');
    for (; *s; ++s) {
        if (*s == '"' || *s == '\\') {
            putchar('\\');
        }
        putchar(*s);
    }
    putchar('"');
}

int main(int argc, char **argv) {
    if (argc >= 4 && strcmp(argv[1], "--lockstep") == 0) {
        return d4b_run_lockstep_cli(argv[2], argv[3]);
    }
    if (argc < 2) {
        fprintf(stderr, "usage: %s <extracted_prg_dir> | --lockstep <rom.nes> <out.json>\n", argv[0]);
        return 2;
    }
    const char *dir = argv[1];
    TestResult results[10];
    memset(results, 0, sizeof(results));
    const int total = 10;
    int passed = 0;
    passed += d4_run_rom_and_mapper_tests(dir, &results[0]);
    passed += d4_run_gameplay_and_audio_tests(dir, &results[5]);

    printf("{\"isPassed\":%s,\"assertionsPassedCount\":%d,\"assertionsTotalCount\":%d,\"tests\":[",
           (passed == total) ? "true" : "false", passed, total);
    for (int i = 0; i < total; ++i) {
        printf("%s{\"name\":", (i > 0) ? "," : "");
        print_json_str(results[i].name ? results[i].name : "");
        printf(",\"isPassed\":%s,\"detail\":", results[i].isPassed ? "true" : "false");
        print_json_str(results[i].detail);
        putchar('}');
    }
    printf("]}\n");
    return (passed == total) ? 0 : 1;
}
