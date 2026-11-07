"""只复制需求白名单中的公开示例；独立存储，不迁移旧业务库或缓存。"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    *[f'data/scenes/plant/{n}' for n in ('plant.splat', 'scene.ply', 'camera.json', 'meta.json', 'source.json')],
    *[f'models/{n}' for n in ('yolov8n.pt', 'face_detection_yunet_2023mar.onnx', 'face_recognition_sface_2021dec.onnx')],
    'data/videos/vtest.avi',
    *[f'data/test_faces/{n}' for n in ('obama-2009.jpg', 'obama-2012.jpg', 'biden-2021.jpg')],
]


def main():
    """已存在文件只比较 hash，来源不同则停止，绝不覆盖。"""
    parser = argparse.ArgumentParser()
    parser.add_argument('--from-reference', type=Path, required=True)
    args = parser.parse_args()
    records = []
    for name in FILES:
        source, target = args.from_reference / name, ROOT / name
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise RuntimeError(f'目标文件与公开参考不一致，保留原文件：{name}')
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copy2(source, target)
        records.append({'path': name, 'bytes': target.stat().st_size, 'sha256': digest, 'origin': '许可公开素材，见 docs/ASSETS.md'})
    # 补全许可证后再次校验白名单，不能把已附带的许可证条目从清单丢掉。
    license_path = ROOT / 'data/scenes/plant/LICENSE.txt'
    if license_path.is_file():
        records.append({'path': license_path.relative_to(ROOT).as_posix(), 'bytes': license_path.stat().st_size,
                        'sha256': hashlib.sha256(license_path.read_bytes()).hexdigest(),
                        'origin': 'CC BY4.0完整许可，见 third_party/licenses/sources.json'})
    (ROOT / 'assets-manifest.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), 'utf-8')
    print(f'独立复制/校验 {len(records)} 个明确公开示例；未复制人员或历史')


if __name__ == '__main__':
    main()
