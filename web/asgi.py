"""Django HTTP + 单目标双向 WS 网关；背压直接传播，不在网关堆积帧。"""
import asyncio
import os
from urllib.parse import urlsplit
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'web.settings')
from django.core.asgi import get_asgi_application
from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler
from shared.config import CONFIG, backend_headers

django_app = ASGIStaticFilesHandler(get_asgi_application())


async def application(scope, receive, send):
    """WS 只允许固定路由与预期 Origin；实例凭证由服务端添加。"""
    if scope['type'] == 'lifespan':
        while True:
            event = await receive()
            if event['type'] == 'lifespan.startup':
                await send({'type': 'lifespan.startup.complete'})
            elif event['type'] == 'lifespan.shutdown':
                await send({'type': 'lifespan.shutdown.complete'})
                return
    if scope['type'] != 'websocket':
        await django_app(scope, receive, send)
        return
    headers = dict(scope['headers'])
    origin = headers.get(b'origin', b'').decode()
    path = scope['path']
    if origin not in CONFIG['allowed_origins'] or path not in ('/ws/control', '/ws/scene', '/ws/traffic'):
        await send({'type': 'websocket.close', 'code': 4403})
        return
    import websockets
    target = CONFIG['backend_url'].replace('https://', 'wss://').replace('http://', 'ws://').rstrip('/') + path
    if (await receive())['type'] != 'websocket.connect':
        return
    downstream_closed = False
    try:
        async with websockets.connect(target, additional_headers=backend_headers(), origin=origin,
                                      max_size=8 * 1024 * 1024, max_queue=2, write_limit=65536) as upstream:
            await send({'type': 'websocket.accept'})

            async def upload():
                nonlocal downstream_closed
                while True:
                    message = await receive()
                    if message['type'] == 'websocket.disconnect':
                        downstream_closed = True
                        return
                    await upstream.send(message.get('bytes') if message.get('bytes') is not None else message.get('text', ''))

            async def download():
                async for message in upstream:
                    await send({'type': 'websocket.send', 'bytes': message} if isinstance(message, bytes)
                               else {'type': 'websocket.send', 'text': message})
            tasks = [asyncio.create_task(upload()), asyncio.create_task(download())]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if not downstream_closed:
                await send({'type': 'websocket.close', 'code': 1012, 'reason': 'GPU 流已结束，请重新连接'})
    except Exception:
        if not downstream_closed:
            try:
                await send({'type': 'websocket.close', 'code': 1013, 'reason': 'GPU 后端未连接或流已关闭'})
            except RuntimeError:
                pass
