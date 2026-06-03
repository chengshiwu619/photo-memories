from services.background_task_manager import BackgroundTaskManager


class _FakeThread:
    def __init__(self):
        self.stop_requested = False
        self.quit_called = False
        self.waits = []

    def isRunning(self):
        return True

    def request_stop(self):
        self.stop_requested = True

    def quit(self):
        self.quit_called = True

    def wait(self, timeout_ms):
        self.waits.append(timeout_ms)


def test_cancel_all_requests_worker_stop(monkeypatch):
    monkeypatch.setattr(
        "services.background_task_manager.resolve_ai_device",
        lambda: type("Info", (), {"device": "cpu", "gpu_available": False})(),
    )
    manager = BackgroundTaskManager()
    thread = _FakeThread()
    manager.register(thread)

    manager.cancel_all()

    assert thread.stop_requested is True
    assert thread.quit_called is True
    assert thread.waits == [500]
