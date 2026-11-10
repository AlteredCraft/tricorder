#include "network.h"
#include "test_storage.h"
#include "setup.h"
#include "service_wire.h"
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
std::atomic<uint32_t> station_ipv4{0}; // own address, 0 while down; read by the start screen
// Hotspot mode: the last joined device's lease, and the MAC it was given to.
std::atomic<uint32_t> peer_ipv4{0};
std::atomic<bool> hotspot{false};
portMUX_TYPE name_lock=portMUX_INITIALIZER_UNLOCKED;
char hotspot_name[33]; // name_lock
uint8_t peer_mac[6]; // event loop task only
portMUX_TYPE known_lock=portMUX_INITIALIZER_UNLOCKED;
StorageNetwork known[storage_known_max]; int known_count; // known_lock
StorageNetwork saved_hotspot; // known_lock; empty ssid until hotspot mode was provisioned
lv_obj_t *known_buttons[storage_known_max], *hotspot_button; // LVGL task only
esp_netif_t* ap_netif;
struct Credentials { char ssid[33]; char password[64]; bool initialize_only; bool access_point; };
QueueHandle_t requests;
lv_obj_t *panel, *ssid_field, *password_field, *keyboard, *status, *hint;
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

void start_server() {
    if (server) return;
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

void address_event(const char* mode, uint32_t ipv4) {
    char ip[24];
    snprintf(ip, sizeof(ip), IPSTR, IP2STR(reinterpret_cast<const esp_ip4_addr_t*>(&ipv4)));
    auto* event = diagnostic_event("wifi_address");
    cJSON_AddStringToObject(event, "ipv4", ip);
    cJSON_AddStringToObject(event, "mode", mode);
    diagnostic_emit(event);
}

// The Mac joined the hotspot: its lease is where the service listens, on the configured port.
void peer_assigned(const ip_event_ap_staipassigned_t& assigned) {
    peer_ipv4.store(assigned.ip.addr);
    memcpy(peer_mac, assigned.mac, sizeof(peer_mac));
    ServiceEndpoint configured;
    const int port = configured.parse(CONFIG_TRICORDER_INVESTIGATION_ENDPOINT) ? configured.port : 8765;
    char ip[24], endpoint[64], text[128];
    snprintf(ip, sizeof(ip), IPSTR, IP2STR(&assigned.ip));
    snprintf(endpoint, sizeof(endpoint), "ws://%s:%d/", ip, port);
    setup_set_endpoint(endpoint, EndpointSource::Hotspot);
    snprintf(text, sizeof(text), "Mac joined the hotspot: %s / service %s", ip, endpoint);
    show_status(text);
    auto* event = diagnostic_event("wifi_ap_client");
    cJSON_AddStringToObject(event, "ipv4", ip);
    cJSON_AddStringToObject(event, "endpoint", endpoint);
    diagnostic_emit(event);
}

void wifi_event(void*, esp_event_base_t base, int32_t id, void* data) {
    if (base==WIFI_EVENT && id==WIFI_EVENT_STA_START) {
        if (hotspot.load()) return;
        auto result = esp_wifi_connect();
        if (result != ESP_OK) show_status("Wi-Fi connect failed; open setup to retry.");
    } else if (base==WIFI_EVENT && id==WIFI_EVENT_AP_START) {
        esp_netif_ip_info_t info{};
        if (ap_netif && esp_netif_get_ip_info(ap_netif, &info)==ESP_OK) station_ipv4.store(info.ip.addr);
        peer_ipv4.store(0);
        show_status("Hotspot on. Join it from the Mac, then start the service.");
        address_event("ap", station_ipv4.load());
        start_server();
    } else if (base==WIFI_EVENT && id==WIFI_EVENT_AP_STOP) {
        station_ipv4.store(0);
        peer_ipv4.store(0);
    } else if (base==WIFI_EVENT && id==WIFI_EVENT_AP_STACONNECTED) {
        auto* joined = static_cast<wifi_event_ap_staconnected_t*>(data);
        auto* event = diagnostic_event("wifi_ap_station");
        cJSON_AddStringToObject(event, "state", "joined");
        cJSON_AddNumberToObject(event, "aid", joined->aid);
        diagnostic_emit(event);
    } else if (base==WIFI_EVENT && id==WIFI_EVENT_AP_STADISCONNECTED) {
        auto* left = static_cast<wifi_event_ap_stadisconnected_t*>(data);
        const bool was_peer = peer_ipv4.load() && !memcmp(left->mac, peer_mac, sizeof(peer_mac));
        if (was_peer) { peer_ipv4.store(0); show_status("The Mac left the hotspot."); }
        auto* event = diagnostic_event("wifi_ap_station");
        cJSON_AddStringToObject(event, "state", "left");
        cJSON_AddNumberToObject(event, "aid", left->aid);
        cJSON_AddNumberToObject(event, "reason", left->reason);
        cJSON_AddBoolToObject(event, "was_service_peer", was_peer);
        diagnostic_emit(event);
    } else if (base==IP_EVENT && id==IP_EVENT_AP_STAIPASSIGNED) {
        peer_assigned(*static_cast<ip_event_ap_staipassigned_t*>(data));
    } else if (base==WIFI_EVENT && id==WIFI_EVENT_STA_DISCONNECTED) {
        // Going back to the hotspot disconnects the station; that is not a lost network.
        if (hotspot.load()) return;
        station_ipv4.store(0);
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
        station_ipv4.store(address->ip_info.ip.addr);
        char ip[24], text[96];
        snprintf(ip, sizeof(ip), IPSTR, IP2STR(&address->ip_info.ip));
        snprintf(text, sizeof(text), "Wi-Fi connected: %s / waiting for Mac echo test", ip);
        show_status(text);
        address_event("station", address->ip_info.ip.addr);
        start_server();
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
    if (!(ap_netif=esp_netif_create_default_wifi_ap())) return ESP_FAIL;
    wifi_init_config_t config = WIFI_INIT_CONFIG_DEFAULT();
    if ((result=esp_wifi_init(&config)) != ESP_OK) return result;
    if ((result=esp_wifi_set_storage(WIFI_STORAGE_RAM)) != ESP_OK) return result;
    if ((result=esp_wifi_set_mode(WIFI_MODE_STA)) != ESP_OK) return result;
    if ((result=esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, wifi_event, nullptr)) != ESP_OK) return result;
    if ((result=esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, wifi_event, nullptr)) != ESP_OK) return result;
    if ((result=esp_event_handler_register(IP_EVENT, IP_EVENT_AP_STAIPASSIGNED, wifi_event, nullptr)) != ESP_OK) return result;
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
        if (initialized && !credentials.initialize_only && credentials.access_point) {
            wifi_config_t config{};
            memcpy(config.ap.ssid, credentials.ssid, strlen(credentials.ssid));
            config.ap.ssid_len = strlen(credentials.ssid);
            memcpy(config.ap.password, credentials.password, strlen(credentials.password));
            config.ap.authmode = WIFI_AUTH_WPA2_PSK;
            config.ap.max_connection = 4;
            config.ap.channel = 1;
            if (started && !hotspot.load()) esp_wifi_disconnect();
            station_ipv4.store(0); peer_ipv4.store(0);
            portENTER_CRITICAL(&name_lock);
            strlcpy(hotspot_name, credentials.ssid, sizeof(hotspot_name));
            portEXIT_CRITICAL(&name_lock);
            hotspot.store(true);
            result=esp_wifi_set_mode(WIFI_MODE_AP);
            if (result==ESP_OK) result=esp_wifi_set_config(WIFI_IF_AP, &config);
            volatile unsigned char* clear = reinterpret_cast<volatile unsigned char*>(&config);
            for (size_t i=0; i<sizeof(config); ++i) clear[i]=0;
            if (result==ESP_OK && !started) { result=esp_wifi_start(); if (result==ESP_OK) started=true; }
        } else if (initialized && !credentials.initialize_only) {
            wifi_config_t config{};
            memcpy(config.sta.ssid, credentials.ssid, strlen(credentials.ssid));
            memcpy(config.sta.password, credentials.password, strlen(credentials.password));
            if (started && !hotspot.load()) esp_wifi_disconnect();
            // Leaving hotspot mode (manual Wi-Fi setup): the mode change posts STA_START, which connects.
            const bool from_hotspot = hotspot.exchange(false);
            if (from_hotspot) { station_ipv4.store(0); peer_ipv4.store(0); }
            result=esp_wifi_set_mode(WIFI_MODE_STA);
            if (result==ESP_OK) result=esp_wifi_set_config(WIFI_IF_STA, &config);
            // Clear local copies without printing credentials to the serial log.
            volatile unsigned char* clear = reinterpret_cast<volatile unsigned char*>(&config);
            for (size_t i=0; i<sizeof(config); ++i) clear[i]=0;
            if (result==ESP_OK) {
                result=!started ? esp_wifi_start() : from_hotspot ? ESP_OK : esp_wifi_connect();
                if (result==ESP_OK) started=true;
            }
        }
        bool initialize_only=credentials.initialize_only, access_point=credentials.access_point;
        if (initialize_only) prepare_result.store(result==ESP_OK ? 0 : 1);
        volatile unsigned char* clear = reinterpret_cast<volatile unsigned char*>(&credentials);
        for (size_t i=0; i<sizeof(credentials); ++i) clear[i]=0;
        if (result!=ESP_OK) show_status("Wi-Fi initialization failed; inspect serial evidence.");
        auto* event = diagnostic_event(initialize_only ? "wifi_initialize_requested" :
                                       access_point ? "wifi_access_point_requested" : "wifi_connect_requested");
        cJSON_AddStringToObject(event, "result", esp_err_to_name(result));
        diagnostic_emit(event);
    }
}

void focus(lv_event_t* event) { lv_keyboard_set_textarea(keyboard, static_cast<lv_obj_t*>(lv_event_get_target(event))); }
constexpr const char* hint_text="Tap a saved network to join it, or type one. Lasts until restart; SD settings reload at boot.";
void open_panel(lv_event_t*) { network_ui_open(); }
void close_panel(lv_event_t*) {
    lv_textarea_set_text(password_field, "");
    lv_obj_add_flag(panel, LV_OBJ_FLAG_HIDDEN);
}
void request(Credentials& credentials, const char* progress) {
    if (xQueueSend(requests, &credentials, 0)==pdTRUE) {
        lv_label_set_text(status, progress);
        close_panel(nullptr);
    }
    volatile unsigned char* clear = reinterpret_cast<volatile unsigned char*>(&credentials);
    for (size_t i=0; i<sizeof(credentials); ++i) clear[i]=0;
}
void connect_clicked(lv_event_t*) {
    const char* ssid=lv_textarea_get_text(ssid_field);
    const char* password=lv_textarea_get_text(password_field);
    if (!strlen(ssid) || strlen(ssid)>32 || strlen(password)>63) {
        lv_label_set_text(status, "SSID must be 1–32 bytes; password at most 63 bytes.");
        lv_label_set_text(hint, "Wi-Fi name: 1 to 32 characters. Password: at most 63.");
        return;
    }
    Credentials credentials{};
    memcpy(credentials.ssid, ssid, strlen(ssid));
    memcpy(credentials.password, password, strlen(password));
    request(credentials, "Connecting Wi-Fi...");
}

void known_clicked(lv_event_t* event) {
    const auto index = static_cast<int>(reinterpret_cast<intptr_t>(lv_event_get_user_data(event)));
    Credentials credentials{};
    portENTER_CRITICAL(&known_lock);
    const bool found = index<known_count;
    if (found) {
        strlcpy(credentials.ssid, known[index].ssid, sizeof(credentials.ssid));
        strlcpy(credentials.password, known[index].password, sizeof(credentials.password));
    }
    portEXIT_CRITICAL(&known_lock);
    if (found) request(credentials, "Connecting Wi-Fi...");
}
void hotspot_clicked(lv_event_t*) {
    Credentials credentials{};
    portENTER_CRITICAL(&known_lock);
    strlcpy(credentials.ssid, saved_hotspot.ssid, sizeof(credentials.ssid));
    strlcpy(credentials.password, saved_hotspot.password, sizeof(credentials.password));
    portEXIT_CRITICAL(&known_lock);
    credentials.access_point = true;
    if (credentials.ssid[0]) request(credentials, "Starting the hotspot...");
}
lv_obj_t* saved_button(int slot, lv_event_cb_t callback) {
    auto* object=lv_button_create(panel);
    lv_obj_set_size(object, 236, 58);
    lv_obj_set_pos(object, 24+slot*249, 184);
    lv_obj_add_event_cb(object, callback, LV_EVENT_CLICKED, reinterpret_cast<void*>(static_cast<intptr_t>(slot)));
    auto* label=lv_label_create(object);
    lv_obj_set_width(label, 212);
    lv_label_set_long_mode(label, LV_LABEL_LONG_DOT);
    lv_obj_set_style_text_align(label, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_center(label);
    lv_obj_add_flag(object, LV_OBJ_FLAG_HIDDEN);
    return object;
}
void show_saved(lv_obj_t* object, const char* text, bool visible) {
    if (visible) { lv_label_set_text(lv_obj_get_child(object, 0), text); lv_obj_remove_flag(object, LV_OBJ_FLAG_HIDDEN); }
    else lv_obj_add_flag(object, LV_OBJ_FLAG_HIDDEN);
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
lv_obj_t* dialog_button(const char* text, int x, int width, lv_event_cb_t callback) {
    auto* object=button(panel, text, x, 14, callback);
    lv_obj_set_size(object, width, 64);
    lv_obj_set_style_text_font(lv_obj_get_child(object, 0), &lv_font_montserrat_28, 0);
    return object;
}
lv_obj_t* dialog_field(int x, const char* placeholder, unsigned max_length) {
    auto* field=lv_textarea_create(panel);
    lv_obj_set_pos(field, x, 100); lv_obj_set_size(field, 608, 72);
    lv_obj_set_style_text_font(field, &lv_font_montserrat_28, 0);
    lv_textarea_set_one_line(field, true);
    lv_textarea_set_placeholder_text(field, placeholder);
    lv_textarea_set_max_length(field, max_length);
    lv_obj_add_event_cb(field, focus, LV_EVENT_FOCUSED, nullptr);
    return field;
}
}

void network_ui_open() {
    lv_label_set_text(hint, hint_text);
    char names[storage_known_max][33]{};
    portENTER_CRITICAL(&known_lock);
    const int count = known_count;
    for (int i=0; i<count; ++i) strlcpy(names[i], known[i].ssid, sizeof(names[i]));
    const bool can_return = saved_hotspot.ssid[0];
    portEXIT_CRITICAL(&known_lock);
    // iPhone hotspot names use a curly apostrophe, which the built-in font lacks.
    for (int i=0; i<count; ++i)
        for (char* curly; (curly=strstr(names[i], "\xE2\x80\x99")); ) { *curly='\''; memmove(curly+1, curly+3, strlen(curly+3)+1); }
    for (int i=0; i<storage_known_max; ++i) show_saved(known_buttons[i], names[i], i<count);
    show_saved(hotspot_button, "Back to hotspot", can_return && !hotspot.load());
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
    // Full screen and opaque, so the Setup screen underneath does not show at the edges.
    panel=lv_obj_create(screen);
    lv_obj_remove_style_all(panel);
    lv_obj_set_size(panel,1280,720); lv_obj_set_pos(panel,0,0);
    lv_obj_set_style_bg_color(panel,lv_color_hex(0x101418),0);
    lv_obj_set_style_bg_opa(panel,LV_OPA_COVER,0);
    lv_obj_remove_flag(panel,LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(panel,LV_OBJ_FLAG_HIDDEN);
    auto* title=lv_label_create(panel);
    lv_label_set_text(title,"Join a 2.4 GHz network on the Mac's LAN");
    lv_obj_set_style_text_font(title,&lv_font_montserrat_32,0);
    lv_obj_set_style_text_color(title,lv_color_hex(0xffffff),0);
    lv_obj_set_pos(title,24,26);
    dialog_button("Connect",842,220,connect_clicked);
    dialog_button("Cancel",1076,180,close_panel);
    ssid_field=dialog_field(24,"Wi-Fi name",32);
    password_field=dialog_field(648,"Password",63);
    lv_textarea_set_password_mode(password_field,true);
    hint=lv_label_create(panel);
    lv_label_set_text(hint,hint_text);
    lv_obj_set_style_text_font(hint,&lv_font_montserrat_22,0);
    lv_obj_set_style_text_color(hint,lv_color_hex(0x90a4ae),0);
    lv_obj_set_pos(hint,24,252);
    for (int i=0; i<storage_known_max; ++i) known_buttons[i]=saved_button(i, known_clicked);
    hotspot_button=saved_button(storage_known_max, hotspot_clicked);
    keyboard=lv_keyboard_create(panel);
    lv_obj_set_size(keyboard,1232,424); lv_obj_align(keyboard,LV_ALIGN_TOP_LEFT,24,288);
    lv_obj_set_style_text_font(keyboard,&lv_font_montserrat_28,LV_PART_ITEMS);
    lv_keyboard_set_textarea(keyboard,ssid_field);
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

bool network_start_access_point(const char* ssid,const char* password) {
    if(!ssid || !password || !strlen(ssid) || strlen(ssid)>32 || strlen(password)<8 || strlen(password)>63)return false;
    Credentials credentials{};strcpy(credentials.ssid,ssid);strcpy(credentials.password,password);credentials.access_point=true;
    portENTER_CRITICAL(&known_lock);
    strlcpy(saved_hotspot.ssid,ssid,sizeof(saved_hotspot.ssid));strlcpy(saved_hotspot.password,password,sizeof(saved_hotspot.password));
    portEXIT_CRITICAL(&known_lock);
    bool ok=xQueueSend(requests,&credentials,0)==pdTRUE;
    volatile unsigned char* p=reinterpret_cast<volatile unsigned char*>(&credentials);
    for(size_t i=0;i<sizeof(credentials);++i)p[i]=0;
    return ok;
}

uint32_t network_ipv4() {return station_ipv4.load();}
uint32_t network_peer_ipv4() {return peer_ipv4.load();}
bool network_access_point() {return hotspot.load();}
bool network_hotspot_saved() {
    portENTER_CRITICAL(&known_lock);const bool saved=saved_hotspot.ssid[0];portEXIT_CRITICAL(&known_lock);
    return saved;
}
void network_set_known(const StorageNetwork* networks,int count) {
    portENTER_CRITICAL(&known_lock);
    known_count=count<storage_known_max?count:storage_known_max;
    for(int i=0;i<known_count;++i)known[i]=networks[i];
    portEXIT_CRITICAL(&known_lock);
}
void network_access_point_name(char* out,size_t size) {
    portENTER_CRITICAL(&name_lock);strlcpy(out,hotspot_name,size);portEXIT_CRITICAL(&name_lock);
}
