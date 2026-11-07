"""脱离 Django 的全量 CUDA 基准；每视角预热后 300 个变化帧。"""
import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from shared.config import ROOT, DATA, CONFIG


def stats(values):
    """原始样本汇总 mean/P50/P95。"""
    return {key: float(value) for key, value in zip(('mean', 'p50', 'p95'), (np.mean(values), *np.percentile(values, [50, 95])))}


def main():
    """保存真实 RGB hash、PNG、各阶段耗时；不把异步提交时间当核心 GPU 耗时。"""
    parser = argparse.ArgumentParser()
    parser.add_argument('--sizes', nargs='+', default=['640x480'])
    parser.add_argument('--frames', type=int, default=300)
    parser.add_argument('--maximum', type=int)
    args = parser.parse_args()
    import_started = time.perf_counter()
    from backend.scene.renderer import Renderer
    from backend.core.resources import Monitor
    import cv2
    import torch
    import_ms = (time.perf_counter() - import_started) * 1000
    folder = ROOT / 'docs/performance'
    folder.mkdir(parents=True, exist_ok=True)
    cold = time.perf_counter()
    monitor = Monitor()
    monitor.start()
    renderer = Renderer(DATA / CONFIG['scene']['package'], CONFIG['device'], args.maximum)
    initialize_ms = (time.perf_counter() - cold) * 1000
    first_start = time.perf_counter()
    renderer.render({'yaw': 0, 'pitch': 0, 'zoom': 1})
    cold_first_forward_ms = (time.perf_counter() - first_start) * 1000
    results = []
    for size in args.sizes:
        width, height = map(int, size.split('x'))
        for name, yaw, zoom in [('default', 0, 1), ('rotation', .65, 1), ('zoom', .1, .75), ('near-stress', .1, .35)]:
            def state(i):
                return {'yaw': yaw + .04 * math.sin(i * .029), 'pitch': .015 * math.sin(i * .03), 'zoom': zoom}
            for i in range(20):
                renderer.render(state(i), width, height)
            samples, hashes, coverage = [], set(), []
            start = time.perf_counter()
            for i in range(args.frames):
                payload, meta, rgb = renderer.render(state(i + 20), width, height)
                samples.append(meta)
                hashes.add(hashlib.sha256(rgb.tobytes()).hexdigest())
                coverage.append(float((rgb.max(axis=-1) > 8).mean()))
                if i in (0, args.frames // 2, args.frames - 1):
                    cv2.imwrite(str(folder / f'{renderer.info["actual"]}-{size}-{name}-{i}.png'), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
            elapsed = time.perf_counter() - start
            keys = ['core_ms', 'gpu_convert_ms', 'copy_ms', 'pixel_convert_ms', 'encode_ms', 'server_ms']
            result = {'view': name, 'resolution': [width, height], 'scene': renderer.info, 'frames': args.frames,
                      'distinct_rgb': len(hashes), 'coverage_min': min(coverage), 'visible_min': min(s['visible'] for s in samples),
                      'fps': args.frames / elapsed, 'timings': {k: stats([s[k] for s in samples]) for k in keys}, 'samples': samples}
            results.append(result)
            print(name, size, 'coreP95', round(result['timings']['core_ms']['p95'], 3), 'FPS', round(result['fps'], 1), flush=True)
    resources = monitor.stop()
    output = {'import_ms': import_ms, 'scene_initialize_ms': initialize_ms, 'cold_first_forward_ms': cold_first_forward_ms,
              'peak_allocated_mb': torch.cuda.max_memory_allocated() / 2**20,
              'torch': torch.__version__, 'cuda_runtime': torch.version.cuda,
              'results': results, 'resources': resources}
    target = folder / f'native-{renderer.info["actual"]}.json'
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2), 'utf-8')
    renderer.close()


if __name__ == '__main__':
    main()
