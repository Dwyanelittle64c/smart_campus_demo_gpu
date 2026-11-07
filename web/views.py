"""轻量 Django 页面与固定目标同源网关；永不导入 GPU 包。"""
import httpx
from django.http import JsonResponse, HttpResponse, StreamingHttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from shared.config import CONFIG, MODULES, backend_headers


@ensure_csrf_cookie
def home(request):
    """首页只生成 UI；后台离线也能打开，模型加载必须显式触发。"""
    return render(request, 'index.html', {'modules': MODULES})


def health(request):
    """纯 Web 健康，无 GPU 查询或线程启动。"""
    return JsonResponse({'ok': True, 'role': 'web', 'modules': MODULES})


async def proxy(request, route):
    """转发到配置中的唯一 GPU 实例；上传有大小上限，不能代理任意 URL。"""
    if request.method not in ('GET', 'POST') or '..' in route or route.startswith('/'):
        return JsonResponse({'error': '无效请求'}, status=400)
    multipart = request.content_type == 'multipart/form-data'
    if int(request.headers.get('Content-Length', 0)) > 101 * 1024 * 1024:
        return JsonResponse({'error': '上传超过 100MB'}, status=413)
    headers = {**backend_headers(), 'Content-Type': request.content_type or 'application/json'}
    if request.META.get('CONTENT_TYPE'):
        headers['Content-Type'] = request.META['CONTENT_TYPE']
    if request.headers.get('X-Control-Session'):
        headers['X-Control-Session'] = request.headers['X-Control-Session']
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=3), trust_env=False) as client:
            if multipart:
                # CSRF 中间件已解析表单；转发临时文件流，不能再读已消费的 request.body。
                files = [(key, (photo.name, photo.file, photo.content_type)) for key in request.FILES for photo in request.FILES.getlist(key)]
                headers.pop('Content-Type', None)
                options = {'files': files, 'data': request.POST.dict()}
            else:
                options = {'content': request.body}
            response = await client.request(request.method, CONFIG['backend_url'].rstrip('/') + '/api/' + route,
                                            headers=headers, params=request.GET, **options)
        return HttpResponse(response.content, status=response.status_code, content_type=response.headers.get('content-type'))
    except httpx.HTTPError:
        return JsonResponse({'error': 'GPU 后端未连接，请启动服务或检查 SSH 隧道'}, status=503)


async def media(request, route):
    """受控媒体按块透传并正确关闭上游连接，不缓存整段视频。"""
    if request.method != 'GET' or '..' in route or route.startswith('/'):
        return HttpResponse(status=400)
    client = httpx.AsyncClient(timeout=20, trust_env=False)
    try:
        response = await client.send(client.build_request('GET', CONFIG['backend_url'].rstrip('/') + '/media/' + route,
                                                         headers=backend_headers()), stream=True)
    except httpx.HTTPError:
        await client.aclose()
        return HttpResponse(status=503)

    async def chunks():
        try:
            async for chunk in response.aiter_bytes():
                yield chunk
        finally:
            await response.aclose()
            await client.aclose()
    return StreamingHttpResponse(chunks(), status=response.status_code, content_type=response.headers.get('content-type'))
