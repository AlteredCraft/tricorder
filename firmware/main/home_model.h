#pragma once
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdio>
// Start screen (F-0001): tile geometry and tile reading text, host-testable.
namespace home {
struct Rect {int x,y,w,h;};
constexpr int screen_w=1280,screen_h=720,columns=3,rows=2,margin=24,gap=16,header=84;
constexpr unsigned tile_count=columns*rows;
constexpr int tile_w=(screen_w-2*margin-(columns-1)*gap)/columns;
constexpr int tile_h=(screen_h-header-margin-(rows-1)*gap)/rows;
inline Rect tile(unsigned index) {
    return {margin+static_cast<int>(index%columns)*(tile_w+gap),header+static_cast<int>(index/columns)*(tile_h+gap),tile_w,tile_h};
}
// Degrees from lying flat (screen up or down), from raw accelerometer axes in any unit.
inline float tilt_degrees(float ax,float ay,float az) {
    const float magnitude=std::sqrt(ax*ax+ay*ay+az*az);
    if(magnitude<=0)return NAN;
    return std::acos(std::fabs(az)/magnitude)*57.29578f;
}
inline void motion_text(float tilt,char* out,size_t size) {
    if(std::isnan(tilt))snprintf(out,size,"No data");
    else snprintf(out,size,"Tilt %d\xc2\xb0",static_cast<int>(std::lround(tilt)));
}
// INA226 on the battery branch; negative current flows into the battery (G-0001.05 C1).
// On USB power the load is not on this branch, so the tile shows only charging.
inline void power_text(float bus_v,float shunt_a,char* out,size_t size) {
    if(std::isnan(bus_v))snprintf(out,size,"No data");
    else if(shunt_a<=-0.02f)snprintf(out,size,"%.2f V\nCharging %.2f A",bus_v,-shunt_a);
    else if(shunt_a>=0.02f)snprintf(out,size,"%.2f V\nUsing %.2f A (%.1f W)",bus_v,shunt_a,bus_v*shunt_a);
    else snprintf(out,size,"%.2f V\nNo battery current",bus_v);
}
// ipv4 as esp_netif stores it (first octet in the low byte); 0 means no address.
inline void ipv4_text(uint32_t ipv4,char* out,size_t size) {
    snprintf(out,size,"%u.%u.%u.%u",static_cast<unsigned>(ipv4&0xff),static_cast<unsigned>((ipv4>>8)&0xff),
             static_cast<unsigned>((ipv4>>16)&0xff),static_cast<unsigned>(ipv4>>24));
}
inline void network_text(uint32_t ipv4,char* out,size_t size) {
    if(!ipv4){snprintf(out,size,"Wi-Fi offline");return;}
    char address[16];ipv4_text(ipv4,address,sizeof(address));snprintf(out,size,"Wi-Fi %s",address);
}
// Hotspot mode (F-0003): ipv4 is the device's own address, peer the last device given one.
inline void network_text(uint32_t ipv4,uint32_t peer_ipv4,bool access_point,char* out,size_t size) {
    if(!access_point){network_text(ipv4,out,size);return;}
    if(!ipv4){snprintf(out,size,"Hotspot starting");return;}
    if(!peer_ipv4){snprintf(out,size,"Hotspot on\nWaiting for the Mac");return;}
    char address[16];ipv4_text(peer_ipv4,address,sizeof(address));snprintf(out,size,"Hotspot on\nMac %s",address);
}
// The Setup screen's longer form of the same state; ssid is the hotspot's network name.
inline void setup_network_text(uint32_t ipv4,uint32_t peer_ipv4,bool access_point,const char* ssid,char* out,size_t size) {
    char address[16];
    if(!access_point) {
        if(!ipv4){snprintf(out,size,"Wi-Fi offline");return;}
        ipv4_text(ipv4,address,sizeof(address));snprintf(out,size,"Wi-Fi on, device %s",address);return;
    }
    if(!ipv4){snprintf(out,size,"Hotspot starting, network %s",ssid);return;}
    if(!peer_ipv4){snprintf(out,size,"Hotspot on, network %s\nWaiting for the Mac to join",ssid);return;}
    ipv4_text(peer_ipv4,address,sizeof(address));snprintf(out,size,"Hotspot on, network %s\nMac %s joined",ssid,address);
}
}
