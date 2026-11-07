"""阻止Python公网socket连接后，实际执行三模块；只使用新工程公开素材。"""
import json
import asyncio
import socket
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shared.config import ROOT, DATA, CONFIG


def main():
    """此拦截仅在独立验收进程内生效，不改系统代理、防火墙或服务网络。"""
    attempts = []
    # Windows asyncio通过本机socketpair唤醒事件循环，先建立它再拦截算法网络。
    loop = asyncio.new_event_loop()
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    def blocked(self, address):
        attempts.append(str(address))
        raise OSError('离线验收：Python socket已禁止连接')
    socket.socket.connect = socket.socket.connect_ex = blocked
    try:
        import cv2
        from backend.scene.renderer import Renderer
        from backend.traffic.service import TrafficService
        from backend.face.models import FaceModels
        renderer = Renderer(DATA / CONFIG['scene']['package'], CONFIG['device'])
        payload, scene, _ = renderer.render({'zoom': 1})
        renderer.close()
        capture = cv2.VideoCapture(str(DATA / 'videos/vtest.avi'))
        valid, frame = capture.read()
        capture.release()
        assert valid
        traffic_service = TrafficService()
        traffic_payload, _, traffic = traffic_service._infer(frame, 0)
        # 公共视频帧作关闭缓冲夹具；不访问真实摄像头、不保存帧。
        traffic_service.source = {'type': 'camera'}
        traffic_service.latest = ({}, traffic_payload)
        loop.run_until_complete(traffic_service.stop())
        predictor = traffic_service.model.predictor
        assert traffic_service.latest is None
        assert predictor.dataset is None and predictor.plotted_img is None
        assert predictor.batch is None and not predictor.results
        traffic_service._infer(frame, .1)  # 保留权重后能重新初始化输入，不影响下一轮。
        traffic_service.unload()
        models = FaceModels()
        _, _, feature, face = models.extract((DATA / 'test_faces/obama-2012.jpg').read_bytes())
        assert scene['device'] == traffic['device'] == 'cuda:0'
        assert face['device'] == 'CUDAExecutionProvider' and len(feature) == 128
        assert scene['actual'] == 113648 and payload
        assert not attempts, attempts
        report = {'python_socket_connect_attempts': attempts, 'scene_device': scene['device'],
                  'scene_actual': scene['actual'], 'traffic_forward_input': traffic['forward_input_device'],
                  'traffic_forward_outputs': traffic['forward_output_devices'], 'face_device': face['device'],
                  'camera_buffer_cleanup_public_video_fixture': True,
                  'scope': 'Python socket connect/connect_ex拦截；不是操作系统全网抓包', 'passed': True}
    finally:
        socket.socket.connect = original_connect
        socket.socket.connect_ex = original_connect_ex
        loop.close()
    (ROOT / 'docs/setup/offline-algorithms.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
    print('离线socket拦截下实际三模块CUDA推理通过；没有尝试Python网络连接')


if __name__ == '__main__':
    main()
