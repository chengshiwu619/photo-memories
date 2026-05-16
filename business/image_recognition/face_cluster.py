import numpy as np
from typing import List, Dict, Optional, Tuple
from collections import defaultdict

from logger_setup import logger
from db_manager import Database
from core.models import FaceCluster, FaceEmbedding
from infra.db.repositories.face_clusters_repo import FaceClustersRepository
from infra.db.repositories.face_embeddings_repo import FaceEmbeddingsRepository
from business.image_recognition._clustering import greedy_cluster

_DISTANCE_THRESHOLD = 0.6


def cluster_faces(embeddings: List[Tuple[int, np.ndarray]], threshold: float = _DISTANCE_THRESHOLD) -> Dict[int, int]:
    if not embeddings:
        return {}

    db = Database()
    clusters_repo = FaceClustersRepository(db)

    clusters = greedy_cluster(embeddings, metric="euclidean", threshold=threshold)

    file_to_cluster = {}
    for cluster_idx, cluster in enumerate(clusters):
        representative_id = cluster[0][0]
        emb_data = [(file_id, emb.astype(np.float32).tobytes()) for file_id, emb in cluster]

        cluster_id = clusters_repo.insert_with_embeddings("", representative_id, emb_data)

        for file_id, _ in cluster:
            file_to_cluster[file_id] = cluster_id

    logger.info(f"人脸聚类完成: {len(embeddings)} 个嵌入 -> {len(clusters)} 个聚类")
    return file_to_cluster


def get_clusters() -> List[FaceCluster]:
    db = Database()
    clusters_repo = FaceClustersRepository(db)
    return clusters_repo.get_all()


def get_cluster_members(cluster_id: int) -> List[int]:
    db = Database()
    embeddings_repo = FaceEmbeddingsRepository(db)
    return embeddings_repo.get_file_ids_by_cluster(cluster_id)


def rename_cluster(cluster_id: int, name: str):
    db = Database()
    clusters_repo = FaceClustersRepository(db)
    clusters_repo.update_name(cluster_id, name)
    logger.info(f"聚类 {cluster_id} 命名为: {name}")


def reassign_face(embedding_id: int, new_cluster_id: int):
    db = Database()
    embeddings_repo = FaceEmbeddingsRepository(db)
    embeddings_repo.update_cluster(embedding_id, new_cluster_id)


def create_cluster_from_face(embedding_id: int, person_name: str = "") -> int:
    db = Database()
    clusters_repo = FaceClustersRepository(db)
    embeddings_repo = FaceEmbeddingsRepository(db)

    cluster = FaceCluster(person_name=person_name, representative_face=embedding_id)
    new_cluster_id = clusters_repo.insert(cluster)
    embeddings_repo.update_cluster(embedding_id, new_cluster_id)
    return new_cluster_id


def get_person_memories() -> Dict[str, List[int]]:
    clusters = get_clusters()
    result = {}
    for c in clusters:
        name = c.person_name or f"人物{c.cluster_id}"
        members = get_cluster_members(c.cluster_id)
        if members:
            result[name] = members
    return result
