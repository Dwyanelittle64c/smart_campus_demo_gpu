"""显式启动 web/gpu 单进程 ASGI；不使用自动重载或 WSGI runserver。"""
import argparse
import asyncio
import json
import os
import sys
import uuid
import socket
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('role', choices=['web', 'gpu'])
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int)
    parser.add_argument('--config')
    args = parser.parse_args()
    if args.config:
        os.environ['CAMPUS_CONFIG'] = args.config
    role = 'backend' if args.role == 'gpu' else 'web'
    if args.role == 'gpu':
        # RTSP URL可能含密码；底层FFmpeg日志静音，API只输出清理过的中文错误。
        os.environ.setdefault('OPENCV_FFMPEG_LOGLEVEL', '-8')
    from shared.config import ROOT, DATA
    import uvicorn
    port = args.port or (8011 if args.role == 'gpu' else 8010)
    # 在写运行记录之前核对端口，重复启动不能覆盖正在工作的实例停止凭据。
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((args.host, port))
        except OSError as exc:
            raise SystemExit(f'端口 {args.host}:{port} 已占用；保留现有服务，请直接访问或选择其他端口') from exc
    folder = DATA / 'runtime/servers'
    folder.mkdir(parents=True, exist_ok=True)
    record = folder / f'{args.role}-{port}.json'
    nonce = uuid.uuid4().hex
    stop_file = folder / f'{args.role}-{port}-{nonce}.stop'
    server = uvicorn.Server(uvicorn.Config(role + '.asgi:application', host=args.host, port=port,
                           workers=1, reload=False, ws_max_queue=2, ws_max_size=8 * 1024 * 1024,
                           timeout_keep_alive=10, timeout_graceful_shutdown=15, access_log=False))

    async def run_server():
        """受控停止文件只置 should_exit，仍由 Uvicorn 正常关闭连接/ASGI lifespan。"""
        async def watch():
            while True:
                await asyncio.sleep(.5)
                if stop_file.is_file() and stop_file.read_text('utf-8') == nonce:
                    server.should_exit = True
                    return
        record.write_text(json.dumps({'pid': os.getpid(), 'role': args.role, 'port': port, 'root': str(ROOT),
                                      'nonce': nonce, 'stop_file': str(stop_file)}), 'utf-8')
        watcher = asyncio.create_task(watch())
        try:
            await server.serve()
        finally:
            watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)
            stop_file.unlink(missing_ok=True)
            if record.is_file() and json.loads(record.read_text('utf-8')).get('nonce') == nonce:
                record.unlink()
    asyncio.run(run_server())
