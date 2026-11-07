"""单进程 Django HTTP 与原生 ASGI WS；正常启动/健康检查不接触 CUDA。"""
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
from django.core.asgi import get_asgi_application

django_app = get_asgi_application()


async def application(scope, receive, send):
    if scope['type'] == 'lifespan':
        while True:
            event = await receive()
            if event['type'] == 'lifespan.startup':
                await send({'type': 'lifespan.startup.complete'})
            elif event['type'] == 'lifespan.shutdown':
                from backend.core.state import release_control
                from backend.core.scheduler import scheduler
                await release_control()
                await scheduler.close()
                await send({'type': 'lifespan.shutdown.complete'})
                return
    elif scope['type'] == 'websocket':
        from backend.streams import websocket
        await websocket(scope, receive, send)
    else:
        await django_app(scope, receive, send)
