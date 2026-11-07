"""显式环境审计；Web拒绝重依赖，runtime可选GPU自检，普通健康不调用。"""
import argparse
import importlib.metadata as metadata
import importlib.util
import json
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('role', choices=['web', 'runtime'])
    parser.add_argument('--gpu', action='store_true')
    args = parser.parse_args()
    report = {'role': args.role, 'python': sys.version, 'prefix': sys.prefix, 'platform': platform.platform(),
              'packages': {item.metadata['Name']: item.version for item in metadata.distributions()},
              'heavy_available': {name: importlib.util.find_spec(name) is not None for name in ('torch', 'gsplat', 'onnxruntime', 'cv2')}}
    if args.role == 'web':
        assert not any(report['heavy_available'].values())
    if args.gpu:
        if args.role != 'runtime':
            raise ValueError('Web环境不能执行GPU自检')
        import torch
        import gsplat.csrc
        import onnxruntime as ort
        assert torch.cuda.is_available()
        report['gpu'] = {'name': torch.cuda.get_device_name(0), 'capability': torch.cuda.get_device_capability(0),
                         'torch': torch.__version__, 'runtime': torch.version.cuda, 'cudnn': torch.backends.cudnn.version(),
                         'memory_free_total': torch.cuda.mem_get_info(), 'ort': ort.__version__, 'providers': ort.get_available_providers()}
    check = subprocess.run([sys.executable, '-m', 'pip', 'check'], capture_output=True, text=True, encoding='utf-8')
    assert check.returncode == 0, check.stdout + check.stderr
    report['pip_check'] = check.stdout.strip()
    folder = ROOT / 'docs/setup'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f'{args.role}-environment.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
    print(json.dumps({key: value for key, value in report.items() if key != 'packages'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
