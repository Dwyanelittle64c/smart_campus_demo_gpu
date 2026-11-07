"""独立子进程隐藏CUDA/指向缺失模型，验证错误隔离；不安装CPU算法后端。"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHILD = r'''
import sys
import numpy as np
from shared.config import CONFIG, DATA
case = sys.argv[1]
try:
    if case.startswith('scene'):
        from backend.scene.renderer import Renderer
        Renderer(DATA / CONFIG['scene']['package'])
    elif case.startswith('face'):
        from backend.face.models import FaceModels
        FaceModels()
    elif case.startswith('traffic'):
        from backend.traffic.service import TrafficService
        TrafficService()._infer(np.zeros((64,64,3), np.uint8), 0)
except (RuntimeError, FileNotFoundError) as exc:
    import json
    print(json.dumps({'case':case,'error':str(exc),'passed':True}, ensure_ascii=False))
else:
    raise AssertionError('应明确失败，不能回退CPU或自动下载')
'''


def main():
    """仅临时配置生效；不变更默认配置、登记库或父进程的GPU可见性。"""
    folder = ROOT / 'data/runtime/tests'
    folder.mkdir(parents=True, exist_ok=True)
    results = []
    with tempfile.TemporaryDirectory(dir=folder) as name:
        temporary = Path(name).resolve()
        assert temporary.is_relative_to(folder.resolve())
        config = json.loads((ROOT / 'config/local-3050.json').read_text('utf-8'))
        config['scene']['package'] = 'scenes/MISSING'
        config['traffic']['model'] = 'models/MISSING.pt'
        config['face']['detector'] = 'models/MISSING.onnx'
        path = temporary / 'missing.json'
        path.write_text(json.dumps(config), 'utf-8')
        for case in ('scene-no-cuda', 'traffic-no-cuda', 'face-no-cuda',
                     'scene-missing', 'traffic-missing', 'face-missing'):
            env = dict(os.environ, PYTHONIOENCODING='utf-8')
            if case.endswith('no-cuda'):
                env['CUDA_VISIBLE_DEVICES'] = '-1'
            else:
                env['CAMPUS_CONFIG'] = str(path)
            child = subprocess.run([sys.executable, '-c', CHILD, case], cwd=ROOT, env=env,
                                   capture_output=True, text=True, encoding='utf-8', timeout=45)
            if child.returncode:
                raise RuntimeError(child.stdout + child.stderr)
            # Ultralytics可能首次打印设置提示，只解析子进程最后一行。
            results.append(json.loads(child.stdout.strip().splitlines()[-1]))
    (ROOT / 'docs/setup/failure-paths.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), 'utf-8')
    print('无CUDA/缺文件的三个模块共6组明确失败，未触发CPU回退或下载')


if __name__ == '__main__':
    main()
