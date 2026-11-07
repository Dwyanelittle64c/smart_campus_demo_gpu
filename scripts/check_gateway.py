"""真实双进程 HTTP/WS 验证；这是协议/业务检查，不冒充浏览器显示 FPS。"""
import asyncio
import json
import math
import sys
import uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
import websockets
from shared.config import ROOT, DATA
from shared.protocol import unpack_frame

URL = 'http://127.0.0.1:8010'
WS = 'ws://127.0.0.1:8010/ws/'


async def main():
    async with httpx.AsyncClient(base_url=URL, trust_env=False, timeout=45) as client:
        home = await client.get('/')
        assert home.status_code == 200
        csrf = client.cookies['csrftoken']
        assert (await client.post('/api/traffic/control/', json={'action': 'start'})).status_code == 403
        async with websockets.connect(WS + 'control', origin=URL) as control:
            hello = json.loads(await control.recv())
            assert hello.get('session_id'), hello
            session = hello['session_id']
            headers = {'X-Control-Session': session, 'X-CSRFToken': csrf}
            async with websockets.connect(WS + 'control', origin=URL) as second:
                rejected = json.loads(await second.recv())
                assert rejected.get('error'), rejected
            async def post(route, body):
                response = await client.post('/api/' + route, json=body, headers=headers)
                assert response.status_code == 200, (route, response.text)
                return response.json()['data']
            frames = []
            async with websockets.connect(WS + 'scene', origin=URL, max_queue=1) as scene:
                await scene.send(json.dumps({'session_id': session}))
                epoch = json.loads(await scene.recv())['epoch']
                for i in range(6):
                    await scene.send(json.dumps({'op': 'camera', 'request_id': i + 1, 'client_time': i,
                                                  'state': {'yaw': i * .03, 'pitch': 0, 'zoom': 1}}))
                    message = await asyncio.wait_for(scene.recv(), timeout=15)
                    assert isinstance(message, bytes), message
                    meta, jpeg = unpack_frame(message)
                    assert meta['epoch'] == epoch and meta['actual'] == 113648 and meta['resolution'] == [640, 480]
                    assert meta['device'] == 'cuda:0'
                    frames.append(meta)
                # 连续高频输入时只覆盖待办；慢读没有无界应用层队列。
                for i in range(100):
                    await scene.send(json.dumps({'op': 'camera', 'request_id': 10 + i, 'client_time': i, 'state': {'yaw': .4 + i * .001}}))
                await asyncio.sleep(.5)
                seen = []
                while True:
                    try:
                        raw = await asyncio.wait_for(scene.recv(), timeout=.3)
                        if isinstance(raw, bytes):
                            meta, _ = unpack_frame(raw)
                            seen.append(meta)
                    except asyncio.TimeoutError:
                        break
                assert seen and seen[-1]['request_id'] == 109 and seen[-1]['input_overwritten'] > 0
                await scene.send(json.dumps({'op': 'reset', 'request_id': 200, 'client_time': 0, 'state': {'yaw': 0, 'pitch': 0, 'zoom': 1}}))
                next_epoch = json.loads(await scene.recv())['epoch']
                assert epoch != next_epoch
                reset, _ = unpack_frame(await scene.recv())
                assert reset['epoch'] == next_epoch
            started = await post('traffic/control/', {'action': 'start', 'source': {'type': 'video', 'asset_id': 'vtest'}})
            async with websockets.connect(WS + 'traffic', origin=URL) as stream:
                await stream.send(json.dumps({'session_id': session}))
                records = []
                while len(records) < 3:
                    raw = await asyncio.wait_for(stream.recv(), timeout=20)
                    assert isinstance(raw, bytes), raw
                    meta, image = unpack_frame(raw)
                    assert meta['source_id'] == started['source_id']
                    assert meta['device'] == 'cuda:0' and meta['forward_input_device'].startswith('cuda')
                    assert all(device.startswith('cuda') for device in meta['forward_output_devices'])
                    records.append(meta)
                (ROOT / 'docs/performance/traffic-real.jpg').write_bytes(image)
                pause = await post('traffic/control/', {'action': 'pause'})
                await asyncio.sleep(.5)
                after = (await client.get('/api/traffic/status/')).json()['data']
                assert pause['elapsed'] == after['elapsed'], (pause['elapsed'], after['elapsed'])
                await post('traffic/control/', {'action': 'stop'})
            request_id = uuid.uuid4().hex
            async def recognize():
                return await client.post('/api/face/submit/', headers=headers, data={'action': 'recognize', 'request_id': request_id},
                    files={'photo': ('public.jpg', (DATA / 'test_faces/obama-2012.jpg').read_bytes(), 'image/jpeg')})
            first, repeated = await recognize(), await recognize()
            assert first.status_code == repeated.status_code == 200, first.text
            event = first.json()['data']
            assert event['id'] == repeated.json()['data']['id'] and event['passed']
            assert event['metrics']['device'] == 'CUDAExecutionProvider'
            report = {'scene_frames': frames, 'burst_completed': len(seen), 'burst_latest': seen[-1], 'epoch_reset': True,
                      'second_control_rejected': rejected['error'], 'csrf_rejected': True, 'traffic_frames': records,
                      'pause_frozen': True, 'face_idempotent_event': event, 'passed': True}
            (ROOT / 'docs/setup/gateway-check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
            print('HTTP/WS 双进程、控制占用、背压、epoch、CUDA交通、暂停、真实人脸幂等：通过')


if __name__ == '__main__':
    asyncio.run(main())
