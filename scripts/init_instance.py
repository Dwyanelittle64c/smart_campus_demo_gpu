"""为每组建立独立数据根，只播种公开示例；不迁移任何人员/历史。"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--config-output', type=Path, required=True)
    parser.add_argument('--gpu-port', type=int, default=18011)
    parser.add_argument('--name', default='教学独立实例')
    args = parser.parse_args()
    if args.config_output.exists():
        raise FileExistsError('配置已存在，保留原文件；请选择新的输出路径')
    target = args.data_root.resolve()
    manifest = json.loads((ROOT / 'assets-manifest.json').read_text('utf-8'))
    for record in manifest:
        name = record['path']
        if not name.startswith('data/'):
            continue
        relative = Path(name).relative_to('data')
        source, destination = ROOT / name, target / relative
        if destination.exists() and hashlib.sha256(destination.read_bytes()).hexdigest() != record['sha256']:
            raise ValueError(f'目标素材不同，未覆盖：{relative}')
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            shutil.copy2(source, destination)
    config = json.loads((ROOT / 'config/local-3050.json').read_text('utf-8'))
    config.update(data_root=str(target), backend_url=f'http://127.0.0.1:{args.gpu_port}', instance_name=args.name)
    args.config_output.parent.mkdir(parents=True, exist_ok=True)
    args.config_output.write_text(json.dumps(config, ensure_ascii=False, indent=2), 'utf-8')
    print('独立数据根已准备，人员/历史未迁移：', target)


if __name__ == '__main__':
    main()
