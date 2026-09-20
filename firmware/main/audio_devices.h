#pragma once
#include "esp_codec_dev.h"
// Shared codec handles, used only by the diagnostic's sequential media owner.
esp_codec_dev_handle_t diagnostic_microphone();
esp_codec_dev_handle_t diagnostic_speaker();
void run_audio_baseline(const char* boot_id);
