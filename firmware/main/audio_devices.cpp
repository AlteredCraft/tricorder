#include "audio_devices.h"
#include "bsp/m5stack_tab5.h"
#include "speaker_route.h"
#include "diagnostic_events.h"
esp_codec_dev_handle_t diagnostic_microphone() {
    static auto handle=bsp_audio_codec_microphone_init();
    return handle;
}
esp_codec_dev_handle_t diagnostic_speaker() {
    static auto handle=bsp_audio_codec_speaker_init();
    return handle;
}
// Headphones in: speaker amp off (speaker_route.h). The media owner calls this
// before and during a spoken reply. PI4IOE1 is on the BSP's I2C bus; the BSP
// writes its output latch only at init. Logs each change of route.
bool route_speaker() {
    constexpr uint8_t input_status=0x0f,output_latch=0x05;
    static i2c_master_dev_handle_t expander=nullptr;
    static int last=-1;
    if(!expander) {
        i2c_device_config_t config{};
        config.dev_addr_length=I2C_ADDR_BIT_LEN_7;config.device_address=0x43;config.scl_speed_hz=400000;
        if(i2c_master_bus_add_device(bsp_i2c_get_handle(),&config,&expander)!=ESP_OK) {expander=nullptr;return false;}
    }
    uint8_t reg=input_status,in=0,out=0;
    if(i2c_master_transmit_receive(expander,&reg,1,&in,1,50)!=ESP_OK)return false;
    reg=output_latch;
    if(i2c_master_transmit_receive(expander,&reg,1,&out,1,50)!=ESP_OK)return false;
    const bool headphones=speaker_route::headphones(in);
    const uint8_t wanted=speaker_route::output_for(out,headphones);
    bool ok=true;
    if(wanted!=out) {
        const uint8_t write[]={output_latch,wanted};
        ok=i2c_master_transmit(expander,write,2,50)==ESP_OK;
    }
    if(last!=headphones || wanted!=out) {
        auto* e=diagnostic_event("speaker_route");
        cJSON_AddBoolToObject(e,"headphones",headphones);cJSON_AddBoolToObject(e,"speaker_amp",!headphones);
        cJSON_AddNumberToObject(e,"input_status",in);cJSON_AddBoolToObject(e,"write_ok",ok);
        diagnostic_emit(e);last=headphones;
    }
    return headphones;
}
