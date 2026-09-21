#pragma once

// Native 30 Hz CSI selects the next destination before reporting completion.
// Four fixed buffers cover a held source and two completed frames during the
// observed 69.540 ms hash/copy burst, with one destination still available.
// Reuse remains a failing counter; this is not a lossy-preview policy.
inline constexpr unsigned camera_capture_buffer_count=4;
