"""轻量环境子进程检查模块关闭/缺专属包；无模型、设备或业务写入。"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHILD = r'''
import asyncio, json, sys, threading
from shared.config import MODULES
from backend.core.state import get_service, SERVICES
disabled, role = sys.argv[1:]
if disabled in MODULES:
    try: get_service(disabled)
    except ValueError: pass
    else: raise AssertionError('关闭模块仍能取得service')
import django
django.setup()
from django.test import Client
client = Client()
if role == 'web':
    response = client.get('/')
    assert response.status_code == 200
    text = response.content.decode()
    for name, enabled in MODULES.items():
        assert (f'id="{name}-module"' in text) == enabled
else:
    assert client.get('/health/').status_code == 200
    assert client.get('/api/capabilities/').status_code == 200
    if disabled in MODULES:
        route = {'scene':'scene/status/', 'traffic':'traffic/status/', 'face':'face/people/'}[disabled]
        assert client.get('/api/'+route).status_code == 404
        if disabled in ('scene','traffic'):
            from backend.streams import websocket
            events=[]
            async def receive(): return {'type':'websocket.connect'}
            async def send(value): events.append(value)
            asyncio.run(websocket({'type':'websocket','path':'/ws/'+disabled,'headers':[(b'origin',b'http://127.0.0.1:8010')]},receive,send))
            assert events[-1]['code'] == 4404
heavy=[name for name in ('torch','cv2','numpy','gsplat','onnxruntime') if name in sys.modules]
assert not heavy, heavy
assert not SERVICES
assert not any(t.name.startswith(('campus-gpu','rtsp-','benchmark-')) for t in threading.enumerate())
print(json.dumps({'role':role,'disabled':disabled,'heavy_imports':heavy,'models':0,'passed':True}))
'''


def main():
    base = ROOT / 'data/runtime/tests'
    base.mkdir(parents=True, exist_ok=True)
    results = []
    with tempfile.TemporaryDirectory(dir=base) as name:
        folder = Path(name).resolve()
        assert folder.is_relative_to(base.resolve())
        for disabled in ('scene', 'traffic', 'face', 'all'):
            config = json.loads((ROOT / 'config/local-3050.json').read_text('utf-8'))
            config['modules'] = {module: disabled not in (module, 'all') for module in config['modules']}
            config['scene']['package'] = 'MISSING-SCENE'
            config['traffic']['model'] = 'MISSING-YOLO'
            config['face']['detector'] = config['face']['recognizer'] = 'MISSING-FACE'
            config_path = folder / f'{disabled}.json'
            config_path.write_text(json.dumps(config), 'utf-8')
            for role in ('web', 'backend'):
                env = dict(os.environ, CAMPUS_CONFIG=str(config_path), DJANGO_SETTINGS_MODULE=role+'.settings', PYTHONIOENCODING='utf-8')
                child = subprocess.run([sys.executable, '-c', CHILD, disabled, role], cwd=ROOT, env=env,
                                       capture_output=True, text=True, encoding='utf-8', timeout=20)
                if child.returncode:
                    raise RuntimeError(child.stderr + child.stdout)
                results.append(json.loads(child.stdout))
    (ROOT / 'docs/setup/module-isolation.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), 'utf-8')
    print('8组无专属包/缺权重的模块关闭及轻量启动检查通过')


if __name__ == '__main__':
    main()
