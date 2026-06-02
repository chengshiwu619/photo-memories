from dataclasses import dataclass
from typing import Any

from logger_setup import logger


@dataclass(frozen=True)
class AIDeviceInfo:
    requested: str
    device: str
    gpu_available: bool


def resolve_ai_device(settings: Any = None) -> AIDeviceInfo:
    if settings is None:
        from config import get_settings

        settings = get_settings()

    requested = str(getattr(settings, "ai_device", "auto") or "auto").lower().strip()
    if requested not in {"auto", "cuda", "cpu"}:
        requested = "auto"

    try:
        import torch

        gpu_available = bool(torch.cuda.is_available())
    except Exception:
        gpu_available = False

    if requested == "cpu":
        return AIDeviceInfo(requested=requested, device="cpu", gpu_available=gpu_available)

    if requested == "cuda":
        if gpu_available:
            return AIDeviceInfo(requested=requested, device="cuda", gpu_available=True)
        logger.warning("AI device requested cuda but CUDA is unavailable; falling back to CPU")
        return AIDeviceInfo(requested=requested, device="cpu", gpu_available=False)

    return AIDeviceInfo(
        requested=requested,
        device="cuda" if gpu_available else "cpu",
        gpu_available=gpu_available,
    )
