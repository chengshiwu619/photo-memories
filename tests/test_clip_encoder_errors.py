import importlib
import sys
import types


class _CaptureLogger:
    def __init__(self):
        self.warnings = []
        self.errors = []

    def warning(self, message, *args):
        self.warnings.append(message % args if args else message)

    def error(self, message, *args):
        self.errors.append(message % args if args else message)

    def info(self, *args, **kwargs):
        pass


def _reload_clip_encoder(monkeypatch):
    monkeypatch.delitem(sys.modules, "infra.image.clip_encoder", raising=False)
    import infra.image.clip_encoder as ce

    return importlib.reload(ce)


def test_open_clip_missing_reports_dependency_once(monkeypatch):
    real_import = __import__
    logger = _CaptureLogger()

    def fake_import(name, *args, **kwargs):
        if name == "open_clip":
            raise ModuleNotFoundError("No module named 'open_clip'", name="open_clip")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    ce = _reload_clip_encoder(monkeypatch)
    monkeypatch.setattr(ce, "logger", logger)

    assert ce._load_model() is False
    assert ce._load_model() is False

    missing = [msg for msg in logger.warnings if "open_clip 未安装" in msg]
    assert len(missing) == 1
    assert logger.errors == []


def test_open_clip_present_model_load_failure_is_not_dependency_warning(monkeypatch):
    ce = _reload_clip_encoder(monkeypatch)
    logger = _CaptureLogger()

    fake_open_clip = types.SimpleNamespace(
        create_model_and_transforms=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("hf download failed")),
        get_tokenizer=lambda *args, **kwargs: object(),
    )
    fake_torch = types.SimpleNamespace(
        __version__="2.5.1+cu121",
        cuda=types.SimpleNamespace(is_available=lambda: True),
    )
    monkeypatch.setitem(sys.modules, "open_clip", fake_open_clip)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setattr(ce, "logger", logger)

    assert ce._load_model(preferred_device="cuda") is False

    assert not any("open_clip 未安装" in msg for msg in logger.warnings)
    assert len(logger.errors) == 1
    error = logger.errors[0]
    assert "model_load_failed" in error
    assert "cuda" in error
    assert "2.5.1+cu121" in error
    assert "cuda_available=True" in error
    assert "open_clip_imported=True" in error
    assert "hf download failed" in error


def test_open_clip_present_importerror_during_model_load_is_model_failure(monkeypatch):
    ce = _reload_clip_encoder(monkeypatch)
    logger = _CaptureLogger()

    fake_open_clip = types.SimpleNamespace(
        create_model_and_transforms=lambda *args, **kwargs: (_ for _ in ()).throw(ImportError("huggingface_hub cache error")),
        get_tokenizer=lambda *args, **kwargs: object(),
    )
    fake_torch = types.SimpleNamespace(
        __version__="2.5.1+cu121",
        cuda=types.SimpleNamespace(is_available=lambda: True),
    )
    monkeypatch.setitem(sys.modules, "open_clip", fake_open_clip)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setattr(ce, "logger", logger)

    assert ce._load_model(preferred_device="cuda") is False

    assert not any("open_clip 未安装" in msg for msg in logger.warnings)
    assert len(logger.errors) == 1
    assert "model_load_failed" in logger.errors[0]
    assert "huggingface_hub cache error" in logger.errors[0]
