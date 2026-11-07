"""每实例一个活跃控制连接，关闭或超时立即结束其交通/GS任务。"""
import time
import uuid


class Ownership:
    """控制 ID 是短期会话；远程实例令牌由网关服务器私下传递。"""
    def __init__(self):
        self.session = None
        self.deadline = 0
        self.closing = False

    def acquire(self):
        if self.session is not None:
            raise ValueError('该 GPU 实例正由另一控制客户端使用，请使用独立实例')
        self.session = uuid.uuid4().hex
        self.deadline = time.monotonic() + 25
        return self.session

    def require(self, session):
        if self.closing or not session or session != self.session or time.monotonic() >= self.deadline:
            raise ValueError('控制会话已过期或无权操作，请重新连接')

    def heartbeat(self, session):
        self.require(session)
        self.deadline = time.monotonic() + 25

    def release(self, session):
        if self.session == session:
            self.session = None
            self.deadline = 0
            self.closing = False


ownership = Ownership()
