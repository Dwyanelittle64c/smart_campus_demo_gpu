"""从许可vtest生成16:9真实视频派生，仅验证上传/黑边ROI，不用于FPS成绩。"""
import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shared.config import ROOT, DATA


def main():
    import cv2
    source = DATA / 'videos/vtest.avi'
    target = DATA / 'runtime/test-wide.avi'
    target.parent.mkdir(parents=True, exist_ok=True)
    capture = cv2.VideoCapture(str(source))
    output = cv2.VideoWriter(str(target), cv2.VideoWriter_fourcc(*'MJPG'), 10, (640, 360))
    if not output.isOpened():
        raise RuntimeError('测试视频编码器不可用')
    count = 0
    try:
        while True:
            valid, frame = capture.read()
            if not valid:
                break
            height, width = frame.shape[:2]
            crop_height = int(width * 9 / 16)
            top = (height - crop_height) // 2
            wide = cv2.resize(frame[top:top+crop_height], (640, 360))
            output.write(wide)
            count += 1
    finally:
        output.release()
        capture.release()
    record = {'source': 'OpenCV4.12.0 vtest/CAVIAR公开研究样例', 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'derived_sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'frames': count, 'fps': 10,
              'resolution': [640, 360], 'operation': '固定中央16:9裁切并缩放；不同真实输入帧，无循环/重复/合成替代',
              'purpose': '仅本机上传/暂停/显示黑边ROI契约，不计入GS或交通性能成绩'}
    (ROOT / 'docs/setup/wide-video-fixture.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), 'utf-8')
    print('生成真实公开视频派生：', count, '帧，', target.stat().st_size, 'bytes')


if __name__ == '__main__':
    main()
