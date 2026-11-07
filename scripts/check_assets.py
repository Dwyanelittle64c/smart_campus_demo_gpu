"""在新克隆上校验公开演示素材；不需要模型库、GPU、网络或旧工程。"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    manifest = json.loads((ROOT / 'assets-manifest.json').read_text('utf-8'))
    errors = []
    for row in manifest:
        path = (ROOT / row['path']).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file():
            errors.append(f"缺失或不在项目内：{row['path']}")
            continue
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if path.stat().st_size != row['bytes'] or digest != row['sha256']:
            errors.append(f"字节数或 SHA256 不符：{row['path']}")
    if errors:
        raise SystemExit('\n'.join(errors))
    print(f'公开演示素材 {len(manifest)} 项：SHA256 全部通过')


if __name__ == '__main__':
    main()
