#include "audio_devices.h"
#include "bsp/m5stack_tab5.h"
esp_codec_dev_handle_t diagnostic_microphone() {
    static auto handle=bsp_audio_codec_microphone_init();
    return handle;
}
esp_codec_dev_handle_t diagnostic_speaker() {
    static auto handle=bsp_audio_codec_speaker_init();
    return handle;
}
