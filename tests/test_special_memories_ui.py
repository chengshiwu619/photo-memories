import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication

from core.models import Memory
from ui.components.special_memories import PokerStack, SpecialMemoriesView


_APP = None


def _app():
    global _APP
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    _APP = app
    return app


def _memory(mid, title):
    return Memory(
        id=mid,
        memory_type="on_this_day" if mid == 1 else "recent",
        title=title,
        description="一段安静的旧时光",
        photo_ids=json.dumps([1, 2, 3, 4]),
    )


def _photos():
    return [
        {"id": i, "thumbnail_path": "", "file_path": f"{i}.jpg", "file_name": f"{i}.jpg"}
        for i in range(1, 5)
    ]


def test_featured_poker_stack_builds_cover_preview_without_crashing():
    _app()
    stack = PokerStack(_memory(1, "三年前的今天"), featured=True)

    stack.resize(760, 420)
    stack.load_photos(_photos())

    assert stack._featured is True
    assert stack._stack_container.height() > 260
    assert len(stack._cards) >= 2
    stack.close()


def test_special_memories_view_uses_one_featured_stack_and_candidates():
    _app()
    view = SpecialMemoriesView()

    view.load_memories([_memory(1, "今日回忆"), _memory(2, "近期回忆")])

    stacks = [s for s in view._stacks if isinstance(s, PokerStack)]
    assert len(stacks) == 2
    assert stacks[0]._featured is True
    assert stacks[1]._featured is False
    view.close()
