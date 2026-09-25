#pragma once

// Receive side of spoken-guidance playback. The stream needs about 66 KB/s of
// WebSocket payload (24 kHz s16 as base64 JSON, about 5.6 KB per 2048-frame
// chunk), and the socket is read in pieces of at most 1 KiB. One read per 20 ms
// playback block (about 51 KB/s) falls behind and the buffer runs dry. Before
// each block, read until one message completes, nothing is waiting, or `limit`
// reads: up to about 4x real time without holding the codec for more than one
// message.
// read(): -1 error, 0 nothing waiting, 1 a message completed, 2 part of one read.
template<class Read> int speech_receive(Read read,unsigned limit) {
    int result=read();
    for(unsigned n=1;result==2 && n<limit;++n)result=read();
    return result;
}
