import time

from app.core.ids import uuid7, uuid7_timestamp_ms


def test_uuid7_version_variant_and_timestamp() -> None:
    before = time.time_ns() // 1_000_000
    value = uuid7()
    after = time.time_ns() // 1_000_000
    assert value.version == 7
    assert value.variant == "specified in RFC 4122"
    assert before <= uuid7_timestamp_ms(value) <= after + 1


def test_uuid7_is_unique_and_monotonic() -> None:
    values = [uuid7() for _ in range(20_000)]
    assert len(set(values)) == len(values)
    assert values == sorted(values)
