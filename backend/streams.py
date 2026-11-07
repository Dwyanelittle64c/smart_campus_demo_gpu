"""持久控制/GS/交通连接；每个流输入和输出单槽背压，元数据与 JPEG 同消息。"""
import asyncio
import json
import time
import uuid
from shared.config import MODULES
from shared.protocol import pack_frame, unpack_frame
from backend.core.ownership import ownership
from backend.core.scheduler import scheduler
from backend.core.state import get_service, release_control

ACTIVE_STREAMS = set()


async def send_json(send, value):
    await send({'type': 'websocket.send', 'text': json.dumps(value, ensure_ascii=False)})


async def control(receive, send):
    """控制 socket 维持独占租约；心跳超时/关闭释放 GPU 模型、交通及控制权。"""
    session = None
    try:
        session = ownership.acquire()
        await send_json(send, {'type': 'control', 'session_id': session})
        while True:
            message = await asyncio.wait_for(receive(), timeout=22)
            if message['type'] == 'websocket.disconnect':
                break
            data = json.loads(message.get('text', '{}'))
            if data.get('op') == 'ping':
                ownership.heartbeat(session)
                await send_json(send, {'type': 'pong'})
    except asyncio.TimeoutError:
        await send_json(send, {'error': '控制心跳超时，资源已释放'})
    except ValueError as exc:
        await send_json(send, {'error': str(exc)})
        await send({'type': 'websocket.close', 'code': 4409})
    finally:
        if session:
            # 回收尚未结束时仍保持占用，避免新控制会话与旧模型卸载交错。
            if ownership.session == session:
                ownership.deadline = float('inf')
                ownership.closing = True
            try:
                await release_control()
            finally:
                ownership.release(session)


async def scene(receive, send, session):
    """状态持续变化也展示每个完成帧；不要求 request_id 等于最新输入。"""
    service = get_service('scene')
    pending = None
    event = asyncio.Event()
    output = asyncio.Queue(maxsize=1)
    epoch = uuid.uuid4().hex
    frame_id = 0
    last_state = None
    counters = {'input_overwritten': 0, 'output_overwritten': 0, 'input_received': 0}

    async def inputs():
        nonlocal pending, last_state, epoch
        while True:
            message = await receive()
            if message['type'] == 'websocket.disconnect':
                return
            ownership.require(session)
            command = json.loads(message.get('text', '{}'))
            if command.get('op') == 'reset':
                epoch = uuid.uuid4().hex
                last_state = None
                while not output.empty():
                    output.get_nowait()
                await send_json(send, {'type': 'epoch', 'epoch': epoch})
            if command.get('op') not in ('camera', 'reset'):
                continue
            key = json.dumps([command.get('state', {}), command.get('width'), command.get('height')], sort_keys=True)
            if key == last_state:
                continue
            last_state = key
            if pending is not None:
                counters['input_overwritten'] += 1
            counters['input_received'] += 1
            pending = (command, epoch, time.perf_counter())
            event.set()

    async def render():
        nonlocal pending, frame_id, last_state
        while True:
            await event.wait()
            event.clear()
            command, work_epoch, received = pending
            pending = None
            ownership.require(session)
            try:
                payload, meta = await scheduler.submit('scene', service.render, command)
                if work_epoch != epoch or session != ownership.session:
                    continue
                frame_id += 1
                if output.full():
                    output.get_nowait()
                    counters['output_overwritten'] += 1
                meta.update(stream='scene', epoch=epoch, session_id=session, frame_id=frame_id,
                            request_id=int(command.get('request_id', 0)), client_time=float(command.get('client_time', 0)),
                            state=command.get('state', {}), request_to_ready_ms=(time.perf_counter() - received) * 1000,
                            **counters)
                item = pack_frame(meta, payload)
                output.put_nowait(item)
            except Exception as exc:
                last_state = None
                await send_json(send, {'error': str(exc)})

    async def frames():
        while True:
            payload = await output.get()
            await send({'type': 'websocket.send', 'bytes': payload})

    await send_json(send, {'type': 'epoch', 'epoch': epoch})
    tasks = [asyncio.create_task(inputs()), asyncio.create_task(render()), asyncio.create_task(frames())]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            if not task.cancelled() and task.exception():
                await send_json(send, {'error': str(task.exception())})
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        pending = None
        while scheduler.running == 'scene' or 'scene' in scheduler.pending:
            await asyncio.sleep(.01)
        await scheduler.submit('scene', service.close)


async def traffic(receive, send, session):
    """订阅只读最新结果，不启动推理；同连接允许有界浏览器采集帧上行。"""
    service = get_service('traffic')
    output = asyncio.Queue(maxsize=1)
    service.subscribers.add(output)
    if service.latest:
        output.put_nowait(service.latest)

    async def inputs():
        while True:
            message = await receive()
            if message['type'] == 'websocket.disconnect':
                return
            ownership.require(session)
            if message.get('bytes') is not None:
                meta, raw = unpack_frame(message['bytes'])
                if meta.get('source_id') != service.source_id:
                    continue
                service.camera_frame(meta, raw)

    async def frames():
        while True:
            meta, payload = await output.get()
            ownership.require(session)
            await send({'type': 'websocket.send', 'bytes': pack_frame(meta, payload)})
    tasks = [asyncio.create_task(inputs()), asyncio.create_task(frames())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        service.subscribers.discard(output)


async def websocket(scope, receive, send):
    """模块开关、控制身份与固定路由检查；初始小 JSON 不把会话放 URL。"""
    from backend.views import authorized
    from shared.config import CONFIG
    headers = {key.decode().title(): value.decode() for key, value in scope['headers']}
    if not authorized(headers) or headers.get('Origin') not in CONFIG['allowed_origins']:
        await send({'type': 'websocket.close', 'code': 4403})
        return
    if (await receive())['type'] != 'websocket.connect':
        return
    path = scope['path']
    module = path.rsplit('/', 1)[-1]
    if module not in ('control', 'scene', 'traffic') or (module in MODULES and not MODULES[module]):
        await send({'type': 'websocket.close', 'code': 4404})
        return
    await send({'type': 'websocket.accept'})
    if module == 'control':
        await control(receive, send)
        return
    try:
        message = await asyncio.wait_for(receive(), timeout=5)
        hello = json.loads(message.get('text', '{}'))
        session = hello.get('session_id')
        ownership.require(session)
        key = (session, module)
        if key in ACTIVE_STREAMS:
            raise ValueError('该控制会话已有同类流，不能启动重复任务')
        ACTIVE_STREAMS.add(key)
        try:
            await (scene if module == 'scene' else traffic)(receive, send, session)
        finally:
            ACTIVE_STREAMS.discard(key)
    except (ValueError, asyncio.TimeoutError) as exc:
        await send_json(send, {'error': str(exc)})
    finally:
        try:
            await send({'type': 'websocket.close', 'code': 1000})
        except RuntimeError:
            pass  # 客户端已断开时协议已完成，不能再次发送 close。
