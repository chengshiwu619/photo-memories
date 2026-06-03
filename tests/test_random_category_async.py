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


class _FakePage:
    def __init__(self):
        self.loaded_photos = None

    def load_photos(self, photos):
        self.loaded_photos = list(photos)


def _make_window(app_mod):
    win = app_mod.MainWindow.__new__(app_mod.MainWindow)
    win.pages = [_FakePage(), _FakePage()]
    win.starred_only = False
    win._cat_result_cache = {}
    win._cat_load_token = 0
    win._cat_active_tokens = {}
    win._cat_workers = {}
    win._cat_offsets = {}
    win._cat_all_loaded = {}
    win._cat_shown_ids = {}
    win._cat_photos = {}
    win._random_category_db_version = lambda: ("v1",)
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
    assert win.pages[0].loaded_photos is None


def test_load_category_reuses_existing_photos_immediately(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    _FakeWorker.started.clear()
    win._cat_photos[1] = [{"id": i} for i in range(app_mod.RANDOM_FIRST_PAGE_SIZE + 10)]
    monkeypatch.setattr(app_mod, "CategoryLoadWorker", _FakeWorker)

    win.load_category(0)

    assert len(win.pages[0].loaded_photos) == app_mod.RANDOM_FIRST_PAGE_SIZE
    assert len(_FakeWorker.started) == 1


def test_old_category_worker_result_is_ignored(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    rendered = []
    monkeypatch.setattr(win, "_render_category_photos", lambda *args, **kwargs: rendered.append(args))

    win._cat_active_tokens[1] = 2
    win._on_category_loaded(1, 1, [{"id": 1}], {})

    assert rendered == []


def test_first_screen_limit_applies(monkeypatch):
    import ui.app as app_mod

    win = _make_window(app_mod)
    monkeypatch.setattr(app_mod, "record_shown_photos", lambda photos, cat_id: None)
    photos = [{"id": i} for i in range(app_mod.RANDOM_FIRST_PAGE_SIZE + 25)]

    win._render_category_photos(0, 1, photos, {}, from_cache=False)

    assert len(win.pages[0].loaded_photos) == app_mod.RANDOM_FIRST_PAGE_SIZE
    assert win._cat_offsets[1] == app_mod.RANDOM_FIRST_PAGE_SIZE
    assert win._cat_all_loaded[1] is False


def test_cache_hit_does_not_start_worker(monkeypatch):
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

    assert _FakeWorker.started == []
    assert win.pages[0].loaded_photos == [{"id": 7}]


def test_visible_cache_hit_uses_current_metrics_not_cached_old_metrics(monkeypatch):
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

    assert rendered
    assert rendered[0]["cache_stage"] == "visible_cache_hit"
    assert rendered[0]["batch_ms"] == 0.0
    assert rendered[0]["total_ms"] < 100.0


def test_version_cache_hit_does_not_refresh_worker(monkeypatch):
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
