from types import SimpleNamespace


def test_resolve_ai_device_cpu_forces_cpu(monkeypatch):
    from services.ai_device import resolve_ai_device

    result = resolve_ai_device(SimpleNamespace(ai_device="cpu"))

    assert result.device == "cpu"


def test_resolve_ai_device_cuda_falls_back_when_unavailable(monkeypatch):
    from services.ai_device import resolve_ai_device

    class _Cuda:
        @staticmethod
        def is_available():
            return False

    class _Torch:
        cuda = _Cuda()

    monkeypatch.setitem(__import__("sys").modules, "torch", _Torch())

    result = resolve_ai_device(SimpleNamespace(ai_device="cuda"))

    assert result.requested == "cuda"
    assert result.device == "cpu"
    assert result.gpu_available is False
