"""常驻显存的 gsplat CUDA 前向封装；无 CPU 渲染或自动下载回退。"""
import importlib.util
import importlib
import json
import time
from pathlib import Path
import numpy as np
from backend.scene.camera import orbit
from backend.scene.ply import read_ply


class Renderer:
    """在 GPU 调度线程内加载/渲染/释放；场景张量跨帧复用。"""
    def __init__(self, package, device='cuda:0', maximum=None, sh_mode='auto'):
        import torch
        torch.set_num_threads(2)
        if not device.startswith('cuda') or not torch.cuda.is_available():
            raise RuntimeError('CUDA GPU 不可用；本项目没有 CPU 算法回退')
        if importlib.util.find_spec('gsplat.csrc') is None:
            raise RuntimeError('gsplat CUDA 扩展未准备，请先执行 scripts/build_gsplat.ps1 或 Linux 准备命令')
        try:
            importlib.import_module('gsplat.csrc')
        except Exception as exc:
            raise RuntimeError('gsplat 扩展存在但无法加载，请显式重新准备；禁止请求阶段自动JIT') from exc
        from gsplat import rasterization
        self.rasterization = rasterization
        self.device = torch.device(device)
        began = time.perf_counter()
        arrays, self.info = read_ply(Path(package) / 'scene.ply', maximum)
        self.info['ply_load_ms'] = (time.perf_counter() - began) * 1000
        self.preset = json.loads((Path(package) / 'camera.json').read_text('utf-8'))
        upload = time.perf_counter()
        self.tensors = {k: torch.from_numpy(np.ascontiguousarray(v)).to(self.device) for k, v in arrays.items()}
        torch.cuda.synchronize(self.device)
        self.info.update(upload_ms=(time.perf_counter() - upload) * 1000, device=str(self.device),
                         gpu_name=torch.cuda.get_device_name(self.device))
        self.degree = self.info['available_sh_degree'] if sh_mode == 'auto' else 0
        self.info['sh_degree'] = self.degree

    def render(self, state, width=640, height=480, quality=88, encode=True):
        """CUDA events 覆盖完整上游前向；同步后分别计转换、拷贝及 CPU JPEG。"""
        import cv2
        import torch
        cv2.setNumThreads(2)
        started = time.perf_counter()
        view, intrinsic, near, far, controls = orbit(self.preset, state, width, height, self.info['center'], self.info['radius'], with_controls=True)
        view = torch.from_numpy(view[None]).to(self.device)
        intrinsic = torch.from_numpy(intrinsic[None]).to(self.device)
        begin, end, converted = (torch.cuda.Event(enable_timing=True) for _ in range(3))
        with torch.inference_mode(), torch.cuda.device(self.device):
            begin.record()
            colors, alpha, meta = self.rasterization(**self.tensors, viewmats=view, Ks=intrinsic, width=width, height=height,
                sh_degree=self.degree, near_plane=near, far_plane=far, packed=False, radius_clip=0., eps2d=.3,
                rasterize_mode='classic', render_mode='RGB')
            end.record()
            rgb_gpu = (colors[0].clamp(0, 1) * 255).round().to(torch.uint8)
            converted.record()
            converted.synchronize()
            gpu_ms, convert_gpu_ms = begin.elapsed_time(end), end.elapsed_time(converted)
            copy_start = time.perf_counter()
            rgb = rgb_gpu.cpu().numpy()
            copy_ms = (time.perf_counter() - copy_start) * 1000
            visible = int((meta['radii'] > 0).all(dim=-1).sum().item())
        convert_start = time.perf_counter()
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        convert_ms = (time.perf_counter() - convert_start) * 1000
        encoding = time.perf_counter()
        payload = None
        if encode:
            valid, jpeg = cv2.imencode('.jpg', bgr, [cv2.IMWRITE_JPEG_QUALITY, int(quality)])
            if not valid:
                raise RuntimeError('JPEG 编码失败')
            payload = jpeg.tobytes()
        metrics = {**self.info, 'camera_control': controls, 'visible': visible, 'resolution': [width, height], 'core_ms': gpu_ms,
                   'gpu_convert_ms': convert_gpu_ms, 'copy_ms': copy_ms, 'pixel_convert_ms': convert_ms,
                   'encode_ms': (time.perf_counter() - encoding) * 1000,
                   'server_ms': (time.perf_counter() - started) * 1000,
                   'allocated_mb': torch.cuda.memory_allocated(self.device) / 2**20,
                   'reserved_mb': torch.cuda.memory_reserved(self.device) / 2**20,
                   'quality': {'eps2d': .3, 'radius_clip': 0., 'mode': 'classic', 'packed': False, 'jpeg': quality}}
        return payload, metrics, rgb

    def close(self):
        """只在明确切换/关闭时释放，不逐帧 empty_cache。"""
        import torch
        self.tensors.clear()
        torch.cuda.synchronize(self.device)
        torch.cuda.empty_cache()
