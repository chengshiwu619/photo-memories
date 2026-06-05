import time


class _FakeSignal:
    def __init__(self):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)


class _FakeWorker:
    started = []

    def __init__(self, token, cat_id, starred_only):
        self.token = token
        self.cat_id = cat_id
        self.starred_only = starred_only
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


class _FakePage:
    def __init__(self):
        self.loaded_photos = None
        self._scroll_bar = type("ScrollBar", (), {"value": 99, "setValue": lambda self, value: setattr(self, "value", value)})()
        self.scroll = type("Scroll", (), {"verticalScrollBar": lambda _self: self._scroll_bar})()

    def load_photos(self, photos):
        self.loaded_photos = list(photos)


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
    win._cat_active_tokens = {}
    win._cat_request_modes = {}
    win._cat_workers = {}
    win._cat_visible_cache = {}
    win._cat_prefetch_workers = {}
    win._cat_prefetch_generation = 0
    win._cat_offsets = {}
    win._cat_all_loaded = {}
    win._cat_shown_ids = {}
    win._cat_photos = {}
    win._random_category_db_version = lambda: ("v1",)
    win._current_random_cat_id = None
    return win


def test_load_category_starts_worker_without_sync_recommendation(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    _FakeWorker.started.clear()
    monkeypatch.setattr(app_mod, "CategoryLoadWorker", _FakeWorker)
    monkeypatch.setattr(app_mod, "rank_category_photos", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("sync rank called")))

    win.load_category(0)

    assert len(_FakeWorker.started) == 1
    assert _FakeWorker.started[0].was_started is True
    assert win.pages[0].loaded_photos == []


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

    key = win._category_visible_cache_key(1, False, ("v1",))
    assert win._cat_visible_cache[key]["first_items"] == [{"id": 99}]
    assert rendered == []


def test_loaded_current_result_seeds_same_category_visible_cache(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    monkeypatch.setattr(win, "_render_category_photos", lambda *args, **kwargs: None)

    win._cat_active_tokens[1] = 1
    win._current_random_cat_id = 1
    win._on_category_loaded(1, 1, [{"id": 1}], {"total_ms": 1.0})

    key = win._category_visible_cache_key(1, False, ("v1",))
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


def test_sample_first_screen_limit_is_doubled(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    monkeypatch.setattr(app_mod, "record_shown_photos", lambda photos, cat_id: None)
    photos = [{"id": i} for i in range(app_mod.RANDOM_SAMPLE_FIRST_PAGE_SIZE + 25)]

    win._render_category_photos(1, app_mod.CATEGORY_SAMPLE, photos, {}, from_cache=False)

    assert len(win.pages[1].loaded_photos) == app_mod.RANDOM_SAMPLE_FIRST_PAGE_SIZE
    assert win._cat_offsets[app_mod.CATEGORY_SAMPLE] == app_mod.RANDOM_SAMPLE_FIRST_PAGE_SIZE


def test_load_category_resets_scroll_immediately(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    _FakeWorker.started.clear()
    monkeypatch.setattr(app_mod, "CategoryLoadWorker", _FakeWorker)
    win.pages[0]._scroll_bar.value = 300

    win.load_category(0)

    assert win.pages[0]._scroll_bar.value == 0


def test_cache_hit_still_clears_and_starts_worker(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    _FakeWorker.started.clear()
    monkeypatch.setattr(app_mod, "CategoryLoadWorker", _FakeWorker)
    monkeypatch.setattr(app_mod, "record_shown_photos", lambda photos, cat_id: None)
    win._cat_result_cache[(1, False)] = {
        "created_at": time.monotonic(),
        "photos": [{"id": 7}],
        "metrics": {},
    }

    win.load_category(0)

    assert len(_FakeWorker.started) == 1
    assert win.pages[0].loaded_photos == []


def test_cache_hit_does_not_render_cached_old_metrics(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    rendered = []
    monkeypatch.setattr(app_mod, "CategoryLoadWorker", _FakeWorker)
    monkeypatch.setattr(
        win,
        "_render_category_photos",
        lambda index, cat_id, photos, metrics, from_cache=False: rendered.append(metrics),
    )
    win._cat_result_cache[(1, False)] = {
        "created_at": time.monotonic(),
        "version": ("v1",),
        "photos": [{"id": 7}],
        "metrics": {"total_ms": 2500.0, "batch_ms": 1800.0},
    }

    win.load_category(0)

    assert rendered == []


def test_prefetch_visible_cache_hit_renders_current_category(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    _FakeWorker.started.clear()
    monkeypatch.setattr(app_mod, "CategoryLoadWorker", _FakeWorker)
    monkeypatch.setattr(app_mod, "record_shown_photos", lambda photos, cat_id: None)
    key = win._category_visible_cache_key(1, False, ("v1",))
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
    assert len(_FakeWorker.started) == 1
    assert _FakeWorker.started[0].cat_id == 1
    assert win._cat_request_modes[_FakeWorker.started[0].token] == "silent_cache_refresh"


def test_prefetch_cache_hit_invalidates_existing_foreground_worker(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    _FakeWorker.started.clear()
    running = _RunningPrefetch()
    win._cat_workers[1] = running
    win._cat_load_token = 7
    win._cat_active_tokens[1] = 7
    monkeypatch.setattr(app_mod, "CategoryLoadWorker", _FakeWorker)
    monkeypatch.setattr(app_mod, "record_shown_photos", lambda photos, cat_id: None)
    key = win._category_visible_cache_key(1, False, ("v1",))
    win._cat_visible_cache[key] = {
        "first_items": [{"id": 11}],
        "total": 123,
        "generated_at": time.monotonic(),
        "query_ms": 5.0,
        "version": ("v1",),
    }

    win.load_category(0)

    assert running.interrupted is True
    assert win._cat_active_tokens[1] != 7
    assert _FakeWorker.started == []


def test_switch_starts_offscreen_refresh_for_previous_category(monkeypatch):
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
    assert len(_FakeWorker.started) == 2
    modes_by_cat = {worker.cat_id: win._cat_request_modes[worker.token] for worker in _FakeWorker.started}
    assert modes_by_cat[2] == "silent_cache_refresh"
    assert modes_by_cat[1] == "offscreen_refresh"


def test_offscreen_refresh_updates_cache_without_render(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    rendered = []
    monkeypatch.setattr(win, "_render_category_photos", lambda *args, **kwargs: rendered.append(args))

    win._current_random_cat_id = 2
    win._cat_active_tokens[1] = 4
    win._cat_request_modes[4] = "offscreen_refresh"
    win._on_category_loaded(4, 1, [{"id": 101}], {"total_ms": 2.0})

    key = win._category_visible_cache_key(1, False, ("v1",))
    assert win._cat_visible_cache[key]["first_items"] == [{"id": 101}]
    assert rendered == []


def test_prefetch_cache_is_version_isolated(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    win._random_category_db_version = lambda: ("v2",)
    _FakeWorker.started.clear()
    monkeypatch.setattr(app_mod, "CategoryLoadWorker", _FakeWorker)
    key = win._category_visible_cache_key(1, False, ("v1",))
    win._cat_visible_cache[key] = {
        "first_items": [{"id": 11}],
        "total": 123,
        "generated_at": time.monotonic(),
        "query_ms": 5.0,
        "version": ("v1",),
    }

    win.load_category(0)

    assert win.pages[0].loaded_photos == []
    assert len(_FakeWorker.started) == 1


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

    win._render_category_photos(0, 1, [{"id": 1}], {}, from_cache=False, schedule_prefetch=False)
    win._start_category_prefetch(0, win._cat_prefetch_generation)

    assert len(_FakePrefetchWorker.started) == 1
    assert _FakePrefetchWorker.started[0].cat_id == 2
    assert _FakePrefetchWorker.started[0].limit == app_mod.RANDOM_SAMPLE_FIRST_PAGE_SIZE


def test_load_category_immediately_prefetches_adjacent_category(monkeypatch):
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


def test_version_cache_hit_still_refreshes_deterministically(monkeypatch):
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

    assert len(_FakeWorker.started) == 1
    assert win.pages[0].loaded_photos == []


def test_version_cache_miss_starts_refresh(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    win._random_category_db_version = lambda: ("v2",)
    _FakeWorker.started.clear()
    monkeypatch.setattr(app_mod, "CategoryLoadWorker", _FakeWorker)
    win._cat_result_cache[(1, False)] = {
        "created_at": 0,
        "version": ("v1",),
        "photos": [{"id": 8}],
        "metrics": {},
    }

    win.load_category(0)

    assert len(_FakeWorker.started) == 1


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
