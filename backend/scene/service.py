"""GS 场景缓存位于 GPU 服务；只有显式相机控制才加载。"""
from shared.config import CONFIG, DATA, inside


class SceneService:
    """唯一调度线程调用，不跨线程同时操作张量。"""
    def __init__(self):
        self.renderer = None

    def render(self, command):
        """首次显式请求加载全量场景，后续仅更新相机。"""
        from backend.scene.renderer import Renderer
        config = CONFIG['scene']
        if self.renderer is None:
            self.renderer = Renderer(inside(DATA, config['package']), CONFIG['device'],
                                     config.get('max_gaussians'), config.get('sh_mode', 'auto'))
        width = int(command.get('width', config['width']))
        height = int(command.get('height', config['height']))
        payload, meta, _ = self.renderer.render(command.get('state', {}), width, height, config['jpeg_quality'])
        return payload, meta

    def close(self):
        if self.renderer:
            self.renderer.close()
            self.renderer = None


service = SceneService()
