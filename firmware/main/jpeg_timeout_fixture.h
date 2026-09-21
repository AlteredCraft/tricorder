#pragma once
// Opt-in diagnostic build only. Reserves DMA2D reorder resources so the real
// encoder queues and times out. Deliberately retains resources until reset.
bool jpeg_arm_queue_timeout_fixture();
