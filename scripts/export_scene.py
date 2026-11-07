"""标准训练输出→GPU服务场景包；原PLY逐字节复制，保留全部可用SH。"""
import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from backend.scene.ply import read_ply

TRAIN_COMMIT = '54c035f7834b564019656c3e3fcc3646292f727d'


def export(ply, cameras, output, index=0, source='用户训练输出', license_text='未声明，请补充数据许可', training_commit=TRAIN_COMMIT):
    """Graphdeco cameras.json 的 rotation是c2w；导出完整CV view/K并保留初始朝向。"""
    ply, output = Path(ply), Path(output)
    if output.exists():
        raise FileExistsError('输出目录已存在，不覆盖原包')
    arrays, info = read_ply(ply)
    records = json.loads(Path(cameras).read_text('utf-8'))
    camera = records[int(index)]
    rotation = np.asarray(camera['rotation'], dtype=float)
    position = np.asarray(camera['position'], dtype=float)
    if rotation.shape != (3, 3) or position.shape != (3,) or not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-3):
        raise ValueError('训练相机旋转/位置格式无效')
    view = np.eye(4)
    view[:3, :3], view[:3, 3] = rotation.T, -rotation.T @ position
    depths = (arrays['means'] - position) @ rotation[:, 2]
    positive = depths[depths > .001]
    distance = float(np.median(positive)) if len(positive) else info['radius'] * 2.8
    width, height = int(camera['width']), int(camera['height'])
    preset = {'world_to_camera': view.tolist(), 'position': position.tolist(),
              'center': (position + rotation[:, 2] * distance).tolist(), 'up': (-rotation[:, 1]).tolist(),
              'width': width, 'height': height, 'fx': float(camera['fx']), 'fy': float(camera['fy']),
              'cx': float(camera.get('cx', width / 2)), 'cy': float(camera.get('cy', height / 2)),
              'near': max(info['radius'] * 1e-4, .0001), 'far': max(distance * 100, info['radius'] * 100)}
    output.mkdir(parents=True)
    shutil.copy2(ply, output / 'scene.ply')
    if hashlib.sha256((output / 'scene.ply').read_bytes()).hexdigest() != info['source_sha256']:
        raise RuntimeError('PLY 复制校验失败')
    (output / 'camera.json').write_text(json.dumps(preset, ensure_ascii=False, indent=2), 'utf-8')
    manifest = {'source': source, 'training_repository': 'https://github.com/graphdeco-inria/gaussian-splatting',
                'training_commit': training_commit, 'license': license_text, 'gaussians': info['actual'],
                'available_sh_degree': info['available_sh_degree'], 'ply_sha256': info['source_sha256'],
                'camera_index': index, 'coordinate_system': 'CV +X right, +Y down, +Z forward; world units unchanged',
                'conversion': 'PLY原样复制，不丢字段、不重新激活、不抽样；只转换相机JSON'}
    (output / 'source.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), 'utf-8')
    (output / 'LICENSE.txt').write_text(license_text, 'utf-8')
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ply', type=Path, required=True)
    parser.add_argument('--cameras', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--camera-index', type=int, default=0)
    parser.add_argument('--source', default='本组COLMAP/训练数据')
    parser.add_argument('--license', default='未声明，请补充数据许可')
    parser.add_argument('--training-commit', default=TRAIN_COMMIT)
    args = parser.parse_args()
    print(json.dumps(export(args.ply, args.cameras, args.output, args.camera_index, args.source, args.license, args.training_commit), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
