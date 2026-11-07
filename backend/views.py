"""Django GPU API：鉴权/输入校验/文件业务，算法交给单 GPU 公平调度器。"""
import asyncio
import hashlib
import hmac
import json
import os
import uuid
from pathlib import Path
from django.http import JsonResponse, StreamingHttpResponse, HttpResponse
from shared.config import CONFIG, DATA, ROOT, MODULES, inside
from backend.core.ownership import ownership
from backend.core.scheduler import scheduler
from backend.core.state import get_service, SERVICES
from backend.core.storage import atomic_json, read_index, LOCK

FACE_REQUESTS = {}
FACE_BUSY = None
MONITOR = None


def authorized(headers):
    """远程实例令牌来自服务器环境变量，默认回环部署无公开管理面。"""
    token = os.environ.get('CAMPUS_INSTANCE_TOKEN', '')
    return not token or hmac.compare_digest(headers.get('Authorization', ''), 'Bearer ' + token)


def capabilities():
    """能力接口只读缓存证据，不加载 GPU 或主动编译。"""
    return {'modules': MODULES, 'role': 'gpu', 'instance_name': CONFIG['instance_name'], 'device_config': CONFIG['device'],
            'scene': CONFIG['scene'] if MODULES['scene'] else None,
            'prepared': (ROOT / 'docs/setup/gpu-selfcheck.json').is_file(),
            'loaded_modules': [name for name, service in SERVICES.items()
                               if getattr(service, 'renderer', None) or getattr(service, 'model', None) or getattr(service, 'models', None)]}


def health(request):
    return JsonResponse({'ok': True, 'role': 'gpu', 'modules': MODULES, 'models_loaded': False if not SERVICES else 'see capabilities'})


async def api(request, route):
    """唯一 API 分发，模块开关在服务器执行；所有写请求还需活跃控制租约。"""
    global FACE_BUSY, MONITOR
    route = route.strip('/')
    if not authorized(request.headers):
        return JsonResponse({'error': '实例认证失败'}, status=403)
    if request.method not in ('GET', 'POST'):
        return JsonResponse({'error': '不支持的方法'}, status=405)
    try:
        if route == 'capabilities' and request.method == 'GET':
            return JsonResponse({'ok': True, 'data': capabilities()})
        module = route.split('/')[0]
        if module in MODULES and not MODULES[module]:
            return JsonResponse({'error': '模块已关闭'}, status=404)
        if request.method == 'POST':
            ownership.require(request.headers.get('X-Control-Session'))
        body = json.loads(request.body or b'{}') if request.content_type == 'application/json' else {}
        if route.startswith('face/sample/') and request.method == 'GET' and MODULES['face']:
            name = route.rsplit('/', 1)[-1]
            if name not in ('obama-2009.jpg', 'obama-2012.jpg', 'biden-2021.jpg'):
                raise ValueError('公开示例名称无效')
            return HttpResponse((DATA / 'test_faces' / name).read_bytes(), content_type='image/jpeg')
        if route == 'traffic/status':
            result = get_service('traffic').snapshot()
        elif route == 'traffic/control' and request.method == 'POST':
            result = await get_service('traffic').control(body)
        elif route == 'traffic/upload' and request.method == 'POST':
            get_service('traffic')
            video = request.FILES.get('video')
            if not video or video.size > 100 * 1024 * 1024 or Path(video.name).suffix.lower() not in ('.mp4', '.avi', '.mkv', '.mov'):
                raise ValueError('请选择 100MB 内 MP4/AVI/MKV/MOV 视频')
            identifier = uuid.uuid4().hex
            name = identifier + Path(video.name).suffix.lower()
            folder = DATA / 'uploads'
            folder.mkdir(parents=True, exist_ok=True)
            def save_video():
                import cv2
                path = folder / name
                with path.open('wb') as output:
                    for chunk in video.chunks():
                        output.write(chunk)
                capture = cv2.VideoCapture(str(path))
                valid, _ = capture.read()
                capture.release()
                if not valid:
                    path.unlink(missing_ok=True)
                    raise ValueError('上传文件没有可解码视频帧')
                with LOCK:
                    index = read_index(folder / 'videos.json', {})
                    index[identifier] = name
                    atomic_json(folder / 'videos.json', index)
            await asyncio.to_thread(save_video)
            result = {'asset_id': identifier}
        elif route in ('face/people', 'face/history') and request.method == 'GET':
            function = get_service('face').people if route.endswith('people') else get_service('face').history
            result = await asyncio.to_thread(function)
        elif route == 'face/delete' and request.method == 'POST':
            result = await scheduler.submit('face', get_service('face').delete, body.get('id', ''))
        elif route == 'face/clear' and request.method == 'POST':
            result = await scheduler.submit('face', get_service('face').clear)
        elif route == 'face/submit' and request.method == 'POST':
            from backend.face.service import valid_id
            photo = request.FILES.get('photo')
            if not photo or photo.size > 20 * 1024 * 1024:
                raise ValueError('请上传 20MB 内单人照片')
            request_id = valid_id(request.POST.get('request_id', ''))
            action = request.POST.get('action', 'recognize')
            if action not in ('enroll', 'recognize'):
                raise ValueError('人脸操作无效')
            raw = photo.read()
            name = request.POST.get('name', '')
            digest = hashlib.sha256(raw + action.encode() + name.encode()).hexdigest()
            if request_id in FACE_REQUESTS:
                previous_digest, future = FACE_REQUESTS[request_id]
                if previous_digest != digest:
                    raise ValueError('同一请求 ID 不可用于不同输入')
                result = await asyncio.shield(future)
            else:
                if FACE_BUSY is not None and not FACE_BUSY.done():
                    raise ValueError('人脸处理中，请等待当前任务完成')
                service = get_service('face')
                async def execute_face():
                    if action == 'enroll':
                        return await scheduler.submit('face', service.enroll, name, raw, request_id)
                    return await scheduler.submit('face', service.recognize, raw, request_id)
                FACE_BUSY = asyncio.create_task(execute_face())
                FACE_REQUESTS[request_id] = (digest, FACE_BUSY)
                if len(FACE_REQUESTS) > 256:
                    FACE_REQUESTS.pop(next(iter(FACE_REQUESTS)))
                result = await asyncio.shield(FACE_BUSY)
        elif route == 'diagnostics/start' and request.method == 'POST':
            from backend.core.resources import Monitor
            if MONITOR:
                await asyncio.to_thread(MONITOR.stop)
            MONITOR = Monitor()
            MONITOR.start()
            result = {'monitoring': True}
        elif route == 'diagnostics/report' and request.method == 'POST':
            if MONITOR:
                body['resources'] = await asyncio.to_thread(MONITOR.stop)
                MONITOR = None
            label = str(body.get('mode', 'unknown'))
            if label not in ('gs-only', 'gs-traffic', 'gs-traffic-face', 'stability'):
                raise ValueError('验收模式无效')
            target = ROOT / 'docs/performance' / f'web-{label}.json'
            await asyncio.to_thread(atomic_json, target, body)
            result = {'saved': target.relative_to(ROOT).as_posix()}
        else:
            return JsonResponse({'error': '接口不存在或方法不正确'}, status=404)
        return JsonResponse({'ok': True, 'data': result}, json_dumps_params={'ensure_ascii': False})
    except (ValueError, FileNotFoundError, RuntimeError, KeyError) as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse({'error': f'后端处理失败：{type(exc).__name__}: {exc}'}, status=500)


async def media(request, route):
    """仅允许人员/事件的生成 JPEG；模型、特征、任意文件路径不提供下载。"""
    if not authorized(request.headers) or not MODULES['face']:
        return HttpResponse(status=403)
    import re
    if not re.fullmatch(r'(faces/[0-9a-f]{32}/(face\.jpg|original\.(jpg|png))|recognitions/images/[0-9a-f]{32}-(scene|face|candidate)\.jpg)', route):
        return HttpResponse(status=404)
    path = inside(DATA, route)
    if not path.is_file():
        return HttpResponse(status=404)
    async def chunks():
        stream = await asyncio.to_thread(path.open, 'rb')
        try:
            while True:
                part = await asyncio.to_thread(stream.read, 65536)
                if not part:
                    break
                yield part
        finally:
            stream.close()
    response = StreamingHttpResponse(chunks(), content_type='image/png' if path.suffix == '.png' else 'image/jpeg')
    response['Cache-Control'] = 'no-store'
    return response
