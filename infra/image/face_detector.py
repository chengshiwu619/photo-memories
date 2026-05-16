import numpy as np
from typing import Optional, List, Tuple

from logger_setup import logger
from infra.image.thumbnail_loader import get_thumbnail_loader

_detector = None


def _load_detector():
    global _detector
    if _detector is not None:
        return True
    try:
        from deepface import DeepFace
        _detector = DeepFace
        logger.info("DeepFace 加载完成")
        return True
    except ImportError:
        logger.warning("deepface 未安装, 人脸检测不可用. 安装: pip install deepface")
        return False
    except Exception as e:
        logger.error(f"DeepFace 加载失败: {e}")
        return False


def is_available() -> bool:
    if _detector is not None:
        return True
    try:
        import deepface
        return True
    except ImportError:
        return False


def detect_faces(file_id: int) -> List[dict]:
    if not _load_detector():
        return []

    loader = get_thumbnail_loader()
    img = loader.load(file_id, size=(640, 640))
    if img is None:
        return []

    try:
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            img.save(tmp.name, "JPEG")
            tmp_path = tmp.name

        try:
            results = _detector.extract_faces(
                img_path=tmp_path,
                detector_backend="retinaface",
                enforce_detection=False,
                align=True,
            )

            faces = []
            for r in results:
                if r.get("confidence", 0) > 0.9:
                    facial_area = r.get("facial_area", {})
                    faces.append({
                        "x": facial_area.get("x", 0),
                        "y": facial_area.get("y", 0),
                        "w": facial_area.get("w", 0),
                        "h": facial_area.get("h", 0),
                        "confidence": r.get("confidence", 0),
                    })
            return faces
        finally:
            os.unlink(tmp_path)
    except Exception as e:
        logger.warning(f"人脸检测失败 file_id={file_id}: {e}")
        return []


def extract_embedding(file_id: int) -> Optional[np.ndarray]:
    if not _load_detector():
        return None

    loader = get_thumbnail_loader()
    img = loader.load(file_id, size=(640, 640))
    if img is None:
        return None

    try:
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            img.save(tmp.name, "JPEG")
            tmp_path = tmp.name

        try:
            result = _detector.represent(
                img_path=tmp_path,
                model_name="ArcFace",
                detector_backend="retinaface",
                enforce_detection=True,
            )
            if result and len(result) > 0:
                return np.array(result[0]["embedding"], dtype=np.float32)
            return None
        finally:
            os.unlink(tmp_path)
    except ValueError:
        return None
    except Exception as e:
        logger.warning(f"人脸嵌入提取失败 file_id={file_id}: {e}")
        return None


def extract_embeddings_batch(file_ids: List[int]) -> List[Tuple[int, np.ndarray]]:
    results = []
    for fid in file_ids:
        emb = extract_embedding(fid)
        if emb is not None:
            results.append((fid, emb))
    return results
