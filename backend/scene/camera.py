"""CV +X右/+Y下/+Z前相机；保留原始世界坐标，不使用旧 Rust signed-fy 转换。"""
import math
import numpy as np


def unit(vector):
    """归一化向量，拒绝零长度及非法相机。"""
    vector = np.asarray(vector, dtype=np.float64)
    length = np.linalg.norm(vector)
    if vector.shape != (3,) or not np.isfinite(vector).all() or length < 1e-8:
        raise ValueError('相机向量无效')
    return vector / length


def rotate(vector, axis, angle):
    """轨道控制的 Rodrigues 刚体旋转；不参与高斯投影或合成。"""
    axis = unit(axis)
    return vector * math.cos(angle) + np.cross(axis, vector) * math.sin(angle) + axis * np.dot(axis, vector) * (1 - math.cos(angle))


def orbit(preset, state, width, height, center, radius, with_controls=False):
    """轨道状态→完整 view/K；支持初始 world_to_camera、非中心主点和 fx≠fy。"""
    yaw, pitch, zoom = (float(state.get(k, v)) for k, v in (('yaw', 0), ('pitch', 0), ('zoom', 1)))
    if not all(math.isfinite(v) for v in (yaw, pitch, zoom)):
        raise ValueError('相机参数必须为有限数值')
    if not 32 <= width <= 1920 or not 32 <= height <= 1080:
        raise ValueError('真实输出尺寸超出允许范围')
    target = np.asarray(preset.get('center', center), dtype=np.float64)
    if 'world_to_camera' in preset:
        base = np.asarray(preset['world_to_camera'], dtype=np.float64).reshape(4, 4)
        position = -base[:3, :3].T @ base[:3, 3]
        up = -base[1, :3]
        if 'center' not in preset:
            target = position + base[2, :3] * radius * 2.8
    else:
        position = np.asarray(preset.get('position', target + [0, 0, -radius * 2.8]), dtype=np.float64)
        up = np.asarray(preset.get('up', [0, -1, 0]), dtype=np.float64)
    up = unit(up)
    offset = rotate(position - target, up, yaw)
    right = unit(np.cross(-offset, up))
    offset = rotate(offset, right, max(-1.3, min(1.3, pitch)))
    position = target + offset * max(.2, min(8., zoom))
    forward = unit(target - position)
    right = unit(np.cross(forward, up))
    rotation = np.stack((right, np.cross(forward, right), forward))
    # 平移以世界向量保存，旋转/缩放时不改变轨道中心；零向量兼容原相机。
    pan = np.asarray(state.get('pan', [0, 0, 0]), dtype=np.float64)
    if pan.shape != (3,) or not np.isfinite(pan).all() or np.max(np.abs(pan)) > max(radius * 10000, 1):
        raise ValueError('平移向量无效或超出场景范围')
    position = position + pan
    view = np.eye(4, dtype=np.float32)
    view[:3, :3], view[:3, 3] = rotation, -rotation @ position
    rw, rh = float(preset.get('width', width)), float(preset.get('height', height))
    focal = width / (2 * math.tan(math.radians(55) / 2))
    intrinsic = np.array([[float(preset.get('fx', focal * rw / width)) * width / rw, 0, float(preset.get('cx', rw / 2)) * width / rw],
                          [0, float(preset.get('fy', focal * rh / height)) * height / rh, float(preset.get('cy', rh / 2)) * height / rh],
                          [0, 0, 1]], dtype=np.float32)
    if not np.isfinite(view).all() or not np.isfinite(intrinsic).all() or intrinsic[0, 0] <= 0 or intrinsic[1, 1] <= 0:
        raise ValueError('外参或内参无效')
    result = (view, intrinsic, float(preset.get('near', max(radius * 1e-4, 1e-4))), float(preset.get('far', radius * 100)))
    if with_controls:
        distance = np.linalg.norm(offset) * max(.2, min(8., zoom))
        controls = {'right': rotation[0].tolist(), 'down': rotation[1].tolist(),
                    'world_per_image_x': float(distance * width / intrinsic[0, 0]),
                    'world_per_image_y': float(distance * height / intrinsic[1, 1])}
        return (*result, controls)
    return result
