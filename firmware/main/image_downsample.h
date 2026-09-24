#pragma once
#include <cstddef>
#include <cstdint>

// Box-average each factor x factor block of packed RGB565 (as captured and as
// LVGL draws it). Rounds each channel to nearest.
inline bool rgb565_downsample(const uint16_t* source,size_t source_bytes,unsigned width,unsigned height,
                              unsigned factor,uint16_t* output,size_t output_bytes) {
    if (!source || !output || !factor || !width || !height || width%factor || height%factor
        || source_bytes!=size_t(width)*height*2
        || output_bytes!=size_t(width/factor)*(height/factor)*2) return false;
    const unsigned area=factor*factor,out_width=width/factor;
    for (unsigned oy=0;oy<height/factor;++oy)
        for (unsigned ox=0;ox<out_width;++ox) {
            unsigned r=0,g=0,b=0;
            for (unsigned y=oy*factor;y<(oy+1)*factor;++y)
                for (unsigned x=ox*factor;x<(ox+1)*factor;++x) {
                    const uint16_t p=source[size_t(y)*width+x];
                    r+=p>>11;g+=(p>>5)&63;b+=p&31;
                }
            output[size_t(oy)*out_width+ox]=uint16_t(((r+area/2)/area)<<11 | ((g+area/2)/area)<<5 | (b+area/2)/area);
        }
    return true;
}

// Mean BT.601 luma, 0..255 (exposure sanity check for a context shot).
inline unsigned rgb565_mean_luma(const uint16_t* pixels,size_t count) {
    if (!pixels || !count) return 0;
    uint64_t sum=0;
    for (size_t i=0;i<count;++i) {
        const uint16_t p=pixels[i];
        const unsigned r=(p>>11)*255/31,g=((p>>5)&63)*255/63,b=(p&31)*255/31;
        sum+=(77*r+150*g+29*b)>>8;
    }
    return unsigned((sum+count/2)/count);
}
