from __future__ import annotations

import json
from datetime import datetime
from typing import Callable, Iterable, List, Optional

from core.models import Memory


TYPE_PRIORITY = {
    "on_this_day": 0,
    "special_date": 1,
    "recent": 2,
    "event": 3,
    "person": 4,
    "scene": 5,
    "folder": 9,
}

DEFAULT_MAX_ITEMS = 6
DEFAULT_MIN_ITEMS = 3
DEFAULT_MIN_VISIBLE_PHOTOS = 3
DEFAULT_MAX_EVENT_SPAN_DAYS = 21
DEFAULT_MAX_PHOTO_OVERLAP = 0.65


def _memory_is_coherent(memory: Memory, max_event_span_days: int = DEFAULT_MAX_EVENT_SPAN_DAYS) -> bool:
    if memory.memory_type != "event" or not memory.payload:
        return True
    try:
        payload = json.loads(memory.payload)
        start = payload.get("start_date")
        end = payload.get("end_date")
        if not start or not end:
            return True
        start_dt = datetime.strptime(start[:10], "%Y-%m-%d")
        end_dt = datetime.strptime(end[:10], "%Y-%m-%d")
        return (end_dt.date() - start_dt.date()).days < max_event_span_days
    except Exception:
        return True


def select_special_memories(
    memories: Iterable[Memory],
    *,
    visible_photo_count: Optional[Callable[[Memory], int]] = None,
    max_items: int = DEFAULT_MAX_ITEMS,
    min_items: int = DEFAULT_MIN_ITEMS,
    min_visible_photos: int = DEFAULT_MIN_VISIBLE_PHOTOS,
    max_photo_overlap: float = DEFAULT_MAX_PHOTO_OVERLAP,
) -> List[Memory]:
    """Pick a small, story-like set for the special memories page."""
    if max_items <= 0:
        return []

    unique = []
    seen = set()
    for memory in memories:
        mid = memory.id
        key = mid if mid is not None else (memory.memory_type, memory.title, memory.photo_ids)
        if key in seen:
            continue
        seen.add(key)
        if memory.dismissed_at or getattr(memory, "is_hidden", 0):
            continue
        if not _memory_is_coherent(memory):
            continue
        unique.append(memory)

    recent_first = sorted(unique, key=lambda m: m.created_at or "", reverse=True)
    less_seen_first = sorted(recent_first, key=lambda m: bool(m.last_shown_at))
    prioritized = sorted(
        less_seen_first,
        key=lambda m: TYPE_PRIORITY.get(m.memory_type, 6),
    )
    primary = [m for m in prioritized if m.memory_type != "folder"]
    fallback = [m for m in prioritized if m.memory_type == "folder"]
    selected: List[Memory] = []
    selected_photo_sets = []

    def can_add(memory: Memory, *, allow_overlap: bool = False) -> bool:
        if visible_photo_count is not None and visible_photo_count(memory) < min_visible_photos:
            return False
        photo_ids = set(memory.get_photo_id_list())
        if not photo_ids:
            return False
        if not allow_overlap:
            for existing_ids in selected_photo_sets:
                smaller = min(len(photo_ids), len(existing_ids))
                if smaller and len(photo_ids & existing_ids) / smaller > max_photo_overlap:
                    return False
        selected.append(memory)
        selected_photo_sets.append(photo_ids)
        return True

    for memory in primary:
        can_add(memory)
        if len(selected) >= max_items:
            return selected

    # 文件夹不是故事主来源，只在有效故事不足时补齐页面，避免一条卡片显得空。
    target_min = min(max(min_items, 0), max_items)
    for memory in fallback:
        if len(selected) >= target_min:
            break
        can_add(memory)

    # 候选很少且互相重叠时，宁可补一条有效故事，也不要留下近乎空白的页面。
    if len(selected) < target_min:
        selected_keys = {m.id for m in selected}
        for memory in primary:
            if memory.id in selected_keys:
                continue
            if can_add(memory, allow_overlap=True):
                selected_keys.add(memory.id)
            if len(selected) >= target_min:
                break

    return selected
