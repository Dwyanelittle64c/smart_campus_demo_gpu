"""为独立小显存训练副本导出有限初始SfM点；不是高斯场景，也不修改原COLMAP结果。"""
import argparse
from pathlib import Path
import numpy as np
from plyfile import PlyData, PlyElement


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--points-txt', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--maximum', type=int, default=5000)
    args = parser.parse_args()
    if args.output.exists() or args.maximum < 1:
        raise ValueError('输出已存在或上限无效，不覆盖原数据')
    points = []
    for line in args.points_txt.read_text('utf-8').splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        columns = line.split()
        if len(columns) < 8:
            raise ValueError('不是COLMAP points3D.txt格式')
        xyz = list(map(float, columns[1:4]))
        rgb = list(map(int, columns[4:7]))
        if not np.isfinite(xyz).all() or not all(0 <= value <= 255 for value in rgb):
            raise ValueError('点坐标/颜色无效')
        points.append(xyz + rgb)
    if not points:
        raise ValueError('稀疏点为空')
    points = np.asarray(points)[np.linspace(0, len(points)-1, min(args.maximum, len(points)), dtype=int)]
    vertex = np.zeros(len(points), dtype=[(name, 'f4') for name in ('x', 'y', 'z', 'nx', 'ny', 'nz')] +
                                        [(name, 'u1') for name in ('red', 'green', 'blue')])
    for index, key in enumerate(('x', 'y', 'z', 'red', 'green', 'blue')):
        vertex[key] = points[:, index]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    PlyData([PlyElement.describe(vertex, 'vertex')]).write(args.output)
    print(f'独立副本初始化点：{len(points)}；原始points3D.txt未修改')


if __name__ == '__main__':
    main()
