import threading
from typing import Optional, Callable

from logger_setup import logger
from db_manager import Database
from checkpoint_manager import CheckpointManager, CheckpointState
from infra.db.repositories.photo_metadata_repo import PhotoMetadataRepository
from infra.db.repositories.photo_tags_repo import PhotoTagsRepository
from infra.db.repositories.face_embeddings_repo import FaceEmbeddingsRepository

_db = Database()
_cp = CheckpointManager(_db, "recognition")


def get_status():
    return _cp.get_status()


def request_pause():
    _cp.request_pause()


def request_stop():
    _cp.request_stop()


def _should_stop():
    return _cp.is_pause_or_stop_requested()


def run_recognition(
    progress_callback: Optional[Callable] = None,
    batch_limit: int = 0,
):
    _db.init_tables()

    meta_repo = PhotoMetadataRepository(_db)
    tags_repo = PhotoTagsRepository(_db)

    cp = _cp.load()
    start_stage = cp.get("stage", "siglip") if cp else "siglip"
    processed_total = cp.get("processed_total", 0) if cp else 0

    stages = ["siglip", "face", "yolo", "scene"]
    stage_idx = stages.index(start_stage) if start_stage in stages else 0

    if not cp:
        _cp.save(CheckpointState.RUNNING, stage="siglip", current_index=0, processed_total=0)

    for si in range(stage_idx, len(stages)):
        stage = stages[si]

        if _should_stop():
            _cp.save(CheckpointState.PAUSED, stage=stage, processed_total=processed_total)
            return {"paused": True, "stage": stage, "processed_total": processed_total}

        if stage == "siglip":
            count = _run_siglip_stage(meta_repo, tags_repo, cp, progress_callback, batch_limit)
            processed_total += count
            if count < 0:
                return {"paused": True, "stage": "siglip", "processed_total": processed_total}

        elif stage == "face":
            count = _run_face_stage(meta_repo, progress_callback, batch_limit)
            processed_total += count
            if count < 0:
                return {"paused": True, "stage": "face", "processed_total": processed_total}

        elif stage == "yolo":
            count = _run_yolo_stage(meta_repo, tags_repo, progress_callback, batch_limit)
            processed_total += count
            if count < 0:
                return {"paused": True, "stage": "yolo", "processed_total": processed_total}

        elif stage == "scene":
            count = _run_scene_stage(meta_repo, progress_callback, batch_limit)
            processed_total += count
            if count < 0:
                return {"paused": True, "stage": "scene", "processed_total": processed_total}

        next_stage = stages[si + 1] if si + 1 < len(stages) else "done"
        _cp.save(CheckpointState.RUNNING, stage=next_stage, current_index=0, processed_total=processed_total)

    _cp.clear()
    logger.info(f"识别流水线全部完成, 共处理 {processed_total} 项")
    return {"total": processed_total, "processed": processed_total}


def _run_siglip_stage(meta_repo, tags_repo, cp, progress_callback, batch_limit):
    from business.image_recognition.tag_generator import generate_tags_for_image
    from infra.image.clip_encoder import is_available as clip_available

    if not clip_available():
        logger.warning("SigLIP 不可用, 跳过标签生成")
        return 0

    untagged = meta_repo.get_photos_without_siglip_tags(limit=10000)
    if not untagged:
        logger.info("没有需要 SigLIP 标签的照片")
        return 0

    total = len(untagged)
    logger.info(f"[SigLIP] 开始标签生成: {total} 张照片")

    start_idx = cp.get("current_index", 0) if cp and cp.get("stage") == "siglip" else 0
    processed = 0

    for i in range(start_idx, total):
        if _should_stop():
            _cp.save(CheckpointState.PAUSED, stage="siglip", current_index=i, processed_total=processed)
            return -1

        file_id = untagged[i]
        try:
            tags = generate_tags_for_image(file_id)
            for tag in tags:
                from core.models import PhotoTag
                pt = PhotoTag(file_id=file_id, tag=tag, source="siglip")
                tags_repo.insert_or_ignore(pt)
            processed += 1
        except Exception as e:
            logger.error(f"[SigLIP] 识别失败 file_id={file_id}: {e}")

        if progress_callback and (i + 1) % 10 == 0:
            progress_callback(i + 1, total)

        if batch_limit and processed >= batch_limit:
            _cp.save(CheckpointState.PAUSED, stage="siglip", current_index=i + 1, processed_total=processed)
            return -1

        if (i + 1) % 50 == 0:
            _cp.save(CheckpointState.RUNNING, stage="siglip", current_index=i + 1, processed_total=processed)

    logger.info(f"[SigLIP] 标签生成完成: {processed}/{total}")
    return processed


def _run_face_stage(meta_repo, progress_callback, batch_limit):
    from infra.image.face_detector import is_available as face_available, extract_embeddings_batch
    from business.image_recognition.face_cluster import cluster_faces

    if not face_available():
        logger.warning("DeepFace 不可用, 跳过人脸检测")
        return 0

    emb_repo = FaceEmbeddingsRepository(_db)

    existing = emb_repo.get_existing_file_ids()

    untagged = meta_repo.get_photos_without_siglip_tags(limit=10000)
    if not untagged:
        logger.info("没有可用的照片进行人脸检测")
        return 0

    candidates = [fid for fid in untagged if fid not in existing]
    if not candidates:
        logger.info("所有照片已有人脸嵌入, 跳过")
        return 0

    batch_size = 50
    total = len(candidates)
    processed = 0
    all_embeddings = []

    logger.info(f"[Face] 开始人脸嵌入提取: {total} 张照片")

    for start in range(0, total, batch_size):
        if _should_stop():
            _cp.save(CheckpointState.PAUSED, stage="face", current_index=start, processed_total=processed)
            return -1

        batch = candidates[start:start + batch_size]
        embeddings = extract_embeddings_batch(batch)

        if embeddings:
            all_embeddings.extend(embeddings)
            processed += len(embeddings)

        if progress_callback and (start + batch_size) % 50 == 0:
            progress_callback(min(start + batch_size, total), total)

        if batch_limit and processed >= batch_limit:
            break

    if all_embeddings:
        cluster_faces(all_embeddings)
        logger.info(f"[Face] 人脸聚类完成: {len(all_embeddings)} 个嵌入")

    logger.info(f"[Face] 人脸检测阶段完成: {processed} 张照片")
    return processed


def _run_yolo_stage(meta_repo, tags_repo, progress_callback, batch_limit):
    from infra.image.object_detector import is_available as yolo_available, detect_objects

    if not yolo_available():
        logger.warning("YOLOv8 不可用, 跳过目标检测")
        return 0

    yolo_tagged = tags_repo.get_file_ids_by_source("yolo")

    untagged = meta_repo.get_photos_without_siglip_tags(limit=10000)
    if not untagged:
        logger.info("没有可用的照片进行目标检测")
        return 0

    candidates = [fid for fid in untagged if fid not in yolo_tagged]
    if not candidates:
        logger.info("所有照片已有 YOLO 标签, 跳过")
        return 0

    total = len(candidates)
    processed = 0

    logger.info(f"[YOLO] 开始目标检测: {total} 张照片")

    for i, file_id in enumerate(candidates):
        if _should_stop():
            _cp.save(CheckpointState.PAUSED, stage="yolo", current_index=i, processed_total=processed)
            return -1

        try:
            detections = detect_objects(file_id)
            for det in detections:
                if det.get("confidence", 0) > 0.5:
                    from core.models import PhotoTag
                    pt = PhotoTag(file_id=file_id, tag=det["class"], source="yolo")
                    tags_repo.insert_or_ignore(pt)
            processed += 1
        except Exception as e:
            logger.error(f"[YOLO] 检测失败 file_id={file_id}: {e}")

        if progress_callback and (i + 1) % 10 == 0:
            progress_callback(i + 1, total)

        if batch_limit and processed >= batch_limit:
            break

    logger.info(f"[YOLO] 目标检测完成: {processed}/{total}")
    return processed


def _run_scene_stage(meta_repo, progress_callback, batch_limit):
    from business.image_recognition.scene_cluster import cluster_by_scene
    from infra.image.clip_encoder import is_available as clip_available

    if not clip_available():
        logger.warning("SigLIP 不可用, 跳过场景聚类")
        return 0

    untagged = meta_repo.get_photos_without_siglip_tags(limit=10000)
    if not untagged:
        logger.info("没有可用的照片进行场景聚类")
        return 0

    scene_batch_size = 200
    total = min(len(untagged), scene_batch_size)
    candidates = untagged[:total]

    logger.info(f"[Scene] 开始场景聚类: {len(candidates)} 张照片")

    try:
        clusters = cluster_by_scene(candidates)
        logger.info(f"[Scene] 场景聚类完成: {len(clusters)} 个场景")
        return len(clusters)
    except Exception as e:
        logger.error(f"[Scene] 场景聚类失败: {e}")
        return 0


def run_recognition_async(progress_callback=None, batch_limit=0):
    thread = threading.Thread(
        target=run_recognition,
        kwargs={"progress_callback": progress_callback, "batch_limit": batch_limit},
        daemon=True,
    )
    thread.start()
    return thread
