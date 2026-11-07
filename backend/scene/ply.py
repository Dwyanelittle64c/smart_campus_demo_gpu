"""标准 INRIA PLY 读取与参数适配；无投影、排序或合成算法。"""
import hashlib
import math
from pathlib import Path
import numpy as np
from plyfile import PlyData


def read_ply(path, maximum=None):
    """全量为默认；高阶 SH 按 INRIA 通道优先存储顺序转换为 N×K×3。"""
    path = Path(path)
    vertex = PlyData.read(path)['vertex'].data
    names = set(vertex.dtype.names)
    required = ['x', 'y', 'z', 'opacity', *[f'scale_{i}' for i in range(3)],
                *[f'rot_{i}' for i in range(4)], *[f'f_dc_{i}' for i in range(3)]]
    if not set(required) <= names or not len(vertex):
        raise ValueError('只接受标准 3DGS PLY；普通 XYZ/RGB 点云或空场景不支持')
    original = len(vertex)
    if maximum is not None:
        if int(maximum) < 1:
            raise ValueError('公开性能档数量必须为正整数')
        vertex = vertex[np.linspace(0, original - 1, min(original, int(maximum)), dtype=int)]
    def columns(keys):
        result = np.stack([vertex[n] for n in keys], axis=-1).astype(np.float32)
        if not np.isfinite(result).all():
            raise ValueError('PLY 含非有限数值')
        return result
    means = columns(['x', 'y', 'z'])
    raw_scale = columns([f'scale_{i}' for i in range(3)])
    raw_opacity = columns(['opacity'])[:, 0]
    quats = columns([f'rot_{i}' for i in range(4)])
    norm = np.linalg.norm(quats, axis=1, keepdims=True)
    if (norm < 1e-8).any() or (raw_scale > 30).any() or (raw_scale < -80).any():
        raise ValueError('PLY 含零四元数或不可表示的尺度')
    quats /= norm  # 原始 wxyz，gsplat 同样要求 wxyz。
    scales = np.exp(raw_scale)
    opacities = np.exp(-np.logaddexp(0, -raw_opacity))  # 稳定 sigmoid，恰好激活一次。
    rest = sorted((n for n in names if n.startswith('f_rest_')), key=lambda n: int(n[7:]))
    if rest != [f'f_rest_{i}' for i in range(len(rest))] or len(rest) % 3:
        raise ValueError('SH 属性编号/数量不连续')
    count = len(rest) // 3 + 1
    degree = math.isqrt(count) - 1
    if (degree + 1) ** 2 != count or not 0 <= degree <= 4:
        raise ValueError('SH 系数数量不是支持的完整阶数 0～4')
    dc = columns([f'f_dc_{i}' for i in range(3)])[:, None, :]
    sh = np.concatenate((dc, columns(rest).reshape(len(vertex), 3, -1).transpose(0, 2, 1)), axis=1) if rest else dc
    center = np.median(means, axis=0)
    radius = max(float(np.quantile(np.linalg.norm(means - center, axis=1), .95)), .01)
    info = {'original': original, 'actual': len(vertex), 'input': len(vertex), 'available_sh_degree': degree,
            'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'center': center.tolist(), 'radius': radius}
    return {'means': means, 'quats': quats, 'scales': scales, 'opacities': opacities, 'colors': sh}, info
