"""轻量环境可运行的关键业务/协议测试；不导入 numpy、torch 或算法模型。"""
import struct
import unittest
from backend.traffic.counting import CounterState, MediaClock, validate_roi
from shared.protocol import pack_frame, unpack_frame


class CountingTests(unittest.TestCase):
    def test_roi_reentry_minutes_class_jitter_and_missing_id(self):
        counter = CounterState((.2, .2, .8, .8))
        self.assertEqual(counter.update([(1, 0, .1, .5)], 0)['cumulative']['person'], 0)
        result = counter.update([(1, 0, .5, .5), (None, 2, .6, .6)], 1)
        self.assertEqual(result['current'], {'person': 1, 'vehicle': 1, 'bicycle': 0})
        self.assertEqual(result['cumulative']['vehicle'], 0)
        counter.update([], 30)
        counter.update([(1, 0, .5, .5)], 35)
        result = counter.update([(1, 2, .5, .5), (2, 2, .5, .5), (3, 1, .5, .5)], 65)
        self.assertEqual(result['cumulative'], {'person': 1, 'vehicle': 1, 'bicycle': 1})
        self.assertEqual(result['minute_new']['person'], 0)
        for group, count in result['cumulative'].items():
            self.assertEqual(sum(bucket[group] for bucket in result['buckets']), count)

    def test_media_clock_fallback_monotonic(self):
        clock = MediaClock(10)
        times = [clock.next(value) for value in (0, 100, 200, 0, 0, float('nan'), 600)]
        self.assertTrue(clock.fallback)
        self.assertEqual([round(value, 1) for value in times], [0, .1, .2, .3, .4, .5, .6])

    def test_roi_and_time_reject_invalid_input(self):
        for roi in ([0, 0, 0, 1], [0, 0, 2, 1], [0, float('nan'), 1, 1]):
            with self.assertRaises(ValueError):
                validate_roi(roi)
        counter = CounterState()
        counter.update([], 2)
        with self.assertRaises(ValueError):
            counter.update([], 1)


class ProtocolTests(unittest.TestCase):
    def test_same_frame_metadata_boundary_and_binary(self):
        meta = {'epoch': 'new', 'frame_id': 12, 'source_id': 'camera'}
        raw = b'\xff\xd8\x00\x01\xff\xd9'
        decoded, pixels = unpack_frame(pack_frame(meta, raw))
        self.assertEqual(pixels, raw)
        self.assertEqual(decoded['frame_id'], 12)
        self.assertEqual(decoded['payload_length'], len(raw))

    def test_truncated_or_malicious_length_rejected(self):
        for data in (b'', b'xxxx' * 4, b'SCG1' + struct.pack('<II', 8, 99999999) + b'{}'):
            with self.assertRaises(ValueError):
                unpack_frame(data)


if __name__ == '__main__':
    unittest.main()
