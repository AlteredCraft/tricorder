#include "network.h"
#include "test_storage.h"
#include "diagnostic_events.h"
#include "bsp/m5stack_tab5.h"
#include "esp_event.h"
#include "esp_hosted_api.h"
#include "esp_http_server.h"
#include "esp_netif.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "nvs_flash.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include <cstdio>
#include <cstring>
#include <atomic>

namespace {
struct Credentials { char ssid[33]; char password[64]; bool initialize_only; };
QueueHandle_t requests;
lv_obj_t *panel, *ssid_field, *password_field, *keyboard, *status;
const char* current_boot;
httpd_handle_t server;
bool initialized;
std::atomic<int> prepare_result{-1};

void show_status(const char* text) {
    if (bsp_display_lock(1000)) {
        lv_label_set_text(status, text);
        bsp_display_unlock();
    }
}

esp_err_t echo(httpd_req_t* request) {
    if (request->content_len != 32) {
        httpd_resp_send_err(request, HTTPD_400_BAD_REQUEST, "Expected 32 hex characters");
        return ESP_OK;
    }
    char nonce[33]{};
    size_t received=0;
    while (received<32) {
        int count = httpd_req_recv(request, nonce+received, 32-received);
        if (count<=0) return ESP_FAIL;
        received += count;
    }
    for (size_t index=0; index<32; ++index) {
        unsigned char c=nonce[index];
        if (!((c>='0' && c<='9') || (c>='a' && c<='f'))) {
            httpd_resp_send_err(request, HTTPD_400_BAD_REQUEST, "Invalid nonce");
            return ESP_OK;
        }
    }
    int64_t now = esp_timer_get_time();
    char response[192];
    snprintf(response, sizeof(response), "{\"nonce\":\"%s\",\"boot_id\":\"%s\",\"device_us\":%lld}",
             nonce, current_boot, static_cast<long long>(now));
    httpd_resp_set_type(request, "application/json");
    auto result = httpd_resp_send(request, response, HTTPD_RESP_USE_STRLEN);
    auto* event = diagnostic_event("network_echo");
    cJSON_AddStringToObject(event, "nonce", nonce);
    cJSON_AddStringToObject(event, "send_result", esp_err_to_name(result));
    cJSON_AddNumberToObject(event, "receive_device_us", now);
    diagnostic_emit(event);
    return result;
}

void wifi_event(void*, esp_event_base_t base, int32_t id, void* data) {
    if (base==WIFI_EVENT && id==WIFI_EVENT_STA_START) {
        auto result = esp_wifi_connect();
        if (result != ESP_OK) show_status("Wi-Fi connect failed; open setup to retry.");
    } else if (base==WIFI_EVENT && id==WIFI_EVENT_STA_DISCONNECTED) {
        auto* disconnected = static_cast<wifi_event_sta_disconnected_t*>(data);
        auto* event = diagnostic_event("wifi_disconnected");
        cJSON_AddNumberToObject(event, "reason", disconnected->reason);
        diagnostic_emit(event);
        if (disconnected->reason==WIFI_REASON_NO_AP_FOUND)
            show_status("Wi-Fi not found. Check the exact name and 2.4 GHz availability.");
        else if (disconnected->reason==WIFI_REASON_AUTH_FAIL
                 || disconnected->reason==WIFI_REASON_HANDSHAKE_TIMEOUT)
            show_status("Wi-Fi authentication failed. Re-enter the password in setup.");
        else show_status("Wi-Fi disconnected; open setup to retry.");
    } else if (base==IP_EVENT && id==IP_EVENT_STA_GOT_IP) {
        auto* address = static_cast<ip_event_got_ip_t*>(data);
        char ip[24], text[96];
        snprintf(ip, sizeof(ip), IPSTR, IP2STR(&address->ip_info.ip));
        snprintf(text, sizeof(text), "Wi-Fi connected: %s / waiting for Mac echo test", ip);
        show_status(text);
        auto* event = diagnostic_event("wifi_address");
        cJSON_AddStringToObject(event, "ipv4", ip);
        diagnostic_emit(event);
        if (!server) {
            httpd_config_t config = HTTPD_DEFAULT_CONFIG();
            config.max_open_sockets = 2;
            config.recv_wait_timeout = 3;
            config.send_wait_timeout = 3;
            config.uri_match_fn = httpd_uri_match_wildcard;
            auto result = httpd_start(&server, &config);
            if (result == ESP_OK) {
                httpd_uri_t route{};
                route.uri = "/echo";
                route.method = HTTP_POST;
                route.handler = echo;
                result = httpd_register_uri_handler(server, &route);
                test_storage_http(server);
            }
            diagnostic_check("wifi_echo_server", result==ESP_OK ? "pass" : "fail",
                             "Listener startup only; host challenge exchange required.");
        }
    }
}

esp_err_t initialize() {
    auto result = esp_hosted_init();
    if (result != ESP_OK) return result;
    // Preserve NVS on error. Diagnostic credentials are never persisted.
    result = nvs_flash_init();
    if (result != ESP_OK) return result;
    if ((result=esp_netif_init()) != ESP_OK) return result;
    if ((result=esp_event_loop_create_default()) != ESP_OK) return result;
    if (!esp_netif_create_default_wifi_sta()) return ESP_FAIL;
    wifi_init_config_t config = WIFI_INIT_CONFIG_DEFAULT();
    if ((result=esp_wifi_init(&config)) != ESP_OK) return result;
    if ((result=esp_wifi_set_storage(WIFI_STORAGE_RAM)) != ESP_OK) return result;
    if ((result=esp_wifi_set_mode(WIFI_MODE_STA)) != ESP_OK) return result;
    if ((result=esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, wifi_event, nullptr)) != ESP_OK) return result;
    if ((result=esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, wifi_event, nullptr)) != ESP_OK) return result;
    esp_hosted_coprocessor_fwver_t version{};
    auto version_result = esp_hosted_get_coprocessor_fwversion(&version);
    auto* event = diagnostic_event("c6_firmware");
    cJSON_AddStringToObject(event, "result", esp_err_to_name(version_result));
    if (version_result==ESP_OK) {
        char value[48];
        snprintf(value, sizeof(value), "%lu.%lu.%lu", static_cast<unsigned long>(version.major1),
                 static_cast<unsigned long>(version.minor1), static_cast<unsigned long>(version.patch1));
        cJSON_AddStringToObject(event, "version", value);
    }
    diagnostic_emit(event);
    return version_result;
}

void network_task(void*) {
    Credentials credentials{};
    bool attempted=false, started=false;
    for (;;) {
        xQueueReceive(requests, &credentials, portMAX_DELAY);
        esp_err_t result=ESP_OK;
        if (!attempted) { attempted=true; result=initialize(); initialized=result==ESP_OK; }
        else if (!initialized) result=ESP_FAIL;
        if (initialized && !credentials.initialize_only) {
            wifi_config_t config{};
            memcpy(config.sta.ssid, credentials.ssid, strlen(credentials.ssid));
            memcpy(config.sta.password, credentials.password, strlen(credentials.password));
            if (started) esp_wifi_disconnect();
            result=esp_wifi_set_config(WIFI_IF_STA, &config);
            // Clear local copies without printing credentials to the serial log.
            volatile unsigned char* clear = reinterpret_cast<volatile unsigned char*>(&config);
            for (size_t i=0; i<sizeof(config); ++i) clear[i]=0;
            if (result==ESP_OK) {
                result=started ? esp_wifi_connect() : esp_wifi_start();
                if (result==ESP_OK) started=true;
            }
        }
        bool initialize_only=credentials.initialize_only;
        if (initialize_only) prepare_result.store(result==ESP_OK ? 0 : 1);
        volatile unsigned char* clear = reinterpret_cast<volatile unsigned char*>(&credentials);
        for (size_t i=0; i<sizeof(credentials); ++i) clear[i]=0;
        if (result!=ESP_OK) show_status("Wi-Fi initialization failed; inspect serial evidence.");
        auto* event = diagnostic_event(initialize_only ? "wifi_initialize_requested" : "wifi_connect_requested");
        cJSON_AddStringToObject(event, "result", esp_err_to_name(result));
        diagnostic_emit(event);
    }
}

void focus(lv_event_t* event) { lv_keyboard_set_textarea(keyboard, static_cast<lv_obj_t*>(lv_event_get_target(event))); }
void open_panel(lv_event_t*) { lv_obj_remove_flag(panel, LV_OBJ_FLAG_HIDDEN); }
void close_panel(lv_event_t*) {
    lv_textarea_set_text(password_field, "");
    lv_obj_add_flag(panel, LV_OBJ_FLAG_HIDDEN);
}
void connect_clicked(lv_event_t*) {
    Credentials credentials{};
    const char* ssid=lv_textarea_get_text(ssid_field);
    const char* password=lv_textarea_get_text(password_field);
    if (!strlen(ssid) || strlen(ssid)>32 || strlen(password)>63) {
        lv_label_set_text(status, "SSID must be 1–32 bytes; password at most 63 bytes.");
        return;
    }
    memcpy(credentials.ssid, ssid, strlen(ssid));
    memcpy(credentials.password, password, strlen(password));
    if (xQueueSend(requests, &credentials, 0)==pdTRUE) {
        lv_label_set_text(status, "Connecting Wi-Fi...");
        close_panel(nullptr);
    }
    volatile unsigned char* clear = reinterpret_cast<volatile unsigned char*>(&credentials);
    for (size_t i=0; i<sizeof(credentials); ++i) clear[i]=0;
}

lv_obj_t* button(lv_obj_t* parent, const char* text, int x, int y, lv_event_cb_t callback) {
    auto* object=lv_button_create(parent);
    lv_obj_set_size(object, 190, 58);
    lv_obj_set_pos(object,x,y);
    lv_obj_add_event_cb(object,callback,LV_EVENT_CLICKED,nullptr);
    auto* label=lv_label_create(object);
    lv_label_set_text(label,text);
    lv_obj_center(label);
    return object;
}
}

void network_ui_open() {
    lv_obj_remove_flag(panel, LV_OBJ_FLAG_HIDDEN);
    lv_obj_move_foreground(panel);
}

bool network_prepare(unsigned timeout_ms) {
    Credentials command{};
    command.initialize_only=true;
    prepare_result.store(-1);
    if (xQueueSend(requests, &command, pdMS_TO_TICKS(100))!=pdTRUE) return false;
    const int64_t deadline=esp_timer_get_time()+static_cast<int64_t>(timeout_ms)*1000;
    while (prepare_result.load()<0 && esp_timer_get_time()<deadline)
        vTaskDelay(pdMS_TO_TICKS(20));
    return prepare_result.load()==0;
}

void network_ui_init(lv_obj_t* screen, const char* boot_id) {
    current_boot=boot_id;
    requests=xQueueCreate(1,sizeof(Credentials));
    configASSERT(requests);
    status=lv_label_create(screen);
    lv_label_set_text(status,"Wi-Fi not connected");
    lv_obj_align(status,LV_ALIGN_TOP_MID,0,20);
    button(screen,"Wi-Fi setup",30,620,open_panel);
    panel=lv_obj_create(screen);
    lv_obj_set_size(panel,1100,580);
    lv_obj_center(panel);
    lv_obj_add_flag(panel,LV_OBJ_FLAG_HIDDEN);
    auto* title=lv_label_create(panel);
    lv_label_set_text(title,"Join a 2.4 GHz network on the Mac's LAN");
    lv_obj_set_pos(title,15,0);
    ssid_field=lv_textarea_create(panel);
    lv_obj_set_pos(ssid_field,15,50); lv_obj_set_size(ssid_field,500,60);
    lv_textarea_set_one_line(ssid_field,true);
    lv_textarea_set_placeholder_text(ssid_field,"Wi-Fi name");
    lv_textarea_set_max_length(ssid_field,32);
    password_field=lv_textarea_create(panel);
    lv_obj_set_pos(password_field,535,50); lv_obj_set_size(password_field,500,60);
    lv_textarea_set_one_line(password_field,true);
    lv_textarea_set_password_mode(password_field,true);
    lv_textarea_set_placeholder_text(password_field,"Password");
    lv_textarea_set_max_length(password_field,63);
    auto* hint=lv_label_create(panel);
    lv_label_set_text(hint,"1# opens symbols; abc returns to letters. Manual entries are temporary; SD settings reload at boot.");
    lv_obj_set_pos(hint,15,114);
    keyboard=lv_keyboard_create(panel);
    lv_obj_set_size(keyboard,1040,300);
    lv_obj_align(keyboard,LV_ALIGN_BOTTOM_MID,0,0);
    lv_keyboard_set_textarea(keyboard,ssid_field);
    lv_obj_add_event_cb(ssid_field,focus,LV_EVENT_FOCUSED,nullptr);
    lv_obj_add_event_cb(password_field,focus,LV_EVENT_FOCUSED,nullptr);
    button(panel,"Connect",15,140,connect_clicked);
    button(panel,"Cancel",225,140,close_panel);
    configASSERT(xTaskCreate(network_task,"network",6144,nullptr,5,nullptr)==pdPASS);
}

bool network_connect_saved(const char* ssid,const char* password) {
    if(!ssid || !password || !strlen(ssid) || strlen(ssid)>32 || strlen(password)>63)return false;
    Credentials credentials{};strcpy(credentials.ssid,ssid);strcpy(credentials.password,password);
    bool ok=xQueueSend(requests,&credentials,0)==pdTRUE;
    volatile unsigned char* p=reinterpret_cast<volatile unsigned char*>(&credentials);
    for(size_t i=0;i<sizeof(credentials);++i)p[i]=0;
    return ok;
}
