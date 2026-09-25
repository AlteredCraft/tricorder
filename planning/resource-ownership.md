# Resource ownership (G-0001.01 C4)

One owner per resource, from the init code. Audited 2026-09-25 at `e87cb9c`. "Media owner" is the `app_main` task (core 0): every codec, camera, IMU and INA226 user runs on it. The rule was only in comments (`audio_devices.h`, `investigation.cpp`); nothing checks it at run time.

| Resource | Initialized | Owner | Once? |
| --- | --- | --- | --- |
| I2C bus 0 | `diagnostic.cpp` `bsp_i2c_init`; BSP touch/display/codec calls reuse it | BSP handle. Media owner (IMU, INA226, RTC/ID probes, codecs, camera SCCB, IO expanders) and LVGL task (touch); IDF serializes transfers | yes (BSP flag) |
| PI4IOE IO expanders | `diagnostic.cpp` | media owner | yes |
| LEDC timer 0 | BSP display start (`bsp_display_brightness_init`, called twice inside it with identical settings) | backlight | yes, since `bsp_cam_osc_init` was dropped (below) |
| Display, DSI, LVGL task, touch | `diagnostic.cpp` `bsp_display_start_with_config` | LVGL task (core 1); everyone else takes `bsp_display_lock` | yes |
| BMI270 IMU | `diagnostic.cpp` + `imu_checked` | media owner | yes |
| INA226 | `diagnostic.cpp` | media owner | yes |
| RTC / ID probes | `diagnostic.cpp` (device added, read, removed) | media owner | paired |
| SD card + FAT | `diagnostic.cpp` `bsp_sdcard_init` | media owner writes; HTTP and USB-console tasks read/replace under `file_mutex` | yes |
| esp_video registration | `media.cpp` `video_init_once` | media owner | yes |
| CSI / ISP stream | STREAMON/STREAMOFF per `VideoSession` | media owner (diagnostic run, context photo) | paired |
| JPEG encoder + worker | `jpeg_pipeline.cpp` | camera baseline only | paired |
| I2S TX/RX | first codec init (BSP, guarded); RX callback wrap in `audio_ingress.cpp` | media owner | yes |
| ES8388 speaker / ES7210 mic | `audio_devices.cpp` statics | media owner | yes |
| Codec open/close | captures, questions, speech, baselines | media owner, one use at a time | paired, including after a failed open (below) |
| esp_hosted, NVS, netif, event loop, Wi-Fi | `network.cpp` on the network task, guarded | network task | yes |
| HTTP server | `network.cpp` | event-loop task | yes |
| Per-session socket, protocol | `run_investigation` | media owner | paired |
| Context image buffer, `draw_live` and UI-probe timers | `investigation_ui_init` | LVGL (display lock) | yes |

## Found and fixed

- **LEDC timer 0 had two owners.** `bsp_cam_osc_init` set it to 24 MHz for a camera clock on GPIO36, and the BSP backlight setup then reset it to 5 kHz. Boot logs `ledc_timer0` = 5000 Hz, and the camera has always worked at that, so the call is dropped (`f97f7b4`). Context photos in the driven runs confirm the camera still works.
- **A failed codec open could leave the device marked open.** `esp_codec_dev_open` sets its opened flag before configuring the device, and a later open of a marked device returns OK without configuring it. Captures and `speak()` now close whenever the device exists (`e930f89`). This is found by reading the code, not reproduced.

## Not determined

Whether esp_lvgl_port's `sw_rotate` (PPA) competes with the JPEG encoder's DMA2D channels. The JPEG pipeline runs only in the camera diagnostic, never in a session.
