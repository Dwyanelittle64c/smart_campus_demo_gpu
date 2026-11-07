"""文件业务的原子索引与图片写入；损坏时拒绝继续，不覆盖为空库。"""
import json
import os
import threading
import uuid
from pathlib import Path

LOCK = threading.RLock()


def read_index(path, default):
    """未创建的新实例可以为空；现有索引损坏必须人工修复。"""
    path = Path(path)
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text('utf-8'))
    except (OSError, ValueError) as exc:
        raise ValueError(f'索引损坏，请保留并修复 {path.name}') from exc


def atomic_json(path, value):
    """同目录临时文件 + replace，避免断电/异常留下半份 JSON。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def image_bytes(image):
    """图片使用固定 JPEG 编码；不保留用户上传文件名。"""
    import cv2
    ok, encoded = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise ValueError('图片编码失败')
    return encoded.tobytes()
