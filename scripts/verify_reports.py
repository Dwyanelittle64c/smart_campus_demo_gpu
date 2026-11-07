"""对原始GPU/网页成绩做数量、时间、hash、设备、质量与执行证据复核。"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'docs/performance'


def main():
    native = json.loads((FOLDER / 'native-113648.json').read_text('utf-8'))
    assert len(native['results']) == 12
    for result in native['results']:
        assert result['frames'] >= 300 and result['distinct_rgb'] == result['frames'] and result['coverage_min'] > .02
        assert result['scene']['actual'] == result['scene']['original'] == 113648
        for frame in result['samples']:
            assert frame['device'].startswith('cuda') and frame['quality']['radius_clip'] == 0
        if result['resolution'] == [640, 480]:
            assert result['timings']['core_ms']['p95'] < 50
    reports = []
    for mode in ('gs-only','gs-traffic','gs-traffic-face','stability'):
        data = json.loads((FOLDER / f'web-{mode}.json').read_text('utf-8'))
        frames = data['frames']
        assert data['visibility'] == 'visible' and data['web_fps'] >= 20
        assert data['duration_seconds'] == (600 if mode == 'stability' else 60)
        assert len(frames) == data['frame_count'] == data['distinct_frames'] == len({frame['hash'] for frame in frames})
        assert frames[-1]['displayed_ms']-frames[0]['displayed_ms'] > (data['duration_seconds']-1)*1000
        assert all(b['frame_id'] > a['frame_id'] for a,b in zip(frames,frames[1:]))
        assert len({frame['epoch'] for frame in frames}) == 1
        assert all(frame['actual']==frame['input']==113648 and frame['resolution']==[640,480] and frame['sh_degree']==0 for frame in frames)
        assert all(.7999 <= frame['state']['zoom'] <= 1.0001 and frame['quality']['radius_clip']==0 for frame in frames)
        assert data['core_ms']['p95'] < 50 and data['latency_ms']['p95'] <= 150
        if mode in ('gs-traffic','gs-traffic-face'):
            start, end = data['traffic_start'], data['traffic_end']
            assert end['status']=='running' and end['frame_id']>start['frame_id']+100 and end['elapsed']>start['elapsed']+50
            assert end['forward_input_device'].startswith('cuda') and all(value.startswith('cuda') for value in end['forward_output_devices'])
        if mode == 'gs-traffic-face':
            assert len(data['face_events']) >= 3
            assert all(event['metrics']['device']=='CUDAExecutionProvider' and event['passed'] for event in data['face_events'])
        reports.append({'mode':mode,'fps':data['web_fps'],'frames':len(frames)})
    manifest = json.loads((ROOT/'assets-manifest.json').read_text('utf-8'))
    for row in manifest:
        assert hashlib.sha256((ROOT/row['path']).read_bytes()).hexdigest()==row['sha256'],row['path']
    result = {'native_cases':12,'web':reports,'all_new_distinct_frames':True,'full_scene_and_original_camera':True,'passed':True}
    (ROOT/'docs/setup/report-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
