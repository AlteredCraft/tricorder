#pragma once
#include <cstdint>
// Tab5 IO expander PI4IOE1 (0x43): P1 enables the speaker amplifier (the BSP's
// ES8388 config has pa_pin -1, "PI4IOE1 P1"), and P7 reads high with headphones
// in (bsp_headphone_detect). The codec drives both outputs, so headphones alone
// don't silence the speaker; the amp is switched off instead.
namespace speaker_route {
constexpr uint8_t amp_bit=1u<<1,headphone_bit=1u<<7;
inline bool headphones(uint8_t input_status) {return input_status&headphone_bit;}
// Only P1 changes; the other latched pins (5 V out, resets) keep their state.
inline uint8_t output_for(uint8_t output_latch,bool headphones) {
    return headphones ? static_cast<uint8_t>(output_latch&~amp_bit) : static_cast<uint8_t>(output_latch|amp_bit);
}
}
