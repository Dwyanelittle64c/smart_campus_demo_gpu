"""后端显式模块注册表及懒服务容器；关闭模块不导入专属重依赖。"""
import importlib
from shared.config import MODULES

REGISTRY = {'scene': 'backend.scene.service', 'traffic': 'backend.traffic.service', 'face': 'backend.face.service'}
SERVICES = {}


def get_service(name):
    """服务对象本身不加载模型；模块关闭时连服务模块也不导入。"""
    if not MODULES.get(name):
        raise ValueError(f'{name} 模块已关闭')
    if name not in SERVICES:
        SERVICES[name] = importlib.import_module(REGISTRY[name]).service
    return SERVICES[name]


async def release_control():
    """等受控 GPU 项结束，再卸载当前控制会话的 mutable 状态及模型缓存。"""
    import asyncio
    from backend.core.scheduler import scheduler
    if 'traffic' in SERVICES:
        await SERVICES['traffic'].stop()
    while scheduler.running or scheduler.pending:
        await asyncio.sleep(.01)
    def unload():
        for name, service in SERVICES.items():
            if name == 'traffic':
                service.unload()
            else:
                service.close()
    if SERVICES:
        await scheduler.submit('diagnostic', unload)
