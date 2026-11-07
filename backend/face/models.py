"""YuNet/SFace 的 ORT CUDA 适配；解码遵循 OpenCV 4.10 官方 face_detect.cpp。

来源：https://github.com/opencv/opencv/blob/4.10.0/modules/objdetect/src/face_detect.cpp
OpenCV Apache-2.0；保留第三方许可。仅做既有网络输入/输出适配，没有训练或新检测算法。
"""
import hashlib
import time
from pathlib import Path
import numpy as np
from shared.config import ROOT, CONFIG


class FaceModels:
    """两个 ONNX session 常驻；主要网络算子必须是 CUDA，CPU 仅预处理/NMS/对齐。"""
    def __init__(self, profiling=False):
        import cv2
        import torch  # 先加载 PyTorch 自带 CUDA12/cuDNN9 DLL，ORT 共用兼容大版本。
        if not torch.cuda.is_available():
            raise RuntimeError('人脸 CUDA 不可用；没有 CPU 推理回退')
        torch.cuda.init()
        import onnxruntime as ort
        if 'CUDAExecutionProvider' not in ort.get_available_providers():
            raise RuntimeError('ONNX Runtime GPU 的 CUDA provider 不可用')
        paths = [ROOT / CONFIG['face'][key] for key in ('detector', 'recognizer')]
        if not all(path.is_file() for path in paths):
            raise FileNotFoundError('YuNet/SFace 权重缺失')
        fingerprint = hashlib.sha256(b''.join(path.read_bytes() for path in paths)).hexdigest()
        self.version = 'yunet2023-sface2021-opencv410-rgb-v1-' + fingerprint[:16]
        self.sessions = []
        for label, path in zip(('yunet', 'sface'), paths):
            options = ort.SessionOptions()
            options.log_severity_level = 3
            options.intra_op_num_threads = 2
            options.inter_op_num_threads = 1
            options.enable_profiling = profiling
            if profiling:
                folder = ROOT / 'docs/setup'
                folder.mkdir(parents=True, exist_ok=True)
                options.profile_file_prefix = str(folder / label)
            session = ort.InferenceSession(str(path), sess_options=options, providers=[('CUDAExecutionProvider', {
                'device_id': int(CONFIG['device'].split(':')[-1]), 'gpu_mem_limit': 512 * 1024 * 1024,
                'arena_extend_strategy': 'kSameAsRequested', 'cudnn_conv_algo_search': 'HEURISTIC',
                'cudnn_conv_use_max_workspace': '0'}), 'CPUExecutionProvider'])
            if session.get_providers()[0] != 'CUDAExecutionProvider':
                raise RuntimeError('ORT 初始化后退回 CPU，拒绝运行')
            self.sessions.append(session)
        # 只复用 OpenCV 官方五点 alignCrop，不调用这个对象的 feature() 网络推理。
        self.aligner = cv2.FaceRecognizerSF.create(str(paths[1]), '')
        self.profile_enabled = profiling

    def detect(self, image):
        """BGR 0～255、固定640补边；官方 stride8/16/32 解码、sqrt(cls*obj) 和 NMS。"""
        import cv2
        padded = np.zeros((640, 640, 3), dtype=np.uint8)
        height, width = image.shape[:2]
        padded[:height, :width] = image
        blob = cv2.dnn.blobFromImage(padded)  # YuNet 不做 RGB 交换或归一化。
        session = self.sessions[0]
        outputs = dict(zip((item.name for item in session.get_outputs()), session.run(None, {session.get_inputs()[0].name: blob})))
        threshold = float(CONFIG['face']['detection_score'])
        faces = []
        for stride in (8, 16, 32):
            cls = outputs[f'cls_{stride}'].reshape(-1)
            obj = outputs[f'obj_{stride}'].reshape(-1)
            boxes = outputs[f'bbox_{stride}'].reshape(-1, 4)
            landmarks = outputs[f'kps_{stride}'].reshape(-1, 5, 2)
            score = np.sqrt(np.clip(cls, 0, 1) * np.clip(obj, 0, 1))
            for index in np.flatnonzero(score >= threshold):
                row, col = divmod(int(index), 640 // stride)
                center = (boxes[index, :2] + [col, row]) * stride
                size = np.exp(boxes[index, 2:]) * stride
                points = (landmarks[index] + [col, row]) * stride
                faces.append(np.r_[center - size / 2, size, points.ravel(), score[index]])
        if not faces:
            return np.empty((0, 15), np.float32)
        faces = np.asarray(faces, np.float32)
        keep = cv2.dnn.NMSBoxes(faces[:, :4].astype(int).tolist(), faces[:, 14].tolist(), threshold, .3, top_k=5000)
        return faces[np.asarray(keep).reshape(-1).astype(int)]

    def extract(self, raw):
        """单人图字节→缩放原图、官方对齐脸、128维单位特征及真实执行元数据。"""
        import cv2
        if not raw or len(raw) > 20 * 1024 * 1024:
            raise ValueError('照片应在 20MB 内')
        import io
        from PIL import Image
        try:
            with Image.open(io.BytesIO(raw)) as header:
                original_format = header.format
                if header.format not in ('JPEG', 'PNG') or header.width * header.height > 25_000_000:
                    raise ValueError('照片只支持 JPG/PNG，像素上限2500万')
        except (OSError, Image.DecompressionBombError) as exc:
            raise ValueError('图片格式无效或尺寸过大') from exc
        image = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError('照片无法解码，请选择 JPG/PNG')
        height, width = image.shape[:2]
        if max(height, width) > 640:
            image = cv2.resize(image, (round(width * 640 / max(height, width)), round(height * 640 / max(height, width))))
        started = time.perf_counter()
        faces = self.detect(image)
        detection_ms = (time.perf_counter() - started) * 1000
        if len(faces) != 1:
            raise ValueError('未检测到人脸' if not len(faces) else '检测到多个人脸，请提供单人照片')
        aligned = self.aligner.alignCrop(image, faces[0])
        # OpenCV FaceRecognizerSF::feature 的真实契约：swapRB=true，scale=1，mean=0。
        blob = cv2.dnn.blobFromImage(aligned, 1, (112, 112), (0, 0, 0), True, False)
        session = self.sessions[1]
        began = time.perf_counter()
        feature = session.run(None, {session.get_inputs()[0].name: blob})[0].reshape(-1).astype(np.float32)
        recognition_ms = (time.perf_counter() - began) * 1000
        norm = np.linalg.norm(feature)
        if feature.shape != (128,) or not np.isfinite(feature).all() or norm < 1e-8:
            raise ValueError('SFace 返回无效特征')
        return image, aligned, feature / norm, {'device': 'CUDAExecutionProvider', 'detect_ms': detection_ms,
            'feature_ms': recognition_ms, 'feature_version': self.version, 'landmarks': faces[0].tolist(),
            'original_format': original_format}

    def finish_profile(self):
        """显式自检的节点执行记录；普通在线 session 不开启 profiler。"""
        return [session.end_profiling() for session in self.sessions] if self.profile_enabled else []
