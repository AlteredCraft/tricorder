#include "speech_filter.h"
#include <cmath>
#include <limits>

// 63-tap Blackman-windowed sinc, cutoff 6500 Hz at 48000 Hz, DC gain 1.
// Coefficients generated from the stated formula, not fitted to the fixtures.
static constexpr float lowpass[] = {
    -1.349323946676e-19f, 3.766876983216e-06f, -1.821253475075e-05f, -9.433911780564e-05f,
    -1.532907693003e-04f, -4.017863685807e-05f, 3.139900880765e-04f, 6.994050714406e-04f,
    6.521029596032e-04f, -1.773194196803e-04f, -1.515945486808e-03f, -2.318750697531e-03f,
    -1.375559137941e-03f, 1.520758420124e-03f, 4.750841871409e-03f, 5.428493474492e-03f,
    1.514086821355e-03f, -5.804561236423e-03f, -1.161462270026e-02f, -9.996122672014e-03f,
    1.118925106468e-03f, 1.639527377485e-02f, 2.448929934639e-02f, 1.512794283292e-02f,
    -1.186112356868e-02f, -4.206057588130e-02f, -5.135670012350e-02f, -1.924863872863e-02f,
    5.674953145595e-02f, 1.551515878739e-01f, 2.383065057102e-01f, 2.708268580547e-01f,
    2.383065057102e-01f, 1.551515878739e-01f, 5.674953145595e-02f, -1.924863872863e-02f,
    -5.135670012350e-02f, -4.206057588130e-02f, -1.186112356868e-02f, 1.512794283292e-02f,
    2.448929934639e-02f, 1.639527377485e-02f, 1.118925106468e-03f, -9.996122672014e-03f,
    -1.161462270026e-02f, -5.804561236423e-03f, 1.514086821355e-03f, 5.428493474492e-03f,
    4.750841871409e-03f, 1.520758420124e-03f, -1.375559137941e-03f, -2.318750697531e-03f,
    -1.515945486808e-03f, -1.773194196803e-04f, 6.521029596032e-04f, 6.994050714406e-04f,
    3.139900880765e-04f, -4.017863685807e-05f, -1.532907693003e-04f, -9.433911780564e-05f,
    -1.821253475075e-05f, 3.766876983216e-06f, -1.349323946676e-19f
};
static constexpr float highpass_alpha=0.989582664726854f; // exp(-2*pi*80/48000)

bool SpeechFilter::process(const int16_t* source,size_t frames,int16_t* output,size_t capacity,SpeechBlockResult& result) {
    if (!source || !output || !frames || frames>2048 || !channels_ || channels_>4 || slot_>=channels_
        || source_frames_>std::numeric_limits<uint64_t>::max()-frames) return false;
    const size_t produced=enabled_ ? (phase_+frames)/3 : frames;
    if (capacity<produced) return false;
    uintptr_t input_begin=reinterpret_cast<uintptr_t>(source),output_begin=reinterpret_cast<uintptr_t>(output);
    size_t input_bytes=frames*channels_*2,output_bytes=produced*2;
    if (input_begin>UINTPTR_MAX-input_bytes || output_begin>UINTPTR_MAX-output_bytes
        || (input_begin<output_begin+output_bytes && output_begin<input_begin+input_bytes)) return false;
    result={};result.source_start=source_frames_;result.source_frames=frames;
    for (size_t frame=0;frame<frames;++frame) {
        int16_t sample=source[frame*channels_+slot_];
        if (sample==-32768 || sample==32767) ++result.input_clipped;
        if (!enabled_) { output[result.output_frames++]=sample;continue; }
        float highpass=sample-previous_input_+highpass_alpha*previous_highpass_;
        previous_input_=sample;previous_highpass_=highpass;
        history_[head_]=highpass;
        head_=(head_+1)%63;
        if (++phase_!=3) continue;
        phase_=0;
        float filtered=0;
        unsigned index=head_;
        for (unsigned tap=0;tap<63;++tap) {
            index=index ? index-1 : 62;
            filtered+=lowpass[tap]*history_[index];
        }
        long rounded=std::lround(filtered);
        if (rounded>32767) {rounded=32767;++result.output_clipped;}
        if (rounded<-32768) {rounded=-32768;++result.output_clipped;}
        output[result.output_frames++]=static_cast<int16_t>(rounded);
    }
    source_frames_+=frames;
    return true;
}
