"""全新文件人员库和幂等识别事件；历史快照不依赖仍存在的登记人员。"""
import json
import hashlib
import os
import re
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from shared.config import DATA, CONFIG
from backend.core.storage import LOCK, atomic_json, read_index, image_bytes


def valid_id(value):
    """生成 ID 才能作为文件路径，姓名永不进入路径。"""
    if not re.fullmatch('[0-9a-f]{32}', str(value)):
        raise ValueError('业务 ID 无效')
    return value


def now():
    return datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')


class FaceService:
    """算法仅在 GPU 调度器执行；管理/历史加文件锁并支持持久幂等。"""
    def __init__(self):
        self.models = None
        self.cache = {}

    def people(self):
        """新实例空库可读，旧索引损坏显式报错。"""
        with LOCK:
            index = DATA / 'faces/people.json'
            if not index.exists() and any((DATA / 'faces').glob('*/feature.npy')):
                raise ValueError('人员索引缺失但登记特征仍存在，请恢复 people.json；不会重建空库')
            people = read_index(index, [])
            if not isinstance(people, list):
                raise ValueError('人员索引格式错误')
            for person in people:
                valid_id(person.get('id'))
                original = person.get('original_file', 'original.jpg')
                if original not in ('original.jpg', 'original.png') or not all((DATA / 'faces' / person['id'] / filename).is_file() for filename in (original, 'face.jpg', 'feature.npy')):
                    raise ValueError('人员登记文件缺失，请恢复数据或明确删除该登记')
            return people

    def history(self):
        """每次有效比对一条，最新在前；非法行不吞掉。"""
        with LOCK:
            path = DATA / 'recognitions/events.jsonl'
            if not path.exists():
                if any((DATA / 'recognitions/images').glob('*.jpg')):
                    raise ValueError('历史索引缺失但快照仍存在，请恢复 events.jsonl')
                return []
            try:
                events = [json.loads(line) for line in path.read_text('utf-8').splitlines() if line.strip()]
                for event in events:
                    valid_id(event['id'])
                    if not all((DATA / 'recognitions/images' / f'{event["id"]}-{kind}.jpg').is_file()
                               for kind in ('scene', 'face', 'candidate')):
                        raise ValueError('历史快照缺失')
            except (KeyError, ValueError) as exc:
                raise ValueError('识别历史损坏或快照缺失，请保留并修复 events.jsonl 和 images') from exc
            return events[::-1]

    def extract(self, raw):
        """首次明确提交才创建 ORT session；不为整个人员库重提特征。"""
        if self.models is None:
            from backend.face.models import FaceModels
            self.models = FaceModels()
        return self.models.extract(raw)

    def enroll(self, name, raw, request_id):
        """单人照片录入 UUID；同名独立，相同请求号重试不重复登记。"""
        import numpy as np
        name = str(name).strip()
        if not name or len(name) > 60:
            raise ValueError('姓名长度应为 1～60 字')
        valid_id(request_id)
        with LOCK:
            previous = next((p for p in self.people() if p.get('request_id') == request_id), None)
            if previous:
                return previous
        image, aligned, feature, metrics = self.extract(raw)
        identifier = uuid.uuid4().hex
        folder = DATA / 'faces' / identifier
        with LOCK:
            people = self.people()
            folder.mkdir(parents=True)
            try:
                original_file = 'original.png' if metrics.get('original_format') == 'PNG' else 'original.jpg'
                (folder / original_file).write_bytes(raw)  # 原始上传逐字节保留，预览/对齐另存。
                (folder / 'face.jpg').write_bytes(image_bytes(aligned))
                np.save(folder / 'feature.npy', feature, allow_pickle=False)
                person = {'id': identifier, 'name': name, 'created_at': now(), 'request_id': request_id,
                          'feature_version': metrics['feature_version'], 'face_url': f'/media/faces/{identifier}/face.jpg',
                          'photo_url': f'/media/faces/{identifier}/{original_file}', 'metrics': metrics,
                          'original_file': original_file, 'original_sha256': hashlib.sha256(raw).hexdigest()}
                atomic_json(DATA / 'faces/people.json', people + [person])
                self.cache[identifier] = feature
            except Exception:
                for filename in ('original.jpg', 'original.png', 'face.jpg', 'feature.npy'):
                    (folder / filename).unlink(missing_ok=True)
                folder.rmdir()
                raise
        return person

    def recognize(self, raw, request_id):
        """有效比对才写事件；CPU余弦不是网络推理，不把分数称作概率。"""
        import numpy as np
        valid_id(request_id)
        with LOCK:
            history = self.history()
            previous = next((event for event in history if event.get('request_id') == request_id), None)
            if previous:
                return previous
            if not self.people():
                raise ValueError('人员库为空，请先录入')
        image, aligned, feature, metrics = self.extract(raw)
        with LOCK:
            candidates = []
            for person in self.people():
                if person.get('feature_version') != metrics['feature_version']:
                    raise ValueError('登记特征与当前模型/预处理版本不同，请重新录入')
                identifier = person['id']
                if identifier not in self.cache:
                    value = np.load(DATA / 'faces' / identifier / 'feature.npy', allow_pickle=False)
                    if value.shape != (128,) or not np.isfinite(value).all() or np.linalg.norm(value) < 1e-8:
                        raise ValueError('登记特征损坏，请重新录入')
                    self.cache[identifier] = value / np.linalg.norm(value)
                candidates.append((float(np.clip(feature @ self.cache[identifier], -1, 1)), person))
            if not candidates:
                raise ValueError('人员库为空')
            score, best = max(candidates, key=lambda pair: pair[0])
            passed = score >= float(CONFIG['face']['threshold'])
            event_id = uuid.uuid4().hex
            folder = DATA / 'recognitions/images'
            folder.mkdir(parents=True, exist_ok=True)
            snapshots = [folder / f'{event_id}-{kind}.jpg' for kind in ('scene', 'face', 'candidate')]
            try:
                snapshots[0].write_bytes(image_bytes(image))
                snapshots[1].write_bytes(image_bytes(aligned))
                snapshots[2].write_bytes((DATA / 'faces' / best['id'] / 'face.jpg').read_bytes())
                event = {'id': event_id, 'request_id': request_id, 'time': now(), 'passed': passed,
                         'name': best['name'] if passed else '未知人员', 'candidate_name': best['name'], 'score': score,
                         'threshold': CONFIG['face']['threshold'], 'metrics': metrics,
                         **{f'{kind}_url': f'/media/recognitions/images/{event_id}-{kind}.jpg' for kind in ('scene', 'face', 'candidate')}}
                with (DATA / 'recognitions/events.jsonl').open('a', encoding='utf-8') as stream:
                    stream.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + '\n')
                    stream.flush()
                    os.fsync(stream.fileno())
                return event
            except Exception:
                for path in snapshots:
                    path.unlink(missing_ok=True)
                raise

    def delete(self, identifier):
        """删除登记文件，不删除旧事件的独立快照。"""
        identifier = valid_id(identifier)
        with LOCK:
            people = self.people()
            if not any(person['id'] == identifier for person in people):
                raise ValueError('人员不存在')
            atomic_json(DATA / 'faces/people.json', [person for person in people if person['id'] != identifier])
            for filename in ('original.jpg', 'original.png', 'face.jpg', 'feature.npy'):
                (DATA / 'faces' / identifier / filename).unlink(missing_ok=True)
            self.cache.pop(identifier, None)
        return {'deleted': identifier}

    def clear(self):
        """历史清理只访问日志引用的生成快照，人员和其他素材保持独立。"""
        with LOCK:
            events = self.history()
            path = DATA / 'recognitions/events.jsonl'
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix('.tmp')
            temporary.write_text('', 'utf-8')
            temporary.replace(path)
            for event in events:
                for kind in ('scene', 'face', 'candidate'):
                    (DATA / 'recognitions/images' / f'{event["id"]}-{kind}.jpg').unlink(missing_ok=True)
        return {'cleared': len(events)}

    def close(self):
        self.models = None
        self.cache.clear()


service = FaceService()
