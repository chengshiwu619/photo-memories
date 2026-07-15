from pathlib import Path


def test_nsfw_review_button_is_before_starred_memories_button():
    source = Path("ui/app.py").read_text(encoding="utf-8")

    assert source.index('QPushButton("疑似样片")') < source.index('QPushButton("优秀回忆")')


def test_nsfw_review_has_bulk_action_and_toggle_close():
    app_source = Path("ui/app.py").read_text(encoding="utf-8")
    view_source = Path("ui/components/nsfw_review_view.py").read_text(encoding="utf-8")

    assert 'QPushButton("剩余全转样片")' in view_source
    assert "QGridLayout" in view_source
    assert "NSFW_REVIEW_PAGE_LIMIT = 600" in app_source
    assert "mark_remaining_sample_requested" in app_source
    assert "dismiss_many_requested" in app_source
    assert "dismiss_review_candidates" in app_source
    assert 'if self._current_nav == "nsfw_review":' in app_source
    assert 'self.sidebar.set_nav("random")' in app_source


def test_nsfw_review_cards_support_click_and_drag_ignore():
    view_source = Path("ui/components/nsfw_review_view.py").read_text(encoding="utf-8")

    assert "drag_started" in view_source
    assert "drag_entered" in view_source
    assert "drag_finished" in view_source
    assert "WA_TransparentForMouseEvents" in view_source
    assert "self.dismiss_many_requested.emit(ids)" in view_source
