import numpy as np
from typing import List, Dict, Tuple

from logger_setup import logger
from infra.image.clip_encoder import encode_image, encode_text, compute_similarity, is_available

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
]

DEFAULT_TOP_K = 5
DEFAULT_THRESHOLD = 0.25

_text_embeddings_cache: Dict[str, np.ndarray] = {}


def _get_text_embeddings(candidates: List[str]) -> np.ndarray:
    key = "|".join(candidates)
    if key not in _text_embeddings_cache:
        result = encode_text(candidates)
        if result is not None:
            _text_embeddings_cache[key] = result
        else:
            return np.array([])
    return _text_embeddings_cache[key]


def generate_tags_for_image(
    file_id: int,
    candidates: List[str] = None,
    top_k: int = DEFAULT_TOP_K,
    threshold: float = DEFAULT_THRESHOLD,
) -> List[str]:
    if not is_available():
        return []

    if candidates is None:
        candidates = TAG_CANDIDATES_ZH + TAG_CANDIDATES_EN

    image_emb = encode_image(file_id)
    if image_emb is None:
        return []

    text_emb = _get_text_embeddings(candidates)
    if text_emb.size == 0:
        return []

    similarities = compute_similarity(image_emb, text_emb)

    top_indices = np.argsort(similarities)[::-1][:top_k]
    tags = []
    for idx in top_indices:
        if similarities[idx] >= threshold:
            tags.append(candidates[idx])

    return tags


def generate_tags_batch(
    file_ids: List[int],
    candidates: List[str] = None,
    top_k: int = DEFAULT_TOP_K,
    threshold: float = DEFAULT_THRESHOLD,
) -> Dict[int, List[str]]:
    if not is_available():
        return {}

    if candidates is None:
        candidates = TAG_CANDIDATES_ZH + TAG_CANDIDATES_EN

    text_emb = _get_text_embeddings(candidates)
    if text_emb.size == 0:
        return {}

    from infra.image.clip_encoder import encode_images_batch
    image_results = encode_images_batch(file_ids)

    result = {}
    for file_id, image_emb in image_results:
        similarities = compute_similarity(image_emb, text_emb)
        top_indices = np.argsort(similarities)[::-1][:top_k]
        tags = [candidates[idx] for idx in top_indices if similarities[idx] >= threshold]
        result[file_id] = tags

    return result
