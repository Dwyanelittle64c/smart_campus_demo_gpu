"""一条 WS 消息封装元数据与 JPEG，避免多任务元图错配。"""
import json
import struct

MAGIC = b'SCG1'
VERSION = 1
MAX_IMAGE = 8 * 1024 * 1024


def pack_frame(meta, payload):
    """输入小型字典和图片字节，输出有长度边界的单个二进制帧。"""
    meta = {**meta, 'protocol_version': VERSION, 'payload_length': len(payload), 'image_type': 'image/jpeg'}
    encoded = json.dumps(meta, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')
    if len(encoded) > 128 * 1024 or len(payload) > MAX_IMAGE:
        raise ValueError('帧超出协议大小限制')
    return MAGIC + struct.pack('<II', len(encoded), len(payload)) + encoded + payload


def unpack_frame(raw):
    """校验边界；用于浏览器摄像头上行及脱离网页的集成测试。"""
    if len(raw) < 12 or raw[:4] != MAGIC:
        raise ValueError('无效帧协议')
    metadata, length = struct.unpack('<II', raw[4:12])
    if metadata > 128 * 1024 or length > MAX_IMAGE or len(raw) != 12 + metadata + length:
        raise ValueError('帧长度无效')
    return json.loads(raw[12:12 + metadata]), raw[12 + metadata:]
