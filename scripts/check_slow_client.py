"""模拟120ms发送消费者，实际CUDA出图检查单槽覆盖；不冒称远程/网页FPS。"""
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shared.config import ROOT
from shared.protocol import unpack_frame
from backend.core.ownership import ownership
from backend.core.scheduler import scheduler
from backend.streams import scene


async def main():
    import os
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
    session = ownership.acquire()
    queue = asyncio.Queue(maxsize=2)
    records = []
    async def receive():
        return await queue.get()
    async def send(message):
        if message.get('bytes'):
            await asyncio.sleep(.12)
            metadata, _ = unpack_frame(message['bytes'])
            records.append(metadata)
    task = asyncio.create_task(scene(receive, send, session))
    for index in range(160):
        command = {'op':'camera','request_id':index+1,'client_time':index,'state':{'yaw':index*.002,'zoom':1}}
        await queue.put({'type':'websocket.receive','text':json.dumps(command)})
        await asyncio.sleep(.02)
    await asyncio.sleep(.5)
    await queue.put({'type':'websocket.disconnect'})
    await task
    ownership.release(session)
    await scheduler.close()
    assert len(records)>3 and records[-1]['request_id']==160
    assert records[-1]['output_overwritten']>0
    assert all(b['frame_id']>a['frame_id'] for a,b in zip(records,records[1:]))
    result = {'simulation':'ASGI发送端每张JPEG延迟120ms，真实全量CUDA渲染；不模拟A100硬件',
              'delivered':len(records),'last':records[-1],'frames':records,'queue_limit':1,'passed':True}
    (ROOT/'docs/setup/slow-consumer.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8')
    print('慢消费者覆盖数',records[-1]['output_overwritten'],'交付',len(records),'张递增新帧，最新请求160已到达')


if __name__ == '__main__':
    asyncio.run(main())
