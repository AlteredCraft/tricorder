#pragma once
#include "driver/jpeg_encode.h"

// Single diagnostic encoder owner. Driver error paths that cannot establish
// DMA quiescence terminate before stack descriptors or source buffers expire.
esp_err_t jpeg_encode_guarded(jpeg_encoder_handle_t engine,const jpeg_encode_cfg_t* config,
                              const uint8_t* source,uint32_t source_bytes,uint8_t* output,
                              uint32_t output_capacity,uint32_t* output_bytes);
