"""仅 RTSP 使用的有界实时采集器；暂停仍覆盖，恢复不回放旧帧。"""
import threading
import time


class LatestCapture:
    def __init__(self, capture):
        self.capture = capture
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.latest = None
        self.error = ''
        self.began = time.monotonic()
        self.thread = threading.Thread(target=self._read, daemon=True, name='rtsp-latest')
        self.thread.start()

    def _read(self):
        """只保留一张最新真实帧，每帧带服务器相对采集时间。"""
        sequence = 0
        while not self.stop_event.is_set():
            ok, frame = self.capture.read()
            if not ok:
                self.error = 'RTSP 读取超时或已断开'
                return
            sequence += 1
            with self.lock:
                self.latest = (frame, time.monotonic() - self.began, sequence)

    def take(self):
        with self.lock:
            result, self.latest = self.latest, None
            return result

    def close(self):
        """有界等待后释放设备；OpenCV 已设读超时。"""
        self.stop_event.set()
        self.thread.join(timeout=4)
        self.capture.release()
