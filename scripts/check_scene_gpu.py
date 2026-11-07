"""显式准备：载入 CUDA 扩展与全量 Houseplant，保存真实两视角及硬件证据。"""
import json
import argparse
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shared.config import ROOT, DATA, CONFIG


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--expected-count', type=int, help='可选的来源数量核对；自有校园包不必等于Houseplant')
    args = parser.parse_args()
    import cv2
    import numpy as np
    import torch
    from backend.scene.renderer import Renderer
    start = time.perf_counter()
    package = DATA / CONFIG['scene']['package']
    renderer = Renderer(package, CONFIG['device'])
    width, height = CONFIG['scene']['width'], CONFIG['scene']['height']
    label = 'houseplant' if package.name == 'plant' else 'scene'
    output = ROOT / 'docs/performance'
    output.mkdir(parents=True, exist_ok=True)
    records = []
    images = []
    for yaw in (0, .6):
        for _ in range(3):
            _, meta, rgb = renderer.render({'yaw': yaw}, width, height)
        assert meta['actual'] == meta['original'] and rgb.shape == (height, width, 3)
        if args.expected_count is not None:
            assert meta['actual'] == args.expected_count
        coverage = float((rgb.max(axis=-1) > 8).mean())
        assert coverage > .02
        cv2.imwrite(str(output / f'{label}-view-{yaw}.png'), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
        images.append(rgb)
        records.append({**meta, 'nonblack_coverage': coverage})
    difference = float(np.abs(images[0].astype(float) - images[1]).mean())
    assert difference > .5
    report = {'scene_package': str(package), 'expected_count': args.expected_count,
              'gpu': torch.cuda.get_device_name(0), 'capability': torch.cuda.get_device_capability(0),
              'torch': torch.__version__, 'cuda_runtime': torch.version.cuda, 'cudnn': torch.backends.cudnn.version(),
              'prepare_ms': (time.perf_counter() - start) * 1000, 'two_view_mae': difference, 'views': records, 'passed': True}
    folder = ROOT / 'docs/setup'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'gpu-selfcheck.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    renderer.close()


if __name__ == '__main__':
    main()
