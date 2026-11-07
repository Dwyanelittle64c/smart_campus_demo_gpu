"""隔离临时新库验证幂等、损坏保护与删除语义；不调用测试人员的旧数据库。"""
import tempfile
import unittest
import uuid
from pathlib import Path
import numpy as np
from shared.config import ROOT
import backend.face.service as faces


class StorageTests(unittest.TestCase):
    def setUp(self):
        folder = ROOT / 'data/runtime/tests'
        folder.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=folder)
        self.root = Path(self.temp.name).resolve()
        assert self.root.is_relative_to(folder.resolve())
        self.original_root = faces.DATA
        faces.DATA = self.root
        self.service = faces.FaceService()
        image = np.full((40, 40, 3), 100, np.uint8)
        feature = np.ones(128, np.float32) / np.sqrt(128)
        self.service.extract = lambda raw: (image, image, feature, {'feature_version': 'fixture-v1', 'device': 'test-stub'})

    def tearDown(self):
        faces.DATA = self.original_root
        self.temp.cleanup()

    def test_persistent_idempotency_and_independent_snapshots(self):
        enroll_id, recognize_id = uuid.uuid4().hex, uuid.uuid4().hex
        person = self.service.enroll('同名 / 不能成为路径', b'fixture', enroll_id)
        self.assertEqual((self.root / 'faces' / person['id'] / 'original.jpg').read_bytes(), b'fixture')
        self.assertEqual(self.service.enroll('同名 / 不能成为路径', b'fixture', enroll_id)['id'], person['id'])
        event = self.service.recognize(b'fixture', recognize_id)
        self.assertEqual(self.service.recognize(b'fixture', recognize_id)['id'], event['id'])
        self.assertEqual(len(self.service.history()), 1)
        snapshot = self.root / 'recognitions/images' / f'{event["id"]}-candidate.jpg'
        self.service.delete(person['id'])
        self.assertTrue(snapshot.is_file())
        with self.assertRaisesRegex(ValueError, '人员库为空'):
            self.service.recognize(b'fixture', uuid.uuid4().hex)
        self.assertEqual(len(self.service.history()), 1)
        sentinel = self.root / 'scenes/scene.ply'
        sentinel.parent.mkdir()
        sentinel.write_text('keep')
        self.service.clear()
        self.assertFalse(snapshot.exists())
        self.assertEqual(sentinel.read_text(), 'keep')
        self.assertEqual(self.service.history(), [])

    def test_corrupt_index_is_never_reset_to_empty(self):
        index = self.root / 'faces/people.json'
        index.parent.mkdir()
        index.write_text('broken-json', 'utf-8')
        with self.assertRaises(ValueError):
            self.service.people()
        self.assertEqual(index.read_text(), 'broken-json')

    def test_missing_index_with_existing_features_is_not_empty_library(self):
        person = self.service.enroll('公开夹具', b'fixture', uuid.uuid4().hex)
        index = self.root / 'faces/people.json'
        index.unlink()
        with self.assertRaises(ValueError):
            self.service.people()
        self.assertTrue((self.root / 'faces' / person['id'] / 'feature.npy').exists())

    def test_missing_history_snapshot_is_reported_without_reset(self):
        self.service.enroll('公开夹具', b'fixture', uuid.uuid4().hex)
        event = self.service.recognize(b'fixture', uuid.uuid4().hex)
        index = self.root / 'recognitions/events.jsonl'
        original = index.read_bytes()
        (self.root / 'recognitions/images' / f'{event["id"]}-face.jpg').unlink()
        with self.assertRaisesRegex(ValueError, '快照缺失'):
            self.service.history()
        self.assertEqual(index.read_bytes(), original)
