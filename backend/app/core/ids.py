"""UUID version 7 (RFC 9562): 48-bit Unix millisecond timestamp + random bits.

Time-ordered ids keep B-tree indexes compact and make ``ORDER BY id`` roughly
chronological. Python 3.12 has no ``uuid.uuid7``; this implementation adds a
monotonic counter so ids generated in the same millisecond still sort in order.
"""

import os
import threading
import time
import uuid

_lock = threading.Lock()
_last_ms = 0
_counter = 0


def uuid7() -> uuid.UUID:
    global _last_ms, _counter
    with _lock:
        ms = time.time_ns() // 1_000_000
        if ms <= _last_ms:
            ms = _last_ms
            _counter += 1
            if _counter > 0xFFF:  # 12-bit counter exhausted: borrow the next millisecond
                ms += 1
                _counter = 0
        else:
            _counter = int.from_bytes(os.urandom(2)) & 0x3FF  # random start, room to grow
        _last_ms = ms
        counter = _counter
    rand_b = int.from_bytes(os.urandom(8)) & ((1 << 62) - 1)
    value = (ms & ((1 << 48) - 1)) << 80
    value |= 0x7 << 76  # version 7
    value |= counter << 64  # rand_a field used as a monotonic counter
    value |= 0b10 << 62  # RFC 4122 variant
    value |= rand_b
    return uuid.UUID(int=value)


def uuid7_timestamp_ms(value: uuid.UUID) -> int:
    return value.int >> 80
