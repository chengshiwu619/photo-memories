import time

import pytest

pytest.importorskip("PyQt6")


class _FakeSignal:
    def __init__(self):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)


class _FakeWorker:
    started = []

    def __init__(self, token, cat_id, starred_only, limit=None):
        self.token = token
        self.cat_id = cat_id
        self.starred_only = starred_only
        self.limit = limit
        self.loaded = _FakeSignal()
        self.failed = _FakeSignal()
        self.finished = _FakeSignal()
        _FakeWorker.started.append(self)

    def start(self):
        self.was_started = True

    def isRunning(self):
        return False

    def requestInterruption(self):
        self.interrupted = True



class _FakeMoreWorker:
    started = []

    def __init__(self, token, cat_id, starred_only=False, exclude_ids=None, limit=30):
        self.token = token
        self.cat_id = cat_id
        self.starred_only = starred_only
        self.exclude_ids = set(exclude_ids or [])
        self.limit = limit
        self.loaded = _FakeSignal()
        self.failed = _FakeSignal()
        self.finished = _FakeSignal()
        _FakeMoreWorker.started.append(self)

    def start(self):
        self.was_started = True

    def isRunning(self):
        return False

    def requestInterruption(self):
        self.interrupted = True

class _FakePrefetchWorker(_FakeWorker):
    started = []
    prefetched = None

    def __init__(self, cat_id, starred_only, data_version, generation, limit):
        self.cat_id = cat_id
        self.starred_only = starred_only
        self.data_version = data_version
        self.generation = generation
        self.limit = limit
        self.prefetched = _FakeSignal()
        self.failed = _FakeSignal()
        self.finished = _FakeSignal()
        _FakePrefetchWorker.started.append(self)


class _FakeShownHistoryWorker:
    started = []

    def __init__(self, photos, cat_id):
        self.photos = list(photos)
        self.cat_id = cat_id
        self.failed = _FakeSignal()
        self.finished = _FakeSignal()
        self.interrupted = False
        self.waited = None
        _FakeShownHistoryWorker.started.append(self)

    def start(self):
        self.was_started = True

    def isRunning(self):
        return True

    def requestInterruption(self):
        self.interrupted = True

    def wait(self, wait_ms):
        self.waited = wait_ms


class _FakePage:
    def __init__(self):
        self.loaded_photos = None
        self.appended_photos = []
        self.all_loaded = False
        self.reset_for_shuffle_called = False
        self._scroll_bar = type("ScrollBar", (), {"value": 99, "setValue": lambda self, value: setattr(self, "value", value)})()
        self.scroll = type("Scroll", (), {"verticalScrollBar": lambda _self: self._scroll_bar})()

    def load_photos(self, photos):
        self.loaded_photos = list(photos)

    def append_photos(self, photos):
        self.appended_photos.extend(list(photos))

    def set_all_loaded(self, has_thumbnails_remaining=True):
        self.all_loaded = True
        self.has_thumbnails_remaining = has_thumbnails_remaining

    def reset_for_shuffle(self):
        self.reset_for_shuffle_called = True


class _RunningPrefetch:
    def __init__(self):
        self.interrupted = False

    def isRunning(self):
        return True

    def requestInterruption(self):
        self.interrupted = True


def _make_window(app_mod):
    win = app_mod.MainWindow.__new__(app_mod.MainWindow)
    win.pages = [_FakePage(), _FakePage()]
    win.starred_only = False
    win._cat_result_cache = {}
    win._cat_load_token = 0
    win._cat_more_token = 0
    win._cat_active_tokens = {}
    win._cat_request_modes = {}
    win._cat_request_versions = {}
    win._cat_workers = {}
    win._cat_visible_cache = {}
    win._cat_prefetch_workers = {}
    win._cat_more_workers = {}
    win._cat_more_tokens = {}
    win._cat_prefetch_generation = 0
    win._cat_offsets = {}
    win._cat_all_loaded = {}
    win._cat_total_counts = {}
    win._cat_shown_ids = {}
    win._cat_photos = {}
    win._cat_rendered_pages = set()
    win._random_category_db_version = lambda: ("v1",)
    win._random_category_version_cache = None
    win._random_category_version_cache_at = 0.0
    win._random_first_render_done = False
    win._current_random_cat_id = None
    win._shown_history_workers = set()
    win._record_shown_photos_async = lambda photos, cat_id: None
    return win


def test_random_category_db_version_is_ttl_cached(monkeypatch):
    import ui.app as app_mod

    class FakeDb:
        def __init__(self):
            self.calls = 0

        def execute(self, _sql):
            self.calls += 1
            value = self.calls
            return type("FakeCursor", (), {"fetchone": lambda _self: (value,)})()

    times = [10.0, 12.0, 13.5]
    win = app_mod.MainWindow.__new__(app_mod.MainWindow)
    win.db = FakeDb()
    win._random_category_version_cache = None
    win._random_category_version_cache_at = 0.0
    monkeypatch.setattr(app_mod.time, "monotonic", lambda: times.pop(0))

    first = win._random_category_db_version()
    second = win._random_category_db_version()
    third = win._random_category_db_version()

    assert first == (1,)
    assert second == first
    assert third == (2,)
    assert win.db.calls == 2


def test_load_category_starts_worker_without_sync_recommendation(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    _FakeWorker.started.clear()
    monkeypatch.setattr(app_mod, "CategoryLoadWorker", _FakeWorker)
    monkeypatch.setattr(app_mod, "rank_category_photos", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("sync rank called")))
    win._random_category_db_version = lambda: (_ for _ in ()).throw(AssertionError("db version should not be queried before worker start"))

    win.load_category(0)

    assert len(_FakeWorker.started) == 1
    assert _FakeWorker.started[0].was_started is True
    assert _FakeWorker.started[0].limit == app_mod._random_initial_pool_size(1)
    assert win.pages[0].loaded_photos == []


def test_same_category_click_reuses_running_worker(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    running = _RunningPrefetch()
    win._current_random_cat_id = 1
    win._cat_workers[1] = running
    win._random_category_db_version = lambda: (_ for _ in ()).throw(AssertionError("db version should not be queried"))
    _FakeWorker.started.clear()
    monkeypatch.setattr(app_mod, "CategoryLoadWorker", _FakeWorker)

    win.load_category(0)

    assert running.interrupted is False
    assert _FakeWorker.started == []
    assert win.pages[0].loaded_photos is None


def test_same_category_click_reuses_rendered_page(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    win._current_random_cat_id = 1
    win._cat_rendered_pages.add(1)
    win._cat_photos[1] = [{"id": 1}]
    win.pages[0].loaded_photos = [{"id": 1}]
    win.pages[0]._scroll_bar.value = 220
    win._random_category_db_version = lambda: (_ for _ in ()).throw(AssertionError("db version should not be queried"))
    _FakeWorker.started.clear()
    monkeypatch.setattr(app_mod, "CategoryLoadWorker", _FakeWorker)

    win.load_category(0)

    assert _FakeWorker.started == []
    assert win.pages[0].loaded_photos == [{"id": 1}]
    assert win.pages[0]._scroll_bar.value == 220


def test_loaded_result_reuses_request_version_without_second_db_lookup(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    _FakeWorker.started.clear()
    monkeypatch.setattr(app_mod, "CategoryLoadWorker", _FakeWorker)
    monkeypatch.setattr(app_mod, "record_shown_photos", lambda photos, cat_id: None)
    monkeypatch.setattr(win, "_schedule_category_prefetch", lambda *args, **kwargs: None)

    win._cat_load_token += 1
    token = win._cat_load_token
    win._current_random_cat_id = 1
    win._cat_active_tokens[1] = token
    win._start_category_load(0, 1, token, mode="foreground", data_version=("request-version",))
    win._random_category_db_version = lambda: (_ for _ in ()).throw(AssertionError("version queried after worker result"))
    worker = _FakeWorker.started[0]
    win._on_category_loaded(worker.token, 1, [{"id": 1}], {"total_ms": 1.0})

    assert win._cat_result_cache[(1, False)]["version"] == ("request-version",)


def test_loaded_result_without_request_version_does_not_query_db(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    _FakeWorker.started.clear()
    monkeypatch.setattr(app_mod, "CategoryLoadWorker", _FakeWorker)
    monkeypatch.setattr(win, "_schedule_category_prefetch", lambda *args, **kwargs: None)

    win.load_category(0)
    win._random_category_db_version = lambda: (_ for _ in ()).throw(AssertionError("db version should not be queried after worker result"))
    worker = _FakeWorker.started[0]
    win._on_category_loaded(worker.token, 1, [{"id": 1}], {"total_ms": 1.0})

    assert win._cat_result_cache[(1, False)]["version"] is None


def test_render_records_shown_history_asynchronously(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    recorded = []
    monkeypatch.setattr(app_mod, "record_shown_photos", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("sync write called")))
    win._record_shown_photos_async = lambda photos, cat_id: recorded.append((cat_id, list(photos)))
    monkeypatch.setattr(win, "_schedule_category_prefetch", lambda *args, **kwargs: None)

    win._render_category_photos(0, 1, [{"id": 1}, {"id": 2}], {"total_ms": 1.0}, display_total=3)

    assert recorded == [(1, [{"id": 1}, {"id": 2}])]
    assert win.pages[0].loaded_photos == [{"id": 1}, {"id": 2}]


def test_shown_history_worker_is_cancellable(monkeypatch):
    import ui.app as app_mod

    win = app_mod.MainWindow.__new__(app_mod.MainWindow)
    win._shown_history_workers = set()
    _FakeShownHistoryWorker.started.clear()
    monkeypatch.setattr(app_mod, "ShownHistoryWorker", _FakeShownHistoryWorker)

    app_mod.MainWindow._record_shown_photos_async(win, [{"id": 1}], 1)
    worker = _FakeShownHistoryWorker.started[0]

    assert worker.was_started is True
    assert worker in win._shown_history_workers

    app_mod.MainWindow._cancel_shown_history_workers(win, wait_ms=250)

    assert worker.interrupted is True
    assert worker.waited == 250
    assert win._shown_history_workers == set()


def test_shown_history_workers_run_one_at_a_time(monkeypatch):
    import ui.app as app_mod

    win = app_mod.MainWindow.__new__(app_mod.MainWindow)
    win._shown_history_workers = set()
    win._shown_history_pending = []
    _FakeShownHistoryWorker.started.clear()
    monkeypatch.setattr(app_mod, "ShownHistoryWorker", _FakeShownHistoryWorker)
    monkeypatch.setattr(app_mod.QTimer, "singleShot", lambda _ms, callback: callback())

    app_mod.MainWindow._record_shown_photos_async(win, [{"id": 1}], 1)
    app_mod.MainWindow._record_shown_photos_async(win, [{"id": 2}], 1)

    first_worker = _FakeShownHistoryWorker.started[0]
    assert len(_FakeShownHistoryWorker.started) == 1
    assert win._shown_history_pending == [([{"id": 2}], 1)]

    app_mod.MainWindow._on_shown_history_worker_finished(win, first_worker)

    assert len(_FakeShownHistoryWorker.started) == 2
    assert _FakeShownHistoryWorker.started[1].photos == [{"id": 2}]
    assert win._shown_history_pending == []


def test_load_category_clears_existing_photos_instead_of_reusing(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    _FakeWorker.started.clear()
    win._cat_photos[1] = [{"id": i} for i in range(app_mod.RANDOM_FIRST_PAGE_SIZE + 10)]
    monkeypatch.setattr(app_mod, "CategoryLoadWorker", _FakeWorker)

    win.load_category(0)

    assert win.pages[0].loaded_photos == []
    assert win._cat_photos[1] == []
    assert len(_FakeWorker.started) == 1


def test_old_category_worker_result_is_ignored(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    rendered = []
    monkeypatch.setattr(win, "_render_category_photos", lambda *args, **kwargs: rendered.append(args))

    win._cat_active_tokens[1] = 2
    win._on_category_loaded(1, 1, [{"id": 1}], {})

    assert rendered == []


def test_loaded_result_for_non_current_category_is_discarded(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    rendered = []
    monkeypatch.setattr(win, "_render_category_photos", lambda *args, **kwargs: rendered.append(args))

    win._cat_active_tokens[1] = 1
    win._current_random_cat_id = 2
    win._on_category_loaded(1, 1, [{"id": 1}], {})

    assert rendered == []


def test_refresh_result_for_current_category_replaces_cache_view(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    rendered = []
    monkeypatch.setattr(
        win,
        "_render_category_photos",
        lambda index, cat_id, photos, metrics, **kwargs: rendered.append((cat_id, photos)),
    )

    win._cat_active_tokens[1] = 3
    win._cat_request_modes[3] = "refresh"
    win._current_random_cat_id = 1
    win._on_category_loaded(3, 1, [{"id": 99}], {"total_ms": 1.0})

    assert rendered == [(1, [{"id": 99}])]


def test_refresh_result_for_old_category_updates_cache_without_render(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    rendered = []
    monkeypatch.setattr(win, "_render_category_photos", lambda *args, **kwargs: rendered.append(args))

    win._cat_active_tokens[1] = 3
    win._cat_request_modes[3] = "refresh"
    win._current_random_cat_id = 2
    win._on_category_loaded(3, 1, [{"id": 99}], {"total_ms": 1.0})

    key = win._category_visible_cache_key(1, False, None)
    assert win._cat_visible_cache[key]["first_items"] == [{"id": 99}]
    assert rendered == []


def test_loaded_current_result_seeds_same_category_visible_cache(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    monkeypatch.setattr(win, "_render_category_photos", lambda *args, **kwargs: None)

    win._cat_active_tokens[1] = 1
    win._current_random_cat_id = 1
    win._on_category_loaded(1, 1, [{"id": 1}], {"total_ms": 1.0})

    key = win._category_visible_cache_key(1, False, None)
    assert win._cat_visible_cache[key]["first_items"] == [{"id": 1}]


def test_first_screen_limit_applies(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    monkeypatch.setattr(app_mod, "record_shown_photos", lambda photos, cat_id: None)
    photos = [{"id": i} for i in range(app_mod.RANDOM_FIRST_PAGE_SIZE + 25)]

    win._render_category_photos(0, 1, photos, {}, from_cache=False)

    assert len(win.pages[0].loaded_photos) == app_mod.RANDOM_FIRST_PAGE_SIZE
    assert win._cat_offsets[1] == app_mod.RANDOM_FIRST_PAGE_SIZE
    assert win._cat_all_loaded[1] is False
    assert win.pages[0]._scroll_bar.value == 0
    assert win._random_first_render_done is True


def test_render_schedules_adjacent_prefetch_immediately(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    scheduled = []
    win._schedule_category_prefetch = lambda index, delay_ms=250, retry_count=0: scheduled.append((index, delay_ms, retry_count))

    win._render_category_photos(0, 1, [{"id": 1}], {}, from_cache=False)

    assert scheduled == [(0, 0, 0)]


def test_background_waits_while_random_first_render_is_busy(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    win._random_first_render_done = False
    win._cat_workers[1] = _RunningPrefetch()

    assert win.is_random_ready_for_background() is False

def test_sample_first_screen_limit_is_doubled(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    monkeypatch.setattr(app_mod, "record_shown_photos", lambda photos, cat_id: None)
    photos = [{"id": i} for i in range(app_mod.RANDOM_SAMPLE_FIRST_PAGE_SIZE + 25)]

    win._render_category_photos(1, app_mod.CATEGORY_SAMPLE, photos, {}, from_cache=False)

    assert len(win.pages[1].loaded_photos) == app_mod.RANDOM_SAMPLE_FIRST_PAGE_SIZE
    assert win._cat_offsets[app_mod.CATEGORY_SAMPLE] == app_mod.RANDOM_SAMPLE_FIRST_PAGE_SIZE


def test_background_can_start_after_random_first_render(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    win._random_first_render_done = True
    win._cat_workers[1] = _RunningPrefetch()

    assert win.is_random_ready_for_background() is True


def test_background_waits_for_random_prefetch_after_first_render(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    win._random_first_render_done = True
    win._cat_prefetch_workers[2] = _RunningPrefetch()

    assert win.is_random_ready_for_background() is False


def test_load_more_stops_at_end_without_reshuffle(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    monkeypatch.setattr(app_mod, "record_shown_photos", lambda photos, cat_id: None)
    win._cat_photos[1] = [{"id": 1}, {"id": 2}]
    win._cat_offsets[1] = 2
    win._cat_all_loaded[1] = True
    win._cat_shown_ids[1] = {1, 2}

    win._on_load_more(1)

    assert win.pages[0].all_loaded is True
    assert win.pages[0].appended_photos == []
    assert win.pages[0].reset_for_shuffle_called is False
    assert win._cat_offsets[1] == 2



def test_load_more_starts_scroll_batch_when_local_pool_is_exhausted(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    _FakeMoreWorker.started.clear()
    monkeypatch.setattr(app_mod, "CategoryMoreWorker", _FakeMoreWorker)
    win._cat_photos[1] = [{"id": 1}, {"id": 2}, {"id": 3}]
    win._cat_offsets[1] = 3
    win._cat_total_counts[1] = 20
    win._cat_all_loaded[1] = False
    win._cat_shown_ids[1] = {1, 2, 3}

    win._on_load_more(1)

    assert len(_FakeMoreWorker.started) == 1
    worker = _FakeMoreWorker.started[0]
    assert worker.was_started is True
    assert worker.cat_id == 1
    assert worker.exclude_ids == {1, 2, 3}
    assert worker.limit == app_mod._random_scroll_batch_size(1)
    assert win.pages[0].all_loaded is False


def test_scroll_batch_appends_new_photos_without_reset(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    recorded = []
    win._record_shown_photos_async = lambda photos, cat_id: recorded.append((cat_id, list(photos)))
    win._current_random_cat_id = 1
    win._cat_photos[1] = [{"id": 1}, {"id": 2}, {"id": 3}]
    win._cat_offsets[1] = 3
    win._cat_total_counts[1] = 9
    win._cat_all_loaded[1] = False
    win._cat_shown_ids[1] = {1, 2, 3}
    win._cat_more_tokens[1] = 5
    win._cat_result_cache[(1, False)] = {
        "version": ("v1",),
        "photos": list(win._cat_photos[1]),
        "total": 9,
        "metrics": {"partial": True},
    }

    win._on_category_more_loaded(5, 1, [{"id": 2}, {"id": 4}, {"id": 5}, {"id": 6}, {"id": 7}], {"total_ms": 3.0})

    assert win.pages[0].appended_photos == [{"id": 4}, {"id": 5}, {"id": 6}, {"id": 7}]
    assert win._cat_offsets[1] == 7
    assert win._cat_all_loaded[1] is False
    assert [p["id"] for p in win._cat_result_cache[(1, False)]["photos"]] == [1, 2, 3, 4, 5, 6, 7]
    assert recorded == [(1, [{"id": 4}, {"id": 5}, {"id": 6}, {"id": 7}])]


def test_scroll_batch_extends_estimated_total(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    monkeypatch.setattr(app_mod, "record_shown_photos", lambda photos, cat_id: None)
    win._current_random_cat_id = 1
    win._cat_photos[1] = [{"id": 1}, {"id": 2}, {"id": 3}]
    win._cat_offsets[1] = 3
    win._cat_total_counts[1] = 4
    win._cat_all_loaded[1] = False
    win._cat_shown_ids[1] = {1, 2, 3}
    win._cat_more_tokens[1] = 5
    win._cat_result_cache[(1, False)] = {
        "version": ("v1",),
        "photos": list(win._cat_photos[1]),
        "total": 4,
        "metrics": {"partial": True},
    }

    win._on_category_more_loaded(5, 1, [{"id": 4}, {"id": 5}], {"total_ms": 3.0})

    assert win._cat_total_counts[1] == 6
    assert win._cat_all_loaded[1] is False
    assert win._cat_result_cache[(1, False)]["total"] == 6


def test_empty_scroll_batch_marks_partial_cache_complete():
    import ui.app as app_mod

    win = _make_window(app_mod)
    win._current_random_cat_id = 1
    win._cat_photos[1] = [{"id": 1}, {"id": 2}, {"id": 3}]
    win._cat_offsets[1] = 3
    win._cat_total_counts[1] = 4
    win._cat_all_loaded[1] = False
    win._cat_more_tokens[1] = 5
    win._cat_result_cache[(1, False)] = {
        "version": ("v1",),
        "photos": list(win._cat_photos[1]),
        "total": 4,
        "metrics": {"partial": True},
    }

    win._on_category_more_loaded(5, 1, [], {"total_ms": 3.0})

    cached = win._cat_result_cache[(1, False)]
    assert win._cat_all_loaded[1] is True
    assert win._cat_total_counts[1] == 3
    assert cached["total"] == 3
    assert cached["metrics"]["partial"] is False
    assert cached["metrics"]["cache_stage"] == "scroll_complete_result"
    assert win.pages[0].all_loaded is True


def test_load_category_resets_scroll_immediately(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    _FakeWorker.started.clear()
    monkeypatch.setattr(app_mod, "CategoryLoadWorker", _FakeWorker)
    win.pages[0]._scroll_bar.value = 300

    win.load_category(0)

    assert win.pages[0]._scroll_bar.value == 0


def test_partial_result_cache_without_visible_cache_starts_foreground_worker(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    _FakeWorker.started.clear()
    monkeypatch.setattr(app_mod, "CategoryLoadWorker", _FakeWorker)
    monkeypatch.setattr(app_mod, "record_shown_photos", lambda photos, cat_id: None)
    win._cat_result_cache[(1, False)] = {
        "created_at": time.monotonic(),
        "photos": [{"id": 7}],
        "metrics": {"partial": True},
    }

    win.load_category(0)

    assert len(_FakeWorker.started) == 1
    assert win.pages[0].loaded_photos == []


def test_full_result_cache_hit_renders_complete_cached_photos(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    rendered = []
    _FakeWorker.started.clear()
    monkeypatch.setattr(app_mod, "CategoryLoadWorker", _FakeWorker)
    monkeypatch.setattr(app_mod, "record_shown_photos", lambda photos, cat_id: None)
    monkeypatch.setattr(
        win,
        "_render_category_photos",
        lambda index, cat_id, photos, metrics, **kwargs: rendered.append((cat_id, photos, metrics, kwargs)),
    )
    win._cat_result_cache[(1, False)] = {
        "created_at": time.monotonic(),
        "version": ("v1",),
        "photos": [{"id": 7}, {"id": 8}],
        "total": 2,
        "metrics": {"total_ms": 2500.0, "batch_ms": 1800.0},
    }

    win.load_category(0)

    assert rendered == [(1, [{"id": 7}, {"id": 8}], {
        "total_ms": 0.0,
        "batch_ms": 0.0,
        "cache_stage": "full_cache_hit",
        "memory_ms": 0.0,
    }, {"from_cache": True, "display_total": 2, "schedule_prefetch": False})]
    assert _FakeWorker.started == []


def test_rendered_cache_hit_reuses_page_without_reload(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    _FakeWorker.started.clear()
    monkeypatch.setattr(app_mod, "CategoryLoadWorker", _FakeWorker)
    monkeypatch.setattr(win, "_schedule_category_prefetch", lambda *args, **kwargs: None)
    win.pages[0].loaded_photos = [{"id": 7}]
    win.pages[0]._scroll_bar.value = 360
    win._cat_photos[1] = [{"id": 7}]
    win._cat_rendered_pages.add(1)
    win._cat_result_cache[(1, False)] = {
        "created_at": time.monotonic(),
        "version": ("v1",),
        "photos": [{"id": 7}],
        "total": 1,
        "metrics": {},
    }

    win.load_category(0)

    assert win.pages[0].loaded_photos == [{"id": 7}]
    assert win.pages[0]._scroll_bar.value == 360
    assert _FakeWorker.started == []


def test_full_result_cache_hit_does_not_query_db_version(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    _FakeWorker.started.clear()
    win._random_category_db_version = lambda: (_ for _ in ()).throw(AssertionError("db version should not be queried"))
    monkeypatch.setattr(app_mod, "CategoryLoadWorker", _FakeWorker)
    monkeypatch.setattr(app_mod, "record_shown_photos", lambda photos, cat_id: None)
    win._cat_result_cache[(1, False)] = {
        "created_at": time.monotonic(),
        "version": ("old",),
        "photos": [{"id": 7}],
        "total": 1,
        "metrics": {},
    }

    win.load_category(0)

    assert win.pages[0].loaded_photos == [{"id": 7}]
    assert _FakeWorker.started == []


def test_prefetch_visible_cache_hit_renders_current_category(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    _FakeWorker.started.clear()
    monkeypatch.setattr(app_mod, "CategoryLoadWorker", _FakeWorker)
    monkeypatch.setattr(app_mod, "record_shown_photos", lambda photos, cat_id: None)
    win._random_category_db_version = lambda: (_ for _ in ()).throw(AssertionError("db version should not be queried"))
    key = win._category_visible_cache_key(1, False, None)
    win._cat_visible_cache[key] = {
        "first_items": [{"id": 11}],
        "total": 123,
        "generated_at": time.monotonic(),
        "query_ms": 5.0,
        "version": ("v1",),
    }

    win.load_category(0)

    assert win.pages[0].loaded_photos == [{"id": 11}]
    assert win._cat_all_loaded[1] is False
    assert _FakeWorker.started == []


def test_prefetch_cache_hit_invalidates_existing_foreground_worker(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    _FakeWorker.started.clear()
    running = _RunningPrefetch()
    win._cat_workers[1] = running
    win._cat_load_token = 7
    win._cat_active_tokens[1] = 7
    win._cat_request_modes[7] = "foreground"
    monkeypatch.setattr(app_mod, "CategoryLoadWorker", _FakeWorker)
    monkeypatch.setattr(app_mod, "record_shown_photos", lambda photos, cat_id: None)
    key = win._category_visible_cache_key(1, False, None)
    win._cat_visible_cache[key] = {
        "first_items": [{"id": 11}],
        "total": 123,
        "generated_at": time.monotonic(),
        "query_ms": 5.0,
        "version": ("v1",),
    }

    win.load_category(0)

    assert running.interrupted is True
    assert 1 not in win._cat_active_tokens
    assert _FakeWorker.started == []


def test_prefetch_cache_hit_keeps_existing_offscreen_refresh(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    _FakeWorker.started.clear()
    running = _RunningPrefetch()
    win._cat_workers[1] = running
    win._cat_load_token = 7
    win._cat_active_tokens[1] = 7
    win._cat_request_modes[7] = "offscreen_refresh"
    monkeypatch.setattr(app_mod, "CategoryLoadWorker", _FakeWorker)
    monkeypatch.setattr(app_mod, "record_shown_photos", lambda photos, cat_id: None)
    key = win._category_visible_cache_key(1, False, None)
    win._cat_visible_cache[key] = {
        "first_items": [{"id": 11}],
        "total": 123,
        "generated_at": time.monotonic(),
        "query_ms": 5.0,
        "version": ("v1",),
    }

    win.load_category(0)

    assert running.interrupted is False
    assert win._cat_active_tokens[1] == 7
    assert _FakeWorker.started == []


def test_switch_cache_hit_does_not_start_extra_refresh(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    win._current_random_cat_id = 1
    _FakeWorker.started.clear()
    monkeypatch.setattr(app_mod, "CategoryLoadWorker", _FakeWorker)
    monkeypatch.setattr(app_mod, "record_shown_photos", lambda photos, cat_id: None)
    key = win._category_visible_cache_key(2, False, ("v1",))
    win._cat_visible_cache[key] = {
        "first_items": [{"id": 22}],
        "total": 50,
        "generated_at": time.monotonic(),
        "query_ms": 3.0,
        "version": ("v1",),
    }

    win.load_category(1)

    assert win.pages[1].loaded_photos == [{"id": 22}]
    assert _FakeWorker.started == []


def test_offscreen_refresh_updates_cache_without_render(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    rendered = []
    monkeypatch.setattr(win, "_render_category_photos", lambda *args, **kwargs: rendered.append(args))

    win._current_random_cat_id = 2
    win._cat_active_tokens[1] = 4
    win._cat_request_modes[4] = "offscreen_refresh"
    win._on_category_loaded(4, 1, [{"id": 101}], {"total_ms": 2.0})

    key = win._category_visible_cache_key(1, False, None)
    assert win._cat_visible_cache[key]["first_items"] == [{"id": 101}]
    assert rendered == []


def test_visible_cache_with_old_version_renders_without_refresh(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    win._random_category_db_version = lambda: (_ for _ in ()).throw(AssertionError("db version should not be queried"))
    _FakeWorker.started.clear()
    monkeypatch.setattr(app_mod, "CategoryLoadWorker", _FakeWorker)
    monkeypatch.setattr(app_mod, "record_shown_photos", lambda photos, cat_id: None)
    key = win._category_visible_cache_key(1, False, None)
    win._cat_visible_cache[key] = {
        "first_items": [{"id": 11}],
        "total": 123,
        "generated_at": time.monotonic(),
        "query_ms": 5.0,
        "version": ("v1",),
    }

    win.load_category(0)

    assert win.pages[0].loaded_photos == [{"id": 11}]
    assert _FakeWorker.started == []


def test_prefetch_worker_uses_limited_rank_query(monkeypatch):
    import ui.app as app_mod

    class FakeConn:
        def close(self):
            pass

    conn = FakeConn()
    calls = []
    monkeypatch.setattr(app_mod, "Database", lambda: type("FakeDb", (), {"get_persistent_connection": lambda self: conn})())
    monkeypatch.setattr(app_mod, "rank_category_photos", lambda db, cat_id, limit=None: calls.append((db, cat_id, limit)) or [{"id": 1}])

    emitted = []
    worker = app_mod.CategoryPrefetchWorker(2, False, ("v1",), 0, limit=123)
    worker.prefetched.connect(lambda *args: emitted.append(args))
    worker.run()

    assert calls == [(conn, 2, 123)]
    assert emitted[0][5] == 2


def test_category_load_worker_uses_estimated_total_for_limited_starred_query(monkeypatch):
    import ui.app as app_mod

    class FakeConn:
        def close(self):
            pass

    conn = FakeConn()
    calls = []
    monkeypatch.setattr(app_mod, "Database", lambda: type("FakeDb", (), {"get_persistent_connection": lambda self: conn})())
    monkeypatch.setattr(
        app_mod,
        "load_starred_photos",
        lambda db, cat_id, limit=None: calls.append((db, cat_id, limit)) or [{"id": 1}, {"id": 2}],
    )

    emitted = []
    worker = app_mod.CategoryLoadWorker(7, 2, True, limit=123)
    worker.loaded.connect(lambda *args: emitted.append(args))
    worker.run()

    assert calls == [(conn, 2, 123)]
    assert emitted[0][3]["display_total"] == 3
    assert emitted[0][3]["display_total_estimated"] is True


def test_prefetch_worker_uses_limited_starred_query(monkeypatch):
    import ui.app as app_mod

    class FakeConn:
        def close(self):
            pass

    conn = FakeConn()
    calls = []
    monkeypatch.setattr(app_mod, "Database", lambda: type("FakeDb", (), {"get_persistent_connection": lambda self: conn})())
    monkeypatch.setattr(app_mod, "load_starred_photos", lambda db, cat_id, limit=None: calls.append((db, cat_id, limit)) or [{"id": 1}])

    emitted = []
    worker = app_mod.CategoryPrefetchWorker(2, True, ("v1",), 0, limit=123)
    worker.prefetched.connect(lambda *args: emitted.append(args))
    worker.run()

    assert calls == [(conn, 2, 123)]
    assert emitted[0][5] == 2

def test_more_worker_uses_limited_starred_query_with_exclusions(monkeypatch):
    import ui.app as app_mod

    class FakeConn:
        def close(self):
            pass

    conn = FakeConn()
    calls = []
    monkeypatch.setattr(app_mod, "Database", lambda: type("FakeDb", (), {"get_persistent_connection": lambda self: conn})())
    monkeypatch.setattr(
        app_mod,
        "load_starred_photos",
        lambda db, cat_id, limit=None, exclude_ids=None: calls.append((db, cat_id, limit, set(exclude_ids or []))) or [{"id": 5}],
    )

    worker = app_mod.CategoryMoreWorker(9, 2, True, exclude_ids={1, 3}, limit=123)
    worker.run()

    assert calls == [(conn, 2, 123, {1, 3})]

def test_prefetch_result_cache_is_partial_when_limited(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    win._random_category_db_version = lambda: (_ for _ in ()).throw(AssertionError("db version should not be queried"))

    win._on_category_prefetched(2, False, ("v1",), 0, [{"id": 21}], 77, 9.0)

    cached = win._cat_result_cache[(2, False)]
    assert cached["metrics"]["partial"] is True
    assert cached["metrics"]["cache_stage"] == "prefetch_partial_result"
    assert cached["total"] == 77

def test_prefetch_result_for_other_category_only_stores_cache(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    win._current_random_cat_id = 1
    rendered = []
    monkeypatch.setattr(win, "_render_category_photos", lambda *args, **kwargs: rendered.append(args))

    win._on_category_prefetched(2, False, ("v1",), 0, [{"id": 21}], 77, 9.0)

    key = win._category_visible_cache_key(2, False, ("v1",))
    assert win._cat_visible_cache[key]["first_items"] == [{"id": 21}]
    assert rendered == []


def test_prefetch_old_generation_is_discarded(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    win._cat_prefetch_generation = 2
    win._current_random_cat_id = 2
    rendered = []
    monkeypatch.setattr(win, "_render_category_photos", lambda *args, **kwargs: rendered.append(args))

    win._on_category_prefetched(2, False, ("v1",), 1, [{"id": 21}], 77, 9.0)

    assert win._cat_visible_cache == {}
    assert rendered == []


def test_prefetch_result_for_current_category_only_updates_cache(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    win._current_random_cat_id = 2
    rendered = []
    monkeypatch.setattr(
        win,
        "_render_category_photos",
        lambda index, cat_id, photos, metrics, **kwargs: rendered.append((index, cat_id, photos, kwargs)),
    )

    win._on_category_prefetched(2, False, ("v1",), 0, [{"id": 21}], 77, 9.0)

    key = win._category_visible_cache_key(2, False, ("v1",))
    assert win._cat_visible_cache[key]["first_items"] == [{"id": 21}]
    assert rendered == []


def test_render_schedules_adjacent_category_prefetch(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    _FakePrefetchWorker.started.clear()
    monkeypatch.setattr(app_mod, "CategoryPrefetchWorker", _FakePrefetchWorker)
    monkeypatch.setattr(app_mod, "record_shown_photos", lambda photos, cat_id: None)
    monkeypatch.setattr(win, "_is_background_busy_for_prefetch", lambda: False)
    win._random_category_db_version = lambda: (_ for _ in ()).throw(AssertionError("db version should not be queried"))

    win._render_category_photos(0, 1, [{"id": 1}], {}, from_cache=False, schedule_prefetch=False)
    win._start_category_prefetch(0, win._cat_prefetch_generation)

    assert len(_FakePrefetchWorker.started) == 1
    assert _FakePrefetchWorker.started[0].cat_id == 2
    assert _FakePrefetchWorker.started[0].limit == app_mod._random_initial_pool_size(app_mod.CATEGORY_SAMPLE)


def test_load_category_prefetches_adjacent_category_after_foreground_render(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    _FakeWorker.started.clear()
    _FakePrefetchWorker.started.clear()
    monkeypatch.setattr(app_mod, "CategoryLoadWorker", _FakeWorker)
    monkeypatch.setattr(app_mod, "CategoryPrefetchWorker", _FakePrefetchWorker)
    monkeypatch.setattr(app_mod.QTimer, "singleShot", lambda _ms, callback: callback())
    monkeypatch.setattr(win, "_is_background_busy_for_prefetch", lambda: False)

    win.load_category(0)

    assert len(_FakeWorker.started) == 1
    assert _FakePrefetchWorker.started == []

    worker = _FakeWorker.started[0]
    win._current_random_cat_id = 1
    monkeypatch.setattr(app_mod, "record_shown_photos", lambda photos, cat_id: None)
    win._on_category_loaded(worker.token, 1, [{"id": 1}], {"total_ms": 1.0})

    assert len(_FakePrefetchWorker.started) == 1
    assert _FakePrefetchWorker.started[0].cat_id == 2


def test_load_category_keeps_existing_prefetch_running(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    running = _RunningPrefetch()
    win._cat_prefetch_workers[2] = running
    win._cat_prefetch_generation = 3
    _FakeWorker.started.clear()
    monkeypatch.setattr(app_mod, "CategoryLoadWorker", _FakeWorker)

    win.load_category(0)

    assert win._cat_prefetch_generation == 3
    assert running.interrupted is False
    assert win._cat_prefetch_workers[2] is running


def test_prefetch_skips_when_background_busy(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    _FakePrefetchWorker.started.clear()
    monkeypatch.setattr(app_mod, "CategoryPrefetchWorker", _FakePrefetchWorker)
    monkeypatch.setattr(win, "_is_background_busy_for_prefetch", lambda: True)

    win._start_category_prefetch(0, win._cat_prefetch_generation)

    assert _FakePrefetchWorker.started == []


def test_version_cache_hit_renders_without_refresh_worker(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    _FakeWorker.started.clear()
    monkeypatch.setattr(app_mod, "CategoryLoadWorker", _FakeWorker)
    monkeypatch.setattr(app_mod, "record_shown_photos", lambda photos, cat_id: None)
    win._cat_result_cache[(1, False)] = {
        "created_at": 0,
        "version": ("v1",),
        "photos": [{"id": 8}],
        "metrics": {},
    }

    win.load_category(0)

    assert _FakeWorker.started == []
    assert win.pages[0].loaded_photos == [{"id": 8}]


def test_full_cache_with_old_version_renders_without_refresh(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    win._random_category_db_version = lambda: (_ for _ in ()).throw(AssertionError("db version should not be queried"))
    _FakeWorker.started.clear()
    monkeypatch.setattr(app_mod, "CategoryLoadWorker", _FakeWorker)
    monkeypatch.setattr(app_mod, "record_shown_photos", lambda photos, cat_id: None)
    win._cat_result_cache[(1, False)] = {
        "created_at": 0,
        "version": ("v1",),
        "photos": [{"id": 8}],
        "metrics": {},
    }

    win.load_category(0)

    assert _FakeWorker.started == []
    assert win.pages[0].loaded_photos == [{"id": 8}]


def test_siglip_batch_builder_stops_before_next_batch():
    import ui.app as app_mod

    calls = []

    def generate(batch):
        calls.append(list(batch))
        return {fid: ["tag"] for fid in batch}

    def should_stop():
        return len(calls) >= 1

    pending, processed, stopped = app_mod._build_siglip_tag_rows(
        [1, 2, 3, 4],
        generate,
        should_stop,
        batch_size=2,
    )

    assert calls == [[1, 2]]
    assert processed == 2
    assert stopped is True
    assert pending == []


def test_background_next_batch_schedule_decision():
    import ui.app as app_mod

    assert app_mod._should_schedule_background_next(remaining=10, stopped=False, batches_run=0) is True
    assert app_mod._should_schedule_background_next(remaining=0, stopped=False, batches_run=0) is False
    assert app_mod._should_schedule_background_next(remaining=10, stopped=True, batches_run=0) is False
    assert app_mod._should_schedule_background_next(remaining=10, stopped=False, batches_run=3, max_batches=3) is False


def test_background_next_delay_cools_down_instead_of_stopping():
    import ui.app as app_mod

    assert app_mod._background_next_delay_ms(remaining=10, stopped=False, batches_run=0, max_batches=3, batch_delay_ms=1000) == 1000
    assert app_mod._background_next_delay_ms(remaining=10, stopped=False, batches_run=3, max_batches=3, batch_delay_ms=1000) == 5000
    assert app_mod._background_next_delay_ms(remaining=0, stopped=False, batches_run=3, max_batches=3, batch_delay_ms=1000) is None
    assert app_mod._background_next_delay_ms(remaining=10, stopped=True, batches_run=3, max_batches=3, batch_delay_ms=1000) is None
