import numpy as np
from typing import List, Tuple
from logger_setup import logger


def greedy_cluster(
    embeddings: List[Tuple[int, np.ndarray]],
    metric: str = "euclidean",
    threshold: float = 0.6,
) -> List[List[Tuple[int, np.ndarray]]]:
    if not embeddings:
        return []

    clusters: List[List[Tuple[int, np.ndarray]]] = []
    reps: List[np.ndarray] = []

    for file_id, emb in embeddings:
        assigned = False
        if reps:
            if metric == "euclidean":
                dists = np.linalg.norm(np.array(reps) - emb, axis=1)
                best_idx = int(np.argmin(dists))
                if dists[best_idx] < threshold:
                    clusters[best_idx].append((file_id, emb))
                    assigned = True
            elif metric == "cosine":
                sims = np.dot(np.array(reps), emb)
                best_idx = int(np.argmax(sims))
                if sims[best_idx] >= threshold:
                    clusters[best_idx].append((file_id, emb))
                    assigned = True

        if not assigned:
            clusters.append([(file_id, emb)])
            reps.append(emb)

    logger.debug(f"greedy_cluster: {len(embeddings)} items -> {len(clusters)} clusters (metric={metric}, threshold={threshold})")
    return clusters
