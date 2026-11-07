"""真实 CUDA 核心的椭圆/旋转/透明遮挡/高阶SH/完整相机契约测试；合成夹具非性能场景。"""
import json
import math
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from plyfile import PlyData, PlyElement
from shared.config import ROOT
from backend.scene.renderer import Renderer
from backend.scene.camera import orbit

FOLDER = ROOT / 'docs/performance/fixtures'


def fixture(name, positions, scales, quats, colors, opacity, rest=None, camera=None):
    """标准原始 log/logit/wxyz/SH 字段写入，交给与真实场景相同 loader。"""
    path = FOLDER / name
    path.mkdir(parents=True, exist_ok=True)
    keys = ['x', 'y', 'z', *[f'scale_{i}' for i in range(3)], *[f'rot_{i}' for i in range(4)],
            *[f'f_dc_{i}' for i in range(3)], 'opacity']
    if rest is not None:
        keys.extend(f'f_rest_{i}' for i in range(rest.shape[1]))
    data = np.empty(len(positions), dtype=[(key, '<f4') for key in keys])
    arrays = [np.array(positions), np.log(scales), np.array(quats), (np.array(colors) - .5) / .28209479177387814,
              (np.log(np.array(opacity) / (1 - np.array(opacity))))[:, None]]
    if rest is not None:
        arrays.append(rest)
    matrix = np.concatenate(arrays, axis=1)
    for i, key in enumerate(keys):
        data[key] = matrix[:, i]
    PlyData([PlyElement.describe(data, 'vertex')], text=False).write(path / 'scene.ply')
    preset = {'position': [0, 0, 0], 'center': [0, 0, 2], 'up': [0, -1, 0], 'width': 160, 'height': 120,
              'fx': 140, 'fy': 140, 'cx': 80, 'cy': 60, 'near': .01, 'far': 100}
    preset.update(camera or {})
    (path / 'camera.json').write_text(json.dumps(preset), 'utf-8')
    return path


def render(path):
    import cv2
    renderer = Renderer(path)
    try:
        _, metrics, rgb = renderer.render({}, 160, 120)
        cv2.imwrite(str(path / 'output.png'), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
        return rgb, metrics
    finally:
        renderer.close()


def covariance(image):
    """只统计输出图像，检验形状；不是渲染算法。"""
    weight = image.mean(axis=-1).astype(float)
    yy, xx = np.indices(weight.shape)
    x, y = xx - (xx * weight).sum() / weight.sum(), yy - (yy * weight).sum() / weight.sum()
    return np.array([[(x*x*weight).sum(), (x*y*weight).sum()], [(x*y*weight).sum(), (y*y*weight).sum()]]) / weight.sum()


def main():
    normal, _ = render(fixture('ellipse', [[0, 0, 2]], [[.3, .06, .06]], [[1, 0, 0, 0]], [[1, 1, 1]], [.8]))
    cov = covariance(normal)
    aspect = float(np.sqrt(cov[0, 0] / cov[1, 1]))
    assert aspect > 4
    rotated, _ = render(fixture('rotated', [[0, 0, 2]], [[.3, .06, .06]], [[math.cos(math.pi/8), 0, 0, math.sin(math.pi/8)]], [[1, 1, 1]], [.8]))
    rot_cov = covariance(rotated)
    correlation = float(rot_cov[0, 1] / np.sqrt(rot_cov[0, 0] * rot_cov[1, 1]))
    assert correlation > .85
    overlap, _ = render(fixture('occlusion', [[0, 0, 3], [0, 0, 2]], [[.2]*3, [.2]*3], [[1, 0, 0, 0]]*2, [[1, 0, 0], [0, 0, 1]], [.7, .7]))
    pixel = overlap[60, 80].tolist()
    assert 40 < pixel[0] < 65 and pixel[1] < 3 and 165 < pixel[2] < 185, pixel
    off, _ = render(fixture('full-intrinsics', [[.02, .03, 2]], [[.02]*3], [[1, 0, 0, 0]], [[1, 0, 0]], [.9], camera={'fx': 150, 'fy': 200, 'cx': 80, 'cy': 50}))
    peak_y, peak_x = np.unravel_index(off[:, :, 0].argmax(), off.shape[:2])
    assert abs(peak_x - 81.5) < 2 and abs(peak_y - 53) < 2, (peak_x, peak_y)
    rest = np.zeros((1, 9), np.float32)
    rest[0, 2] = .5  # INRIA red 的 l=1,m=+1；方向基为 -C1*x。
    red = []
    for sign in (-1, 1):
        image, meta = render(fixture('sh-direction-' + str(sign), [[0, 0, 2]], [[.18]*3], [[1, 0, 0, 0]], [[.5]*3], [.9], rest,
                                      {'position': [sign*.5, 0, 0]}))
        red.append(int(image[60, 80, 0]))
        assert meta['sh_degree'] == 1
    assert red[1] - red[0] > 15, red
    known = np.array([[0, -1, 0, .2], [1, 0, 0, -.1], [0, 0, 1, 0], [0, 0, 0, 1]], dtype=float)
    view, _, _, _ = orbit({'world_to_camera': known.tolist()}, {}, 160, 120, [0, 0, 0], 1)
    assert np.allclose(view, known, atol=1e-6)
    report = {'ellipse_aspect': aspect, 'rotation_correlation': correlation, 'occlusion_rgb': pixel,
              'off_center_peak': [int(peak_x), int(peak_y)], 'degree1_red_by_camera_x': red, 'cv_view_preserved': True, 'passed': True}
    (FOLDER / 'results.json').write_text(json.dumps(report, indent=2), 'utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
