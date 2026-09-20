#include "ui_ingress.h"
#include "esp_lcd_panel_ops.h"
#include "esp_timer.h"

// The diagnostic has one BSP panel, exclusively driven through LVGL. Observe
// calls only while holding that display's lock; retain the original arguments,
// return value and asynchronous completion callback ownership.
static UiIngress* active=nullptr;
void ui_observe(UiIngress* log) {active=log;}
extern "C" esp_err_t __real_esp_lcd_panel_draw_bitmap(esp_lcd_panel_handle_t,int,int,int,int,const void*);
extern "C" esp_err_t __wrap_esp_lcd_panel_draw_bitmap(esp_lcd_panel_handle_t panel,int x1,int y1,int x2,int y2,const void* pixels) {
    const int64_t start=active ? esp_timer_get_time():0;
    auto result=__real_esp_lcd_panel_draw_bitmap(panel,x1,y1,x2,y2,pixels);
    if (active) active->submitted(start,esp_timer_get_time(),x1,y1,x2,y2,result);
    return result;
}
