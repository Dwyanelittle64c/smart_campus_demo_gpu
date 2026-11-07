"""PLY激活/SH排列、普通点云拒绝、相机内参缩放与原样场景导出契约。"""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
from plyfile import PlyData, PlyElement
from shared.config import ROOT
from backend.scene.ply import read_ply
from backend.scene.camera import orbit
from scripts.export_scene import export


class SceneContractTests(unittest.TestCase):
    def setUp(self):
        base = ROOT / 'data/runtime/tests'
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.folder = Path(self.temp.name).resolve()
        assert self.folder.is_relative_to(base.resolve())

    def tearDown(self):
        self.temp.cleanup()

    def test_ascii_log_logit_wxyz_and_sh_channel_layout(self):
        keys = ['x', 'y', 'z', 'opacity', *[f'scale_{i}' for i in range(3)], *[f'rot_{i}' for i in range(4)],
                *[f'f_dc_{i}' for i in range(3)], *[f'f_rest_{i}' for i in range(9)]]
        vertex = np.zeros(1, dtype=[(key, '<f4') for key in keys])
        vertex['z'] = 2
        vertex['opacity'] = np.log(.7 / .3)
        vertex['rot_0'] = 2
        for i, scale in enumerate((.2, .1, .05)):
            vertex[f'scale_{i}'] = np.log(scale)
        for i in range(9):
            vertex[f'f_rest_{i}'] = i + 1
        path = self.folder / 'fixture.ply'
        PlyData([PlyElement.describe(vertex, 'vertex')], text=True).write(path)
        arrays, info = read_ply(path)
        np.testing.assert_allclose(arrays['scales'][0], [.2, .1, .05], rtol=1e-6)
        np.testing.assert_allclose(arrays['opacities'], [.7], rtol=1e-6)
        np.testing.assert_allclose(arrays['quats'][0], [1, 0, 0, 0])
        np.testing.assert_allclose(arrays['colors'][0, 1], [1, 4, 7])
        self.assertEqual(info['available_sh_degree'], 1)
        camera = self.folder / 'cameras.json'
        camera.write_text(json.dumps([{'position': [0, 0, 0], 'rotation': np.eye(3).tolist(), 'width': 160, 'height': 120,
                                     'fx': 150, 'fy': 200, 'cx': 70, 'cy': 45}]), 'utf-8')
        target = self.folder / 'exported'
        manifest = export(path, camera, target, license_text='合成测试，自行生成')
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), manifest['ply_sha256'])
        self.assertEqual(path.read_bytes(), (target / 'scene.ply').read_bytes())
        self.assertEqual(manifest['available_sh_degree'], 1)
        preset = json.loads((target / 'camera.json').read_text())
        view, intrinsic, _, _ = orbit(preset, {}, 320, 240, [0, 0, 2], 1)
        np.testing.assert_allclose(view, np.eye(4), atol=1e-6)
        np.testing.assert_allclose(np.diag(intrinsic)[:2], [300, 400])
        self.assertEqual([intrinsic[0, 2], intrinsic[1, 2]], [140, 90])
        with self.assertRaises(FileExistsError):
            export(path, camera, target)

    def test_xyz_point_cloud_is_rejected(self):
        path = self.folder / 'points.ply'
        vertex = np.zeros(2, dtype=[('x', 'f4'), ('y', 'f4'), ('z', 'f4')])
        PlyData([PlyElement.describe(vertex, 'vertex')]).write(path)
        with self.assertRaises(ValueError):
            read_ply(path)
