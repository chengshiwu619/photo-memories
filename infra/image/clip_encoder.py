import numpy as np
from typing import Optional, List, Tuple

from logger_setup import logger
from infra.image.thumbnail_loader import get_thumbnail_loader


_model = None
_preprocess = None
_tokenizer = None
_model_name = "ViT-SO400M-14-SigLIP-384"
_pretrained = "webli"


def _load_model():
    global _model, _preprocess, _tokenizer
    if _model is not None:
        return True
    try:
        import open_clip
        _model, _, _preprocess = open_clip.create_model_and_transforms(_model_name, pretrained=_pretrained)
        _tokenizer = open_clip.get_tokenizer(_model_name)
        _model.eval()
        logger.info(f"SigLIP 模型加载完成: {_model_name}")
        return True
    except ImportError:
        logger.warning("open_clip 未安装, SigLIP 不可用. 安装: pip install open-clip-torch")
        return False
    except Exception as e:
        logger.error(f"SigLIP 模型加载失败: {e}")
        return False


def is_available() -> bool:
    if _model is not None:
        return True
    try:
        import open_clip
        return True
    except ImportError:
        return False


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
            embeddings = _model.encode_text(tokens)
            embeddings = embeddings / embeddings.norm(dim=-1, keepdim=True)
            return embeddings.cpu().numpy()
    except Exception as e:
        logger.warning(f"文本编码失败: {e}")
        return None


def compute_similarity(image_embedding: np.ndarray, text_embeddings: np.ndarray) -> np.ndarray:
    return (image_embedding @ text_embeddings.T)
