"""显式基准才启动资源采样；nvidia-smi 是整张设备，不冒称算法独占显存。"""
import json
import subprocess
import threading
import time


class Monitor:
    """采样后台进程 CPU/RSS、CUDA 分配和设备利用率；正常首页不创建线程。"""
    def __init__(self):
        self.samples = []
        self.event = threading.Event()
        self.thread = None

    def start(self):
        import psutil
        self.process = psutil.Process()
        self.process.cpu_percent()
        self.thread = threading.Thread(target=self._run, daemon=True, name='benchmark-monitor')
        self.thread.start()

    def _run(self):
        """每秒采样，不在每帧启动外部程序；Windows helper 隐藏窗口。"""
        import psutil
        while len(self.samples) < 700 and not self.event.wait(1):
            sample = {'time': time.time(), 'rss_mb': self.process.memory_info().rss / 2**20,
                      'cpu_one_core_percent': self.process.cpu_percent()}
            sample['cpu_machine_percent'] = sample['cpu_one_core_percent'] / (psutil.cpu_count() or 1)
            try:
                raw = subprocess.check_output(['nvidia-smi', '--query-gpu=utilization.gpu,memory.used,memory.free',
                                               '--format=csv,noheader,nounits'], timeout=3,
                                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                gpu, used, free = map(float, raw.decode().splitlines()[0].split(','))
                sample.update(gpu_util_percent=gpu, device_used_mb=used, device_free_mb=free)
            except Exception:
                sample['gpu_query_unavailable'] = True
            self.samples.append(sample)

    def stop(self):
        self.event.set()
        if self.thread:
            self.thread.join(timeout=4)
        return self.samples
