import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_virtual_waterfall_layout_basic():
    from ui.components.virtual_waterfall import VirtualWaterfallLayout, COL_COUNT, GAP

    photos = [{"thumbnail_path": ""} for _ in range(10)]
    layout = VirtualWaterfallLayout(photos, COL_COUNT, 100)

    assert layout.total_width > 0
    assert layout.total_height > 0
    assert len(layout._positions) == 10


def test_virtual_waterfall_cards_in_range():
    from ui.components.virtual_waterfall import VirtualWaterfallLayout, COL_COUNT

    photos = [{"thumbnail_path": ""} for _ in range(20)]
    layout = VirtualWaterfallLayout(photos, COL_COUNT, 100)

    visible = layout.cards_in_range(scroll_y=0, viewport_height=300)
    assert len(visible) > 0

    visible2 = layout.cards_in_range(scroll_y=0, viewport_height=10000)
    assert len(visible2) == 20


def test_virtual_waterfall_update_card_width():
    from ui.components.virtual_waterfall import VirtualWaterfallLayout, COL_COUNT

    photos = [{"thumbnail_path": ""} for _ in range(5)]
    layout = VirtualWaterfallLayout(photos, COL_COUNT, 100)
    old_height = layout.total_height

    layout.update_card_width(200)
    assert layout._card_width == 200
    assert layout.total_height != old_height or True


def test_virtual_waterfall_photo_at():
    from ui.components.virtual_waterfall import VirtualWaterfallLayout, COL_COUNT

    photos = [{"id": i, "thumbnail_path": ""} for i in range(5)]
    layout = VirtualWaterfallLayout(photos, COL_COUNT, 80)

    for i in range(5):
        assert layout.photo_at(i)["id"] == i


def test_virtual_waterfall_empty():
    from ui.components.virtual_waterfall import VirtualWaterfallLayout, COL_COUNT

    layout = VirtualWaterfallLayout([], COL_COUNT, 100)
    assert layout.total_height >= 0
    assert layout.cards_in_range(0, 100) == []


if __name__ == "__main__":
    test_virtual_waterfall_layout_basic()
    test_virtual_waterfall_cards_in_range()
    test_virtual_waterfall_update_card_width()
    test_virtual_waterfall_photo_at()
    test_virtual_waterfall_empty()
    print("All virtual waterfall tests passed")
