from business.memory.memory_discovery import _build_event_segments, _build_trip_segments, _find_existing_memory


def _row(file_id, day, lat=31.2304, lon=121.4737):
    return (file_id, f"{day}T10:00:00", lat, lon)


def test_event_segments_split_same_location_when_gap_is_too_large():
    rows = [
        _row(1, "2026-06-01"),
        _row(2, "2026-06-02"),
        _row(3, "2026-06-08"),
        _row(4, "2026-06-09"),
    ]

    segments = _build_event_segments(rows, gps_delta=0.01, max_gap_days=2, max_span_days=10)

    assert [[p[0] for p in s["photos"]] for s in segments] == [[1, 2], [3, 4]]
    assert [(s["start_date"], s["end_date"]) for s in segments] == [
        ("2026-06-01", "2026-06-02"),
        ("2026-06-08", "2026-06-09"),
    ]


def test_event_segments_keep_continuous_trip_longer_than_ten_days_together():
    rows = [_row(i + 1, f"2026-06-{i + 1:02d}") for i in range(12)]

    segments = _build_event_segments(rows, gps_delta=0.01, max_gap_days=2, max_span_days=21)

    assert [[p[0] for p in s["photos"]] for s in segments] == [list(range(1, 13))]
    assert segments[0]["start_date"] == "2026-06-01"
    assert segments[0]["end_date"] == "2026-06-12"


def test_event_segments_split_only_after_generous_hard_span():
    rows = [_row(i + 1, f"2026-06-{i + 1:02d}") for i in range(23)]

    segments = _build_event_segments(rows, gps_delta=0.01, max_gap_days=2, max_span_days=21)

    assert [[p[0] for p in s["photos"]] for s in segments] == [
        list(range(1, 22)),
        [22, 23],
    ]


def test_event_segments_keep_locations_separate():
    rows = [
        _row(1, "2026-06-01", lat=31.2304, lon=121.4737),
        _row(2, "2026-06-02", lat=31.2305, lon=121.4738),
        _row(3, "2026-06-01", lat=39.9042, lon=116.4074),
        _row(4, "2026-06-02", lat=39.9043, lon=116.4075),
    ]

    segments = _build_event_segments(rows, gps_delta=0.01)

    segment_ids = sorted([tuple(p[0] for p in s["photos"]) for s in segments])
    assert segment_ids == [(1, 2), (3, 4)]


def test_trip_segments_group_continuous_multi_location_route():
    rows = [
        _row(1, "2026-06-01", lat=31.2304, lon=121.4737),
        _row(2, "2026-06-02", lat=31.2305, lon=121.4738),
        _row(3, "2026-06-03", lat=30.2741, lon=120.1551),
        _row(4, "2026-06-04", lat=30.2742, lon=120.1552),
        _row(5, "2026-06-05", lat=29.8683, lon=121.5440),
    ]

    segments = _build_trip_segments(rows, gps_delta=0.01)

    assert len(segments) == 1
    assert [p[0] for p in segments[0]["photos"]] == [1, 2, 3, 4, 5]
    assert segments[0]["start_date"] == "2026-06-01"
    assert segments[0]["end_date"] == "2026-06-05"
    assert len(segments[0]["location_keys"]) == 3


def test_trip_segments_do_not_treat_single_location_as_route_trip():
    rows = [_row(i + 1, f"2026-06-{i + 1:02d}") for i in range(5)]

    segments = _build_trip_segments(rows, gps_delta=0.01)

    assert segments == []


def test_trip_segments_do_not_treat_two_location_commute_as_route_trip():
    rows = [
        _row(1, "2026-06-01", lat=31.2304, lon=121.4737),
        _row(2, "2026-06-02", lat=30.2741, lon=120.1551),
        _row(3, "2026-06-03", lat=31.2305, lon=121.4738),
        _row(4, "2026-06-04", lat=30.2742, lon=120.1552),
        _row(5, "2026-06-05", lat=31.2306, lon=121.4739),
    ]

    segments = _build_trip_segments(rows, gps_delta=0.01)

    assert segments == []


class _Repo:
    def __init__(self, rows):
        self._rows = rows

    def find_by_type_and_payload_key(self, memory_type):
        return self._rows


def test_find_existing_event_memory_understands_event_key_and_legacy_gps_cluster():
    import json

    event_key = "31.23,121.47|2026-06-01|2026-06-12"
    repo = _Repo([
        (1, json.dumps({"event_key": event_key})),
        (2, json.dumps({"gps_cluster": "39.9,116.4"})),
    ])

    assert _find_existing_memory(repo, "event", event_key) == 1
    assert _find_existing_memory(repo, "event", "39.9,116.4") == 2
