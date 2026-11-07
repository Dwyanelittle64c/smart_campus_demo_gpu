"""独立交通会话：视频按媒体时钟，浏览器/RTSP 最新帧覆盖，CUDA YOLO + ByteTrack。"""
import asyncio
import math
import time
import uuid
from collections import defaultdict, deque
from shared.config import ROOT, DATA, CONFIG, inside
from backend.core.scheduler import scheduler
from backend.traffic.counting import CounterState, MediaClock


class TrafficService:
    """API 控制仅更改有界状态；视频采集和推理由单任务串行负责。"""
    def __init__(self):
        self.task = None
        self.control_lock = asyncio.Lock()
        self.model = None
        self.capture = None
        self.rtsp = None
        self.status = 'idle'
        self.error = ''
        from backend.core.storage import read_index
        self.counter = CounterState(read_index(DATA / 'runtime/traffic-roi.json', [0, 0, 1, 1]))
        self.source = {}
        self.source_id = None
        self.frame_id = 0
        self.latest = None
        self.camera_pending = None
        self.camera_event = asyncio.Event()
        self.camera_last_seq = -1
        self.camera_started = None
        self.camera_last_time = -1
        self.camera_received_started = None
        self.subscribers = set()
        self.last_metrics = {}
        self.forward_evidence = {}
        self.network_begin = None
        self.network_end = None
        self.trails = defaultdict(lambda: deque(maxlen=24))

    def snapshot(self):
        """状态 GET 不加载模型；RTSP 凭证不出现在返回数据。"""
        return {'status': self.status, 'error': self.error, 'source_type': self.source.get('type'),
                'source_id': self.source_id, 'frame_id': self.frame_id, **self.counter.snapshot(), **self.last_metrics}

    async def control(self, command):
        """开始幂等，切源/ROI 重建会话，暂停不推进视频读取或计数。"""
        async with self.control_lock:
            return await self._control(command)

    async def _control(self, command):
        """生命周期锁内执行；并发HTTP不能创建两个采集/Tracker循环。"""
        action = command.get('action')
        if action == 'pause':
            if self.status not in ('running', 'paused'):
                raise ValueError('当前交通未运行')
            self.status = 'paused' if self.status == 'running' else 'running'
            if self.status == 'paused':
                self.camera_pending = None
                self.camera_event.clear()
            return self.snapshot()
        if action in ('stop', 'reset', 'roi'):
            source = self.source.copy()
            was_active = self.status in ('running', 'paused', 'starting')
            await self._stop()
            if action in ('reset', 'roi'):
                self.counter = CounterState(command.get('roi', self.counter.roi))
                self.latest = None
                self.frame_id = 0
                self.source_id = uuid.uuid4().hex
                self.status = 'idle'
            if action == 'roi':
                from backend.core.storage import atomic_json
                atomic_json(DATA / 'runtime/traffic-roi.json', self.counter.roi)
                if source and was_active:
                    return await self._control({'action': 'start', 'source': source})
            return self.snapshot()
        if action != 'start':
            raise ValueError('交通操作无效')
        source = command.get('source', {'type': 'video', 'asset_id': 'vtest'})
        if source.get('type') not in ('video', 'camera', 'rtsp'):
            raise ValueError('只支持服务器/上传视频、浏览器摄像头、RTSP')
        if self.task and not self.task.done() and source == self.source:
            return self.snapshot()
        await self._stop()
        if source['type'] == 'rtsp' and not source.get('url', '').startswith(('rtsp://', 'rtsps://')):
            raise ValueError('请输入 RTSP 地址；访问发生在 GPU 服务器')
        self.source = source
        self.source_id = uuid.uuid4().hex
        self.counter = CounterState(self.counter.roi)
        self.trails.clear()
        self.frame_id = 0
        self.camera_pending = None
        self.camera_last_seq = -1
        self.camera_started = None
        self.camera_last_time = -1
        self.camera_received_started = None
        self.latest = None
        self.error = ''
        self.status = 'starting'
        self.task = asyncio.create_task(self._run())
        return self.snapshot()

    def _open(self):
        """只打开明确允许目录/上传 ID，不解释学生电脑路径；RTSP 有读超时。"""
        import cv2
        from backend.core.storage import read_index
        if self.source['type'] == 'video':
            identifier = str(self.source.get('asset_id', 'vtest'))
            if identifier == 'vtest':
                path = DATA / 'videos/vtest.avi'
            else:
                assets = read_index(DATA / 'uploads/videos.json', {})
                if identifier not in assets:
                    raise ValueError('服务器视频 ID 不存在，请先上传本机文件')
                path = inside(DATA / 'uploads', assets[identifier])
            capture = cv2.VideoCapture(str(path))
        else:
            capture = cv2.VideoCapture(self.source['url'], cv2.CAP_FFMPEG,
                [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 4000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 3000])
        if not capture.isOpened():
            capture.release()
            raise ValueError('服务器无法打开视频/RTSP；请检查文件或服务器网络可达性')
        return capture

    def _infer(self, frame, seconds):
        """整帧 CUDA 检测与内置 ByteTrack；计数只根据归一化底中心。"""
        import cv2
        import numpy as np
        import torch
        import os
        os.environ['YOLO_CONFIG_DIR'] = str(DATA / 'runtime/ultralytics')
        (DATA / 'runtime/ultralytics').mkdir(parents=True, exist_ok=True)
        os.environ['YOLO_AUTOINSTALL'] = 'false'
        os.environ['YOLO_OFFLINE'] = 'true'  # 固定版本支持：跳过公网连通性探测。
        from ultralytics import YOLO, settings
        if not torch.cuda.is_available():
            raise RuntimeError('交通 CUDA 不可用，无 CPU 回退')
        torch.set_num_threads(2)
        cv2.setNumThreads(2)
        if self.model is None:
            path = ROOT / CONFIG['traffic']['model']
            if not path.is_file():
                raise FileNotFoundError('缺少官方 yolov8n.pt')
            settings.update({'sync': False})  # 只写该实例配置，不启用遥测/外部集成。
            self.model = YOLO(str(path))
            self.model.to(CONFIG['device'])
            def before_forward(module, inputs):
                tensor = inputs[0]
                self.forward_evidence = {'forward_input_device': str(tensor.device)}
                self.network_begin = torch.cuda.Event(enable_timing=True)
                self.network_end = torch.cuda.Event(enable_timing=True)
                self.network_begin.record(torch.cuda.current_stream(tensor.device))
            def after_forward(module, inputs, outputs):
                def devices(value):
                    if isinstance(value, torch.Tensor):
                        return [str(value.device)]
                    if isinstance(value, (tuple, list)):
                        return [device for child in value for device in devices(child)]
                    if isinstance(value, dict):
                        return [device for child in value.values() for device in devices(child)]
                    return []
                self.forward_evidence['forward_output_devices'] = sorted(set(devices(outputs)))
                self.network_end.record(torch.cuda.current_stream(inputs[0].device))
            self.model.model.register_forward_pre_hook(before_forward)
            self.model.model.register_forward_hook(after_forward)
        if self.frame_id == 0 and self.model.predictor:
            for tracker in getattr(self.model.predictor, 'trackers', []):
                tracker.reset()
        started = time.perf_counter()
        result = self.model.track(frame, persist=True, tracker='bytetrack.yaml', device=CONFIG['device'],
                                  imgsz=CONFIG['traffic']['imgsz'], conf=CONFIG['traffic']['confidence'], verbose=False)[0]
        torch.cuda.synchronize()
        inference_ms = (time.perf_counter() - started) * 1000
        if (next(self.model.model.parameters()).device.type != 'cuda' or
                not self.forward_evidence.get('forward_input_device', '').startswith('cuda') or
                not self.forward_evidence.get('forward_output_devices') or
                any(not value.startswith('cuda') for value in self.forward_evidence['forward_output_devices'])):
            raise RuntimeError('YOLO 网络前向输入/输出不在 CUDA，拒绝 GPU 验收')
        height, width = frame.shape[:2]
        observations = []
        ids = result.boxes.id.cpu().numpy() if result.boxes.id is not None else [None] * len(result.boxes)
        for identifier, box, cls in zip(ids, result.boxes.xyxy.cpu().numpy(), result.boxes.cls.cpu().numpy()):
            x1, y1, x2, y2 = map(float, box)
            observations.append((int(identifier) if identifier is not None else None, int(cls), (x1 + x2) / (2 * width), y2 / height))
        visual = result.plot()
        alive = set()
        for identifier, cls, x, y in observations:
            if identifier is not None:
                alive.add(identifier)
                self.trails[identifier].append((int(x * width), int(y * height)))
                points = np.asarray(self.trails[identifier], dtype=np.int32)
                if len(points) > 1:
                    cv2.polylines(visual, [points], False, (220, 190, 40), 2)
        for identifier in list(self.trails):
            if identifier not in alive:
                del self.trails[identifier]
        x1, y1, x2, y2 = self.counter.roi
        cv2.rectangle(visual, (round(x1 * width), round(y1 * height)), (round(x2 * width) - 1, round(y2 * height) - 1), (80, 210, 40), 2)
        valid, jpeg = cv2.imencode('.jpg', visual, [cv2.IMWRITE_JPEG_QUALITY, 82])
        if not valid:
            raise RuntimeError('交通画面编码失败')
        return jpeg.tobytes(), observations, {'resolution': [width, height], 'core_ms': inference_ms,
                               'device': str(next(self.model.model.parameters()).device), 'result_device': str(result.boxes.data.device),
                               'network_gpu_ms': self.network_begin.elapsed_time(self.network_end), **self.forward_evidence,
                               'detections': len(result.boxes), 'processing_fps': 1000 / max(inference_ms, .001)}

    async def _run(self):
        """视频顺序处理；浏览器最新输入单槽；RTSP 专用采集线程覆盖旧帧。"""
        import cv2
        clock = None
        began = time.monotonic()
        paused_total = 0
        try:
            if self.source['type'] != 'camera':
                self.capture = await asyncio.to_thread(self._open)
                if self.source['type'] == 'video':
                    clock = MediaClock(self.capture.get(cv2.CAP_PROP_FPS))
                else:
                    from backend.traffic.capture import LatestCapture
                    self.rtsp = LatestCapture(self.capture)
            self.status = 'running'
            while self.status in ('running', 'paused'):
                if self.status == 'paused':
                    wait = time.monotonic()
                    await asyncio.sleep(.05)
                    paused_total += time.monotonic() - wait
                    continue
                if clock:
                    ok, frame = await asyncio.to_thread(self.capture.read)
                    if not ok:
                        self.status = 'ended'
                        break
                    seconds = clock.next(self.capture.get(cv2.CAP_PROP_POS_MSEC))
                    delay = seconds - (time.monotonic() - began - paused_total)
                    if delay > 0:
                        await asyncio.sleep(delay)
                    sequence = clock.index
                elif self.rtsp:
                    item = self.rtsp.take()
                    if item is None:
                        if self.rtsp.error:
                            raise ValueError(self.rtsp.error)
                        await asyncio.sleep(.01)
                        continue
                    frame, seconds, sequence = item
                else:
                    await self.camera_event.wait()
                    self.camera_event.clear()
                    item, self.camera_pending = self.camera_pending, None
                    if item is None:
                        continue
                    raw, seconds, sequence, original_resolution, payload_resolution = item
                    frame = await asyncio.to_thread(cv2.imdecode, __import__('numpy').frombuffer(raw, __import__('numpy').uint8), cv2.IMREAD_COLOR)
                    if frame is None:
                        raise ValueError('浏览器采集帧无法解码')
                    if list(frame.shape[1::-1]) != payload_resolution or frame.shape[1] > 1280 or frame.shape[0] > 960:
                        raise ValueError('摄像头实际尺寸与帧元数据不一致或超限')
                # 文件帧已解码就保留到恢复；直播暂停期间只保留采集端最新帧。
                while clock and self.status == 'paused':
                    waiting = time.monotonic()
                    await asyncio.sleep(.05)
                    paused_total += time.monotonic() - waiting
                if self.status != 'running':
                    continue
                payload, observations, meta = await scheduler.submit('traffic', self._infer, frame, seconds)
                while clock and self.status == 'paused':
                    waiting = time.monotonic()
                    await asyncio.sleep(.05)
                    paused_total += time.monotonic() - waiting
                if self.status != 'running':
                    continue
                # 计数只在 ASGI 控制线程提交，暂停请求后 GPU 在途帧不能再改统计。
                meta['statistics'] = self.counter.update(observations, seconds)
                self.frame_id += 1
                self.last_metrics = {k: meta[k] for k in ('device', 'result_device', 'core_ms', 'processing_fps', 'detections',
                                                        'network_gpu_ms', 'forward_input_device', 'forward_output_devices')}
                meta.update(stream='traffic', epoch=self.source_id, source_id=self.source_id, frame_id=self.frame_id,
                            source_sequence=sequence, timestamp=seconds, timebase='media' if clock else 'capture-relative',
                            session_id=self.source_id)
                meta['original_resolution'] = original_resolution if self.source['type'] == 'camera' else meta['resolution']
                self.latest = (meta, payload)
                for queue in self.subscribers:
                    if queue.full():
                        queue.get_nowait()
                    queue.put_nowait(self.latest)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.status = 'error'
            self.error = 'RTSP 无法打开或读取超时，请检查服务器网络' if self.source.get('type') == 'rtsp' else str(exc)
        finally:
            if self.rtsp:
                await asyncio.to_thread(self.rtsp.close)
                self.rtsp = None
            if self.capture:
                await asyncio.to_thread(self.capture.release)
                self.capture = None

    def camera_frame(self, meta, payload):
        """校验单调采集时间/序号；覆盖待办，不用剩余帧重编号压缩时间。"""
        if self.source.get('type') != 'camera' or self.status not in ('running', 'paused'):
            raise ValueError('请先开始浏览器摄像头交通会话')
        sequence, milliseconds = int(meta['sequence']), float(meta['capture_ms'])
        if not 0 <= sequence < 2**31 or sequence <= self.camera_last_seq or not math.isfinite(milliseconds) or milliseconds <= self.camera_last_time:
            raise ValueError('摄像头采集序号/时间回退')
        if len(payload) > 2 * 1024 * 1024:
            raise ValueError('摄像头帧超过 2MB')
        if meta.get('timebase') != 'browser-monotonic-ms':
            raise ValueError('摄像头缺少明确采集时间基准')
        dimensions = [meta.get('original_resolution'), meta.get('resolution')]
        if any(not isinstance(value, list) or len(value) != 2 or any(not isinstance(number, int) or not 0 < number <= 8192 for number in value) for value in dimensions):
            raise ValueError('摄像头尺寸元数据无效')
        if self.camera_started is None:
            self.camera_started = milliseconds
            self.camera_received_started = time.monotonic()
        seconds = (milliseconds - self.camera_started) / 1000
        if abs(seconds - (time.monotonic() - self.camera_received_started)) > 10:
            raise ValueError('摄像头采集时间异常跳变')
        self.camera_last_seq, self.camera_last_time = sequence, milliseconds
        if self.status == 'running':
            self.camera_pending = (payload, seconds, sequence, *dimensions)
            self.camera_event.set()

    async def stop(self):
        """等待当前 GPU 项结束，再取消采集循环；不会启动第二个并发 Tracker。"""
        async with self.control_lock:
            await self._stop()

    async def _stop(self):
        """锁内释放采集与在途项；正常控制和断线回收复用同一路径。"""
        self.status = 'stopped'
        if self.task and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            # shield 的 GPU 执行可能仍在完成，只在调度线程里释放 mutable 模型。
            while scheduler.running == 'traffic' or 'traffic' in scheduler.pending:
                await asyncio.sleep(.01)
        self.task = None
        self.camera_pending = None
        self.camera_event.clear()
        if self.source.get('type') == 'camera':
            self.latest = None
            if self.model is not None and self.model.predictor is not None:
                self.model.predictor.results = []
                self.model.predictor.batch = None
                self.model.predictor.dataset = None
                self.model.predictor.plotted_img = None

    def unload(self):
        """服务关闭时释放 GPU 模型和 Tracker 缓存。"""
        self.model = None
        self.network_begin = self.network_end = None
        self.forward_evidence.clear()


service = TrafficService()
