"""单 GPU worker 的公平轮转调度；每模块至多一个提交项，模型延迟加载。"""
import asyncio
from concurrent.futures import ThreadPoolExecutor


class Scheduler:
    """输入同步 callable，输出异步结果；阻塞推理不会占用 ASGI 事件循环。"""
    def __init__(self):
        self.pending = {}
        self.event = None
        self.task = None
        self.executor = None
        self.last = -1
        self.running = None

    async def submit(self, module, function, *args):
        """调用方只允许一个在途；GS 另在相机入口覆盖最新状态。"""
        if module in self.pending:
            raise RuntimeError(f'{module} 待办已占用，请等待当前任务')
        if self.task is None:
            self.event = asyncio.Event()
            self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='campus-gpu')
            self.task = asyncio.create_task(self._run())
        future = asyncio.get_running_loop().create_future()
        future.add_done_callback(lambda result: result.exception() if not result.cancelled() else None)
        self.pending[module] = (function, args, future)
        self.event.set()
        return await asyncio.shield(future)

    async def _run(self):
        """公平选择 scene/traffic/face，持续 GS 输入不能饿死交通和人脸。"""
        order = ('scene', 'traffic', 'face', 'diagnostic')
        while True:
            await self.event.wait()
            selected = None
            for delta in range(1, len(order) + 1):
                index = (self.last + delta) % len(order)
                if order[index] in self.pending:
                    self.last, selected = index, order[index]
                    break
            if selected is None:
                self.event.clear()
                continue
            function, args, future = self.pending.pop(selected)
            self.running = selected
            try:
                result = await asyncio.get_running_loop().run_in_executor(self.executor, function, *args)
                if not future.done():
                    future.set_result(result)
            except Exception as exc:
                if not future.done():
                    future.set_exception(exc)
            finally:
                self.running = None
                if not self.pending:
                    self.event.clear()

    async def close(self):
        """等执行项结束，再取消空闲循环和线程池；不遗留 CUDA 后台进程。"""
        while self.running or self.pending:
            await asyncio.sleep(.02)
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None
        if self.executor:
            self.executor.shutdown(wait=True, cancel_futures=True)
            self.executor = None


scheduler = Scheduler()
