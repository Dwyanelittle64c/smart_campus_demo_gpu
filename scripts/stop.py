"""向本工程自己的 ASGI 进程请求优雅退出；不扫描/结束旧项目，不按端口强杀进程。"""
import argparse
import json
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('role', choices=['web', 'gpu', 'all'])
    parser.add_argument('--port', type=int)
    parser.add_argument('--config')
    args = parser.parse_args()
    if args.config:
        import os
        os.environ['CAMPUS_CONFIG'] = args.config
    from shared.config import ROOT, DATA
    folder = (DATA / 'runtime/servers').resolve()
    roles = ('web', 'gpu') if args.role == 'all' else (args.role,)
    for role in roles:
        port = args.port or (8010 if role == 'web' else 8011)
        record = folder / f'{role}-{port}.json'
        if not record.is_file():
            print(role, '没有本工程运行记录（不操作其他服务）')
            continue
        value = json.loads(record.read_text('utf-8'))
        target = Path(value['stop_file']).resolve()
        if value['root'] != str(ROOT) or not target.is_relative_to(folder) or target.suffix != '.stop':
            raise RuntimeError('停止目标不属于本工程，拒绝操作')
        target.write_text(value['nonce'], 'utf-8')
        deadline = time.monotonic() + 25
        while record.exists() and time.monotonic() < deadline:
            time.sleep(.2)
        if record.exists():
            raise RuntimeError(f'{role} 未在25秒内退出；保留记录，请查看服务终端。没有强杀任何进程。')
        print(role, '已正常退出并清理运行记录')


if __name__ == '__main__':
    main()
