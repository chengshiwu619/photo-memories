from core.models import Memory
from business.memory.special_memory_selection import select_special_memories


def _memory(mid, memory_type, created_at="2026-06-01 10:00:00", photo_count=5, **kwargs):
    import json

    return Memory(
        id=mid,
        memory_type=memory_type,
        title=f"{memory_type}-{mid}",
        photo_ids=json.dumps(list(range(mid * 100, mid * 100 + photo_count))),
        created_at=created_at,
        **kwargs,
    )


def test_select_special_memories_prefers_story_types_and_caps_count():
    memories = [
        _memory(1, "scene", "2026-06-03 10:00:00"),
        _memory(2, "recent", "2026-06-02 10:00:00"),
        _memory(3, "on_this_day", "2026-06-01 10:00:00"),
        _memory(4, "person", "2026-06-04 10:00:00"),
        _memory(5, "event", "2026-06-05 10:00:00"),
        _memory(6, "special_date", "2026-06-06 10:00:00"),
        _memory(7, "scene", "2026-06-07 10:00:00"),
    ]

    selected = select_special_memories(memories, visible_photo_count=lambda m: 5)

    assert [m.id for m in selected] == [3, 6, 2, 5, 4, 7]


def test_select_special_memories_filters_hidden_dismissed_and_unrenderable():
    memories = [
        _memory(1, "on_this_day", dismissed_at="2026-06-01"),
        _memory(2, "special_date", is_hidden=1),
        _memory(3, "recent"),
        _memory(4, "event"),
    ]
    visible = {3: 2, 4: 4}

    selected = select_special_memories(
        memories,
        visible_photo_count=lambda m: visible.get(m.id, 5),
        min_visible_photos=3,
    )

    assert [m.id for m in selected] == [4]


def test_select_special_memories_uses_folder_only_as_fallback():
    memories = [
        _memory(1, "folder", "2026-06-05 10:00:00"),
        _memory(2, "recent", "2026-06-01 10:00:00"),
    ]

    selected = select_special_memories(memories, visible_photo_count=lambda m: 5)

    assert [m.id for m in selected] == [2, 1]


def test_select_special_memories_allows_folder_when_it_is_the_only_choice():
    memories = [
        _memory(1, "folder", "2026-06-05 10:00:00"),
        _memory(2, "folder", "2026-06-01 10:00:00"),
    ]

    selected = select_special_memories(memories, visible_photo_count=lambda m: 5)

    assert [m.id for m in selected] == [1, 2]


def test_select_special_memories_stops_visibility_checks_after_enough_items():
    memories = [_memory(i, "recent", f"2026-06-{i:02d} 10:00:00") for i in range(1, 12)]
    checked = []

    selected = select_special_memories(
        memories,
        visible_photo_count=lambda m: checked.append(m.id) or 5,
    )

    assert len(selected) == 6
    assert len(checked) == 6


def test_select_special_memories_suppresses_heavily_overlapping_stories():
    import json

    memories = [
        _memory(1, "on_this_day"),
        _memory(2, "special_date"),
        _memory(3, "event"),
        _memory(4, "recent"),
    ]
    memories[0].photo_ids = json.dumps([1, 2, 3, 4, 5])
    memories[1].photo_ids = json.dumps([1, 2, 3, 4])
    memories[2].photo_ids = json.dumps([20, 21, 22, 23])
    memories[3].photo_ids = json.dumps([30, 31, 32, 33])

    selected = select_special_memories(memories, visible_photo_count=lambda m: 5)

    assert [m.id for m in selected] == [1, 4, 3]


def test_select_special_memories_uses_folder_to_reach_minimum_without_flooding():
    memories = [
        _memory(1, "recent"),
        _memory(2, "folder"),
        _memory(3, "folder"),
        _memory(4, "folder"),
    ]

    selected = select_special_memories(
        memories,
        visible_photo_count=lambda m: 5,
        min_items=3,
    )

    assert [m.id for m in selected] == [1, 2, 3]


def test_select_special_memories_filters_overlong_existing_event_memory():
    import json

    memories = [
        _memory(
            1,
            "event",
            payload=json.dumps({"start_date": "2026-06-01", "end_date": "2026-08-01"}),
        ),
        _memory(
            2,
            "event",
            payload=json.dumps({"start_date": "2026-06-01", "end_date": "2026-06-12"}),
        ),
    ]

    selected = select_special_memories(memories, visible_photo_count=lambda m: 5)

    assert [m.id for m in selected] == [2]
