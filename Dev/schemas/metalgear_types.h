#pragma once

/*
 * NES-ME-USA (UNROM Mapper 2) -- Umbrella Type Schema Header
 *
 * Target ABI: MOS 6502 (pointer_bytes = 2, 16-bit little-endian addresses).
 * Aggregates all four domain type headers for Stage D2/D3 schema validation.
 */

#include "ghidra_compat.h"
#include "types/nes_hardware.h"
#include "types/mg_player.h"
#include "types/mg_world.h"
#include "types/mg_audio.h"
