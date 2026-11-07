"""无模型依赖的统计契约：底边中心在 ROI，track ID 首次进入只计一次。"""
import math
from collections import Counter

GROUPS = ('person', 'vehicle', 'bicycle')


def validate_roi(roi):
    """归一化矩形，排除退化/非有限坐标；不依赖 CSS 显示尺寸。"""
    if not isinstance(roi, (list, tuple)) or len(roi) != 4:
        raise ValueError('ROI 需要四个归一化坐标')
    values = list(map(float, roi))
    if not all(math.isfinite(v) and 0 <= v <= 1 for v in values) or values[2] - values[0] < .01 or values[3] - values[1] < .01:
        raise ValueError('ROI 坐标应为 0～1，宽高至少为 1%')
    return values


class CounterState:
    """累计全会话去重，分钟桶只存 ID 首次进入事件；类别抖动不会重复累计。"""
    def __init__(self, roi=(0, 0, 1, 1)):
        self.roi = validate_roi(roi)
        self.seen = {}
        self.buckets = {}
        self.current = Counter()
        self.elapsed = 0

    def update(self, detections, seconds):
        """输入 (ID或None, COCO类, 底中心x,y)，输出当前帧同源统计。"""
        if not math.isfinite(seconds) or seconds < self.elapsed:
            raise ValueError('源时间必须有限且单调')
        self.elapsed = seconds
        self.current.clear()
        minute = int(seconds // 60)
        for identifier, cls, x, y in detections:
            group = {0: 'person', 1: 'bicycle', 2: 'vehicle', 3: 'vehicle', 5: 'vehicle', 7: 'vehicle'}.get(int(cls))
            if group is None or not self.roi[0] <= x <= self.roi[2] or not self.roi[1] <= y <= self.roi[3]:
                continue
            self.current[group] += 1
            if identifier is not None and identifier not in self.seen:
                self.seen[identifier] = group
                self.buckets.setdefault(minute, Counter())[group] += 1
        return self.snapshot()

    def snapshot(self):
        """缺组显式补零；所有历史桶之和等于累计，直播不按分钟重置 seen。"""
        cumulative = Counter(self.seen.values())
        fill = lambda values: {g: values.get(g, 0) for g in GROUPS}
        return {'current': fill(self.current), 'cumulative': fill(cumulative),
                'minute_new': fill(self.buckets.get(int(self.elapsed // 60), {})),
                'buckets': [{'minute': minute, **fill(value)} for minute, value in sorted(self.buckets.items())],
                'elapsed': self.elapsed, 'roi': self.roi}


class MediaClock:
    """视频 PTS 不可信时按解码序号/FPS 单调回退，慢推理不改变统计时间。"""
    def __init__(self, fps):
        self.fps = fps if math.isfinite(fps) and 1 <= fps <= 240 else 25
        self.index = 0
        self.previous = -1
        self.fallback = False

    def next(self, milliseconds):
        expected = self.index / self.fps
        value = milliseconds / 1000
        if not math.isfinite(value) or value < 0 or (self.index and (value <= self.previous or abs(value - expected) > max(2, expected * .1))):
            self.fallback = True
        value = max(expected, self.previous + 1 / self.fps) if self.fallback else value
        self.previous = value
        self.index += 1
        return value
