"""校验独立组数据播种与SfM点准备脚本；不连接A100，也不执行训练。"""
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from plyfile import PlyData

ROOT = Path(__file__).resolve().parents[1]


def main():
    base = ROOT / 'data/runtime/tests'
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=base) as name:
        folder = Path(name).resolve()
        assert folder.is_relative_to(base.resolve())
        data_root, config = folder / 'group-data', folder / 'group.json'
        command = [sys.executable, 'scripts/init_instance.py', '--data-root', str(data_root),
                   '--config-output', str(config), '--gpu-port', '18021', '--name', '公开测试独立组']
        subprocess.run(command, cwd=ROOT, check=True, capture_output=True)
        settings = json.loads(config.read_text('utf-8'))
        assert settings['backend_url'] == 'http://127.0.0.1:18021'
        assert Path(settings['data_root']) == data_root
        assert not (data_root / 'faces').exists() and not (data_root / 'recognitions').exists()
        manifest = json.loads((ROOT / 'assets-manifest.json').read_text('utf-8'))
        copied = []
        for row in manifest:
            if row['path'].startswith('data/'):
                target = data_root / Path(row['path']).relative_to('data')
                assert hashlib.sha256(target.read_bytes()).hexdigest() == row['sha256']
                copied.append(row['path'])
        assert (data_root / 'scenes/plant/LICENSE.txt').is_file()
        before = config.read_bytes()
        assert subprocess.run(command, cwd=ROOT, capture_output=True).returncode != 0
        assert config.read_bytes() == before

        points = folder / 'points3D.txt'
        points.write_text('# COLMAP fixture\n1 0 0 0 255 0 0 0.1 1 0\n2 1 0 0 0 255 0 0.1 1 1\n3 0 1 0 0 0 255 0.1 1 2\n', 'utf-8')
        original = points.read_bytes()
        output = folder / 'sparse/0/points3D.ply'
        subprocess.run([sys.executable, 'training/prepare_sparse.py', '--points-txt', str(points),
                        '--output', str(output), '--maximum', '2'], cwd=ROOT, check=True, capture_output=True)
        assert len(PlyData.read(output)['vertex']) == 2
        assert points.read_bytes() == original
        result = {'independent_public_assets': copied, 'no_people_or_history_migrated': True,
                  'existing_config_preserved': True, 'sparse_fixture': {'input': 3, 'output': 2, 'original_preserved': True},
                  'training_executed': False, 'a100_executed': False, 'passed': True}
    (ROOT / 'docs/setup/packaging-check.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf-8')
    print('独立实例公开素材/许可证/空库，以及SfM准备3→2点夹具：通过；未执行训练')


if __name__ == '__main__':
    main()
