import numpy as np
from typing import List, Dict, Tuple
from collections import defaultdict

from logger_setup import logger
from infra.image.clip_encoder import encode_images_batch, is_available as clip_available
from business.image_recognition._clustering import greedy_cluster

_SIMILARITY_THRESHOLD = 0.85


def cluster_by_scene(file_ids: List[int], threshold: float = _SIMILARITY_THRESHOLD) -> Dict[int, List[int]]:
    if not clip_available():
        logger.warning("SigLIP 不可用, 场景聚类跳过")
        return {}

    results = encode_images_batch(file_ids)
    if not results:
        return {}

    clusters = greedy_cluster(results, metric="cosine", threshold=threshold)

    result = {}
    for cluster_idx, cluster in enumerate(clusters):
        result[cluster_idx] = [fid for fid, _ in cluster]

    logger.info(f"场景聚类完成: {len(results)} 张照片 -> {len(clusters)} 个场景")
    return result


def get_scene_tags(file_ids: List[int]) -> Dict[int, List[str]]:
    from business.image_recognition.tag_generator import generate_tags_batch
    return generate_tags_batch(file_ids)
