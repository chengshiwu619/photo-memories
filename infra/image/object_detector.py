import os
from typing import List, Optional, Protocol
from logger_setup import logger


class ObjectDetector(Protocol):
    def detect(self, image_path: str) -> List[dict]: ...


_COCO_NAMES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat",
    "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat",
    "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack",
    "umbrella", "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball",
    "kite", "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket",
    "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
    "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair",
    "couch", "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse",
    "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink", "refrigerator",
    "book", "clock", "vase", "scissors", "teddy bear", "hair drier", "toothbrush",
]

_CONFIDENCE_THRESHOLD = 0.25
_IOU_THRESHOLD = 0.45
_INPUT_SIZE = 640


class YOLOv8ONNXDetector:
    def __init__(self):
        self._session = None

    def _load(self) -> bool:
        if self._session is not None:
            return True
        try:
            import onnxruntime as ort
            model_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "..", "..", "models", "yolov8n.onnx"
            )
            model_path = os.path.normpath(model_path)
            if not os.path.isfile(model_path):
                logger.warning(f"YOLOv8 ONNX 模型文件不存在: {model_path}")
                return False
            providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
            self._session = ort.InferenceSession(model_path, providers=providers)
            self._input_name = self._session.get_inputs()[0].name
            logger.info(f"YOLOv8 ONNX 模型加载完成 (providers: {self._session.get_providers()})")
            return True
        except ImportError:
            logger.warning("onnxruntime 未安装, 目标检测不可用. 安装: pip install onnxruntime")
            return False
        except Exception as e:
            logger.error(f"YOLOv8 ONNX 模型加载失败: {e}")
            return False

    def _preprocess(self, image_path: str):
        import numpy as np
        from PIL import Image

        img = Image.open(image_path).convert("RGB")
        orig_w, orig_h = img.size

        scale = min(_INPUT_SIZE / orig_w, _INPUT_SIZE / orig_h)
        new_w, new_h = int(orig_w * scale), int(orig_h * scale)

        resized = img.resize((new_w, new_h), Image.BILINEAR)

        pad_img = Image.new("RGB", (_INPUT_SIZE, _INPUT_SIZE), (114, 114, 114))
        pad_img.paste(resized, ((_INPUT_SIZE - new_w) // 2, (_INPUT_SIZE - new_h) // 2))

        arr = np.array(pad_img).astype(np.float32) / 255.0
        arr = arr.transpose(2, 0, 1)
        arr = np.expand_dims(arr, axis=0)
        arr = arr.astype(np.float32)

        return arr, scale, orig_w, orig_h, (_INPUT_SIZE - new_w) // 2, (_INPUT_SIZE - new_h) // 2

    def _postprocess(self, output, scale, orig_w, orig_h, pad_w, pad_h):
        import numpy as np

        predictions = output[0]
        if predictions.ndim == 3:
            predictions = predictions[0]

        predictions = predictions.transpose(1, 0)

        detections = []
        for pred in predictions:
            obj_conf = pred[4]
            if obj_conf < _CONFIDENCE_THRESHOLD:
                continue

            class_scores = pred[5:]
            class_id = int(np.argmax(class_scores))
            class_conf = float(class_scores[class_id])
            confidence = float(obj_conf) * class_conf

            if confidence < _CONFIDENCE_THRESHOLD:
                continue

            cx = (float(pred[0]) - pad_w) / scale
            cy = (float(pred[1]) - pad_h) / scale
            w = float(pred[2]) / scale
            h = float(pred[3]) / scale

            x1 = max(0, int(cx - w / 2))
            y1 = max(0, int(cy - h / 2))
            x2 = min(orig_w, int(cx + w / 2))
            y2 = min(orig_h, int(cy + h / 2))

            class_name = _COCO_NAMES[class_id] if class_id < len(_COCO_NAMES) else f"class_{class_id}"

            detections.append({
                "class": class_name,
                "confidence": round(confidence, 4),
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
            })

        detections = self._nms(detections)
        return detections

    def _nms(self, detections: List[dict]) -> List[dict]:
        if not detections:
            return detections

        import numpy as np

        boxes = []
        scores = []
        for d in detections:
            boxes.append([d["x1"], d["y1"], d["x2"], d["y2"]])
            scores.append(d["confidence"])

        boxes = np.array(boxes, dtype=np.float32)
        scores = np.array(scores, dtype=np.float32)

        x1 = boxes[:, 0]
        y1 = boxes[:, 1]
        x2 = boxes[:, 2]
        y2 = boxes[:, 3]
        areas = (x2 - x1) * (y2 - y1)

        order = scores.argsort()[::-1]
        keep = []

        while order.size > 0:
            i = order[0]
            keep.append(i)

            xx1 = np.maximum(x1[i], x1[order[1:]])
            yy1 = np.maximum(y1[i], y1[order[1:]])
            xx2 = np.minimum(x2[i], x2[order[1:]])
            yy2 = np.minimum(y2[i], y2[order[1:]])

            inter = np.maximum(0.0, xx2 - xx1) * np.maximum(0.0, yy2 - yy1)
            iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-6)

            inds = np.where(iou <= _IOU_THRESHOLD)[0]
            order = order[inds + 1]

        return [detections[i] for i in keep]

    def detect(self, image_path: str) -> List[dict]:
        if not self._load():
            return []
        try:
            import numpy as np

            arr, scale, orig_w, orig_h, pad_w, pad_h = self._preprocess(image_path)
            outputs = self._session.run(None, {self._input_name: arr})
            return self._postprocess(outputs[0], scale, orig_w, orig_h, pad_w, pad_h)
        except Exception as e:
            logger.warning(f"目标检测失败 {image_path}: {e}")
            return []


_detector: Optional[YOLOv8ONNXDetector] = None


def get_detector() -> Optional[ObjectDetector]:
    global _detector
    if _detector is None:
        _detector = YOLOv8ONNXDetector()
    return _detector


def is_available() -> bool:
    try:
        import onnxruntime
        return True
    except ImportError:
        return False


def detect_objects(file_id: int) -> List[dict]:
    import os
    from config import get_settings

    thumb_path = os.path.join(get_settings().thumbnail_dir, f"{file_id}.jpg")
    if not os.path.exists(thumb_path):
        return []

    detector = get_detector()
    if detector is None:
        return []
    return detector.detect(thumb_path)
