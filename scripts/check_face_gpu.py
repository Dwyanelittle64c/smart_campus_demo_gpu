"""真实公开照片 + ORT 节点 profile + OpenCV CPU 参考；CPU 仅用于测试对照。"""
import json
import sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from shared.config import ROOT, DATA, CONFIG
from backend.face.models import FaceModels


def main():
    import cv2
    model = FaceModels(profiling=True)
    results, features = [], []
    reference = cv2.FaceRecognizerSF.create(str(ROOT / CONFIG['face']['recognizer']), '')
    detector_reference = cv2.FaceDetectorYN.create(str(ROOT / CONFIG['face']['detector']), '', (640,640), .8, .3, 5000)
    first_image = None
    for name in ('obama-2009.jpg', 'obama-2012.jpg', 'biden-2021.jpg'):
        image, aligned, feature, metrics = model.extract((DATA / 'test_faces' / name).read_bytes())
        if first_image is None:
            first_image = image
        padded = np.zeros((640,640,3),np.uint8)
        padded[:image.shape[0],:image.shape[1]] = image
        _, cpu_faces = detector_reference.detect(padded)
        assert cpu_faces is not None and len(cpu_faces)==1
        detector_error = float(np.max(np.abs(cpu_faces[0]-np.asarray(metrics['landmarks']))))
        assert detector_error < 1
        cpu = reference.feature(aligned).reshape(-1)
        cpu /= np.linalg.norm(cpu)
        agreement = float(cpu @ feature)
        assert agreement > .995, agreement
        features.append(feature)
        results.append({'photo': name, 'cpu_reference_cosine': agreement, 'yunet_cpu_max_error':detector_error, 'metrics': metrics})
        print(name, 'CPU reference cosine', agreement, flush=True)
    same, other = float(features[0] @ features[1]), float(features[0] @ features[2])
    assert same >= CONFIG['face']['threshold'] and other < CONFIG['face']['threshold'], (same, other)
    small = cv2.resize(first_image,(250,300))
    multiple = np.zeros((640,640,3),np.uint8)
    multiple[20:320,20:270] = small
    multiple[20:320,350:600] = small
    errors = []
    for label, raw in [('bad-file',b'bad-image'),('no-face',cv2.imencode('.png',np.zeros((640,640,3),np.uint8))[1].tobytes()),
                       ('multiple-faces',cv2.imencode('.png',multiple)[1].tobytes())]:
        try:
            model.extract(raw)
        except ValueError as exc:
            errors.append({'case':label,'error':str(exc)})
        else:
            raise AssertionError(label+'没有拒绝')
    profiles = []
    for filename in model.finish_profile():
        nodes = json.loads(Path(filename).read_text('utf-8'))
        network = [event for event in nodes if event.get('args', {}).get('op_name') in ('Conv', 'FusedConv', 'Gemm', 'MatMul')
                   and event.get('args', {}).get('provider')]
        assert network and all(event['args']['provider'] == 'CUDAExecutionProvider' for event in network)
        providers = Counter(event['args']['provider'] for event in network)
        profiles.append({'path': str(Path(filename).relative_to(ROOT)), 'major_network_node_providers': dict(providers),
                         'all_node_providers': dict(Counter(event.get('args', {}).get('provider') for event in nodes if event.get('args', {}).get('provider')))})
    report = {'photos': results, 'same_person_different_photo_score': same, 'unregistered_person_score': other,
              'threshold': CONFIG['face']['threshold'], 'profiles': profiles, 'negative_inputs':errors, 'passed': True}
    (ROOT / 'docs/setup/face-gpu-check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
    print(json.dumps({'same': same, 'other': other, 'profiles': profiles}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
