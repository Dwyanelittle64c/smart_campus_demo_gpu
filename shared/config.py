"""两种角色共用轻量配置；只读 JSON，不导入算法或启动后台任务。"""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = Path(os.environ.get('CAMPUS_CONFIG', ROOT / 'config/local-3050.json'))
CONFIG = json.loads(CONFIG_PATH.read_text('utf-8'))
DATA = Path(CONFIG.get('data_root', 'data'))
if not DATA.is_absolute():
    DATA = ROOT / DATA
DATA = DATA.resolve()
MODULES = {name: bool(CONFIG.get('modules', {}).get(name, False)) for name in ('scene', 'traffic', 'face')}


def inside(root, relative):
    """只允许根目录内文件；绝对路径、.. 和符号链接越界均拒绝。"""
    root = Path(root).resolve()
    result = (root / relative).resolve()
    if not result.is_relative_to(root):
        raise ValueError('文件路径超出允许目录')
    return result


def backend_headers():
    """实例令牌只取服务端环境变量，不进入页面、URL 或日志。"""
    token = os.environ.get('CAMPUS_INSTANCE_TOKEN', '')
    return {'Authorization': f'Bearer {token}'} if token else {}
