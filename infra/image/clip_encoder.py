import numpy as np
import sys
import warnings
from typing import Optional, List, Tuple

from logger_setup import logger
from infra.image.thumbnail_loader import get_thumbnail_loader


_model = None
_preprocess = None
_tokenizer = None
_device = None
_model_name = "ViT-SO400M-14-SigLIP-384"
_pretrained = "webli"
_missing_open_clip_warned = False
_hf_warning_filters_installed = False


def _install_hf_warning_filters():
    global _hf_warning_filters_installed
    if _hf_warning_filters_installed:
        return
    _hf_warning_filters_installed = True
    warnings.filterwarnings("once", message=".*unauthenticated.*", module="huggingface_hub.*")
    warnings.filterwarnings("once", message=".*symlink.*", module="huggingface_hub.*")


def _reset_model():
    global _model, _preprocess, _tokenizer, _device
    _model = None
    _preprocess = None
    _tokenizer = None
    _device = None


def get_active_device() -> str:
    return _device or "unloaded"


def _torch_runtime_info():
    info = {"torch_version": None, "cuda_available": None}
    try:
        import torch

        info["torch_version"] = getattr(torch, "__version__", None)
        info["cuda_available"] = bool(torch.cuda.is_available())
    except Exception as exc:
        info["torch_error"] = repr(exc)
    return info


def _warn_open_clip_missing_once(exc):
    global _missing_open_clip_warned
    if _missing_open_clip_warned:
        return
    _missing_open_clip_warned = True
    logger.warning("open_clip 未安装, SigLIP 不可用. 安装: pip install open-clip-torch; exception=%r", exc)


def _log_model_load_failed(exc, target_device, open_clip_imported):
    runtime = _torch_runtime_info()
    logger.error(
        "SigLIP model_load_failed: executable=%s device=%s torch_version=%s "
        "cuda_available=%s open_clip_imported=%s model=%s pretrained=%s exception=%r",
        sys.executable,
        target_device,
        runtime.get("torch_version"),
        runtime.get("cuda_available"),
        open_clip_imported,
        _model_name,
        _pretrained,
        exc,
    )


def _import_open_clip():
    try:
        import open_clip

        return open_clip
    except ModuleNotFoundError as exc:
        if exc.name == "open_clip":
            _warn_open_clip_missing_once(exc)
            return None
        raise
    except ImportError as exc:
        if "open_clip" in str(exc):
            _warn_open_clip_missing_once(exc)
            return None
        raise


def _load_model(preferred_device: Optional[str] = None):
    global _model, _preprocess, _tokenizer, _device
    if _model is not None:
        return True
    open_clip = None
    target_device = preferred_device or "unknown"
    try:
        open_clip = _import_open_clip()
        if open_clip is None:
            _reset_model()
            return False

        import torch
        from services.ai_device import resolve_ai_device

        info = resolve_ai_device()
        target_device = preferred_device or info.device
        _install_hf_warning_filters()
        _model, _, _preprocess = open_clip.create_model_and_transforms(_model_name, pretrained=_pretrained)
        _tokenizer = open_clip.get_tokenizer(_model_name)
        try:
            _model = _model.to(target_device)
        except Exception as exc:
            if target_device == "cuda":
                logger.warning(f"SigLIP CUDA 加载失败，降级 CPU: {exc}")
                _model = _model.to("cpu")
                target_device = "cpu"
            else:
                raise
        _model.eval()
        _device = target_device
        logger.info(f"SigLIP 模型加载完成: {_model_name}, device={_device}, cuda_available={torch.cuda.is_available()}")
        return True
    except ModuleNotFoundError as exc:
        if exc.name == "open_clip":
            _warn_open_clip_missing_once(exc)
        else:
            _log_model_load_failed(exc, target_device, open_clip is not None)
        _reset_model()
        return False
    except ImportError as exc:
        if "open_clip" in str(exc) and open_clip is None:
            _warn_open_clip_missing_once(exc)
        else:
            _log_model_load_failed(exc, target_device, open_clip is not None)
        _reset_model()
        return False
    except Exception as e:
        _log_model_load_failed(e, target_device, open_clip is not None)
        _reset_model()
        return False


def is_available() -> bool:
    if _model is not None:
        return True
    return _import_open_clip() is not None


def encode_image(file_id: int) -> Optional[np.ndarray]:
    if not _load_model():
        return None

    loader = get_thumbnail_loader()
    img = loader.load(file_id, size=(384, 384))
    if img is None:
        return None

    try:
        import torch
        with torch.no_grad():
            image_input = _preprocess(img).unsqueeze(0)
            if _device:
                image_input = image_input.to(_device)
            embedding = _model.encode_image(image_input)
            embedding = embedding / embedding.norm(dim=-1, keepdim=True)
            return embedding.cpu().numpy().flatten()
    except Exception as e:
        logger.warning(f"图像编码失败 file_id={file_id}: {e}")
        return None


def encode_images_batch(file_ids: List[int], batch_size: int = 16) -> List[Tuple[int, np.ndarray]]:
    if not _load_model():
        return []

    import torch
    loader = get_thumbnail_loader()
    results = []

    for start in range(0, len(file_ids), batch_size):
        batch_ids = file_ids[start:start + batch_size]
        images = []
        valid_ids = []
        for fid in batch_ids:
            img = loader.load(fid, size=(384, 384))
            if img is not None:
                images.append(_preprocess(img))
                valid_ids.append(fid)

        if not images:
            continue

        try:
            with torch.no_grad():
                batch_tensor = torch.stack(images)
                if _device:
                    batch_tensor = batch_tensor.to(_device)
                embeddings = _model.encode_image(batch_tensor)
                embeddings = embeddings / embeddings.norm(dim=-1, keepdim=True)
                embeddings_np = embeddings.cpu().numpy()

            for i, fid in enumerate(valid_ids):
                results.append((fid, embeddings_np[i].flatten()))
        except Exception as e:
            logger.warning(f"批量编码失败 (batch {start}): {e}")

    return results


def encode_text(texts: List[str]) -> Optional[np.ndarray]:
    if not _load_model():
        return None

    try:
        import torch
        with torch.no_grad():
            tokens = _tokenizer(texts)
            if _device:
                tokens = tokens.to(_device)
            embeddings = _model.encode_text(tokens)
            embeddings = embeddings / embeddings.norm(dim=-1, keepdim=True)
            return embeddings.cpu().numpy()
    except Exception as e:
        logger.warning(f"文本编码失败: {e}")
        return None


def compute_similarity(image_embedding: np.ndarray, text_embeddings: np.ndarray) -> np.ndarray:
    return (image_embedding @ text_embeddings.T)
