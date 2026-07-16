import os
import sys
import numpy as np
from typing import Any, List, Dict, Tuple, Optional
from PIL import Image, ImageOps

from logger_setup import logger
from infra.image.clip_encoder import encode_image, encode_text, compute_similarity, is_available
from infra.image.thumbnail_cache import build_thumbnail_path

TAG_CANDIDATES_ZH = [
    "日落", "日出", "海滩", "山脉", "森林", "湖泊", "河流", "天空", "云",
    "雪", "雨", "花", "草地", "沙漠", "城市", "建筑", "街道", "夜景",
    "人物", "儿童", "婴儿", "家庭", "情侣", "朋友", "聚会", "婚礼",
    "生日", "节日", "圣诞", "春节", "旅行", "飞机", "火车", "汽车",
    "自行车", "船", "食物", "蛋糕", "咖啡", "餐厅", "厨房",
    "宠物", "猫", "狗", "鸟", "鱼", "动物", "野生动物",
    "运动", "跑步", "游泳", "篮球", "足球", "瑜伽",
    "音乐", "乐器", "演唱会", "绘画", "手工",
    "毕业", "学校", "教室", "办公室", "会议",
    "公园", "游乐场", "博物馆", "图书馆",
    "自拍", "合影", "证件照", "风景照",
]

TAG_CANDIDATES_EN = [
    "sunset", "sunrise", "beach", "mountain", "forest", "lake", "river", "sky", "clouds",
    "snow", "rain", "flowers", "grass", "desert", "city", "architecture", "street", "night",
    "people", "children", "baby", "family", "couple", "friends", "party", "wedding",
    "birthday", "festival", "christmas", "travel", "airplane", "train", "car",
    "bicycle", "boat", "food", "cake", "coffee", "restaurant", "kitchen",
    "pet", "cat", "dog", "bird", "fish", "animal", "wildlife",
    "sports", "running", "swimming", "basketball", "football", "yoga",
    "music", "instrument", "concert", "painting", "craft",
    "graduation", "school", "classroom", "office", "meeting",
    "park", "playground", "museum", "library",
    "selfie", "group photo", "portrait", "landscape",
    "nsfw", "nude", "explicit", "nipples", "female genitals", "vulva", "labia",
    "lingerie", "gravure", "model portrait", "photobook",
]

DEFAULT_TOP_K = 5
DEFAULT_THRESHOLD = 0.25
THUMBNAIL_MODEL_SIZE = (384, 384)
SIGLIP_STATUS_SOURCE = "siglip-v3-nsfw"
CALIBRATED_REVIEW_TAG = "nsfw-review:calibrated-v3"
VISUAL_REVIEW_TRIGGER_TAGS = {
    "nsfw",
    "nude",
    "explicit",
    "nipples",
    "female genitals",
    "vulva",
    "labia",
}
VISUAL_REVIEW_PROMPTS = {
    "nsfw": "adult content, not safe for work",
    "nude": "an erotic nude photo",
    "explicit": "a sexually explicit image",
    "nipples": "visible nipples in a photo",
    "female genitals": "visible female genitals in a photo",
    "vulva": "a clearly visible vulva",
    "labia": "clearly visible labia",
}
VISUAL_REVIEW_THRESHOLDS = {
    "nsfw": 0.052,
    "nude": 0.070,
    "explicit": 0.097,
    "nipples": 0.083,
    "female genitals": 0.100,
    "vulva": 0.061,
    "labia": 0.076,
}

_text_embeddings_cache: Dict[str, np.ndarray] = {}


def _candidate_threshold(candidate: str, default_threshold: float, use_visual_calibration: bool) -> float:
    if use_visual_calibration:
        return VISUAL_REVIEW_THRESHOLDS.get(candidate, default_threshold)
    return default_threshold


def _candidate_prompt(candidate: str) -> str:
    return VISUAL_REVIEW_PROMPTS.get(candidate, candidate)


def _get_text_embeddings(candidates: List[str]) -> np.ndarray:
    prompts = [_candidate_prompt(candidate) for candidate in candidates]
    key = "|".join(f"{candidate}\0{prompt}" for candidate, prompt in zip(candidates, prompts))
    if key not in _text_embeddings_cache:
        result = encode_text(prompts)
        if result is not None:
            _text_embeddings_cache[key] = result
        else:
            return np.array([])
    return _text_embeddings_cache[key]


def _select_tags(
    similarities,
    candidates: List[str],
    top_k: int,
    threshold: float,
    use_visual_calibration: bool,
) -> List[str]:
    ranked_indices = list(np.argsort(similarities)[::-1][:top_k])
    if use_visual_calibration:
        ranked_indices.extend(
            index
            for index, candidate in enumerate(candidates)
            if candidate in VISUAL_REVIEW_TRIGGER_TAGS and index not in ranked_indices
        )

    tags = []
    for index in ranked_indices:
        candidate = candidates[index]
        if similarities[index] >= _candidate_threshold(
            candidate,
            threshold,
            use_visual_calibration,
        ):
            tags.append(candidate)

    if use_visual_calibration and any(tag in VISUAL_REVIEW_TRIGGER_TAGS for tag in tags):
        tags.append(CALIBRATED_REVIEW_TAG)
    return tags


def _resolve_settings(settings: Any = None):
    if settings is not None:
        return settings

    from config import get_settings

    return get_settings()


def _thumbnail_error(file_id: int, settings: Any, reason: str, error: Optional[str] = None) -> Dict[str, Any]:
    payload = {
        "file_id": file_id,
        "thumbnail_path": build_thumbnail_path(settings.thumbnail_dir, file_id),
        "reason": reason,
    }
    if error:
        payload["error"] = error
    return payload


def _load_thumbnail_image(file_id: int, settings: Any) -> tuple[Optional[Image.Image], Optional[Dict[str, Any]]]:
    thumbnail_path = build_thumbnail_path(settings.thumbnail_dir, file_id)
    if not os.path.exists(thumbnail_path):
        return None, _thumbnail_error(file_id, settings, "thumbnail_not_found")

    try:
        with Image.open(thumbnail_path) as opened:
            opened.load()
            img = ImageOps.exif_transpose(opened)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            else:
                img = img.copy()
            img.thumbnail(THUMBNAIL_MODEL_SIZE, Image.LANCZOS)
            return img, None
    except Exception as exc:
        return None, _thumbnail_error(file_id, settings, "image_open_failed", str(exc))


def _encode_preprocessed_batch(image_inputs: List[Any], clip_encoder_module: Any) -> np.ndarray:
    import torch

    with torch.no_grad():
        batch_tensor = torch.stack(image_inputs)
        active_device = getattr(clip_encoder_module, "get_active_device", lambda: "unloaded")()
        if active_device not in {"", "unloaded", "cpu"}:
            batch_tensor = batch_tensor.to(active_device)
        try:
            embeddings = clip_encoder_module._model.encode_image(batch_tensor)
        except Exception:
            if active_device == "cuda" and hasattr(clip_encoder_module, "_reset_model"):
                logger.warning("SigLIP CUDA 推理失败，降级 CPU 后重试")
                clip_encoder_module._reset_model()
                if not clip_encoder_module._load_model(preferred_device="cpu"):
                    raise
                batch_tensor = torch.stack(image_inputs)
                embeddings = clip_encoder_module._model.encode_image(batch_tensor)
            else:
                raise
        embeddings = embeddings / embeddings.norm(dim=-1, keepdim=True)
        return embeddings.cpu().numpy()


def _encode_images_batch_detailed(
    file_ids: List[int],
    settings: Any = None,
    batch_size: int = 16,
) -> Dict[str, Any]:
    settings = _resolve_settings(settings)
    result = {
        "embeddings": [],
        "encoded_count": 0,
        "encode_failed_count": 0,
        "encode_errors": [],
    }

    if not file_ids:
        return result

    from infra.image import clip_encoder as ce

    if not ce._load_model():
        result["encode_failed_count"] = len(file_ids)
        result["encode_errors"] = [
            _thumbnail_error(file_id, settings, "model_encode_failed", "SigLIP model unavailable")
            for file_id in file_ids
        ]
        return result

    for start in range(0, len(file_ids), batch_size):
        batch_ids = file_ids[start:start + batch_size]
        preprocessed_inputs: List[Any] = []
        valid_ids: List[int] = []

        for file_id in batch_ids:
            img, load_error = _load_thumbnail_image(file_id, settings)
            if load_error is not None:
                result["encode_errors"].append(load_error)
                continue

            try:
                preprocessed_inputs.append(ce._preprocess(img))
                valid_ids.append(file_id)
            except Exception as exc:
                result["encode_errors"].append(
                    _thumbnail_error(file_id, settings, "preprocess_failed", str(exc))
                )
            finally:
                try:
                    img.close()
                except Exception:
                    pass

        if not preprocessed_inputs:
            continue

        try:
            embeddings_np = _encode_preprocessed_batch(preprocessed_inputs, ce)
            for index, file_id in enumerate(valid_ids):
                result["embeddings"].append((file_id, embeddings_np[index].flatten()))
        except Exception as exc:
            for file_id in valid_ids:
                result["encode_errors"].append(
                    _thumbnail_error(file_id, settings, "model_encode_failed", str(exc))
                )

    result["encoded_count"] = len(result["embeddings"])
    result["encode_failed_count"] = len(result["encode_errors"])
    return result


def generate_tags_for_image(
    file_id: int,
    candidates: List[str] = None,
    top_k: int = DEFAULT_TOP_K,
    threshold: float = DEFAULT_THRESHOLD,
) -> List[str]:
    if not is_available():
        return []

    use_visual_calibration = candidates is None
    if candidates is None:
        candidates = TAG_CANDIDATES_ZH + TAG_CANDIDATES_EN

    image_emb = encode_image(file_id)
    if image_emb is None:
        return []

    text_emb = _get_text_embeddings(candidates)
    if text_emb.size == 0:
        return []

    similarities = compute_similarity(image_emb, text_emb)

    return _select_tags(
        similarities,
        candidates,
        top_k,
        threshold,
        use_visual_calibration,
    )


def generate_tags_batch(
    file_ids: List[int],
    candidates: List[str] = None,
    top_k: int = DEFAULT_TOP_K,
    threshold: float = DEFAULT_THRESHOLD,
    settings: Any = None,
    return_diagnostics: bool = False,
) -> Dict[int, List[str]]:
    if not is_available():
        detailed = {
            "tags_by_file": {},
            "encoded_count": 0,
            "encode_failed_count": len(file_ids),
            "encode_errors": [
                _thumbnail_error(file_id, _resolve_settings(settings), "model_encode_failed", "SigLIP unavailable")
                for file_id in file_ids
            ],
        }
        return detailed if return_diagnostics else {}

    use_visual_calibration = candidates is None
    if candidates is None:
        candidates = TAG_CANDIDATES_ZH + TAG_CANDIDATES_EN

    text_emb = _get_text_embeddings(candidates)
    if text_emb.size == 0:
        resolved_settings = _resolve_settings(settings)
        detailed = {
            "tags_by_file": {},
            "encoded_count": 0,
            "encode_failed_count": len(file_ids),
            "encode_errors": [
                _thumbnail_error(
                    file_id,
                    resolved_settings,
                    "model_text_encode_failed",
                    "SigLIP text model unavailable",
                )
                for file_id in file_ids
            ],
        }
        return detailed if return_diagnostics else {}

    image_results = _encode_images_batch_detailed(file_ids, settings=settings)

    result = {}
    for file_id, image_emb in image_results["embeddings"]:
        similarities = compute_similarity(image_emb, text_emb)
        result[file_id] = _select_tags(
            similarities,
            candidates,
            top_k,
            threshold,
            use_visual_calibration,
        )

    if return_diagnostics:
        return {
            "tags_by_file": result,
            "encoded_count": image_results["encoded_count"],
            "encode_failed_count": image_results["encode_failed_count"],
            "encode_errors": image_results["encode_errors"],
        }
    return result
