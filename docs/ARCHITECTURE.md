# 双角色架构与生命周期

业务代码是独立重建，旧 CPU 工程仅只读参考。Web 与 GPU 使用同一仓库、不同命名 Conda 环境、不同 ASGI 进程；本机与远程共用接口。浏览器没有模型、PLY、WebGL/WebGPU 或深度学习库。

```text
浏览器（HTML / 原生 JS / 二维图片 / getUserMedia）
   ↕ HTTP + 三条 WS，同源 localhost:8010
Web Django（CSRF、页面、固定目标 HTTP/WS 网关）
   ↕ 回环接口，或 SSH 本地端口转发
GPU Django（localhost:8011；无窗口，无数据库）
   ├─ 控制租约 / 文件业务 / 公平 GPU 调度器
   ├─ gsplat CUDA：常驻场景张量 → CPU JPEG
   ├─ YOLO CUDA → ByteTrack CPU → ROI/轨迹/计数
   └─ YuNet / SFace ORT CUDA → CPU 对齐/余弦 → 文件历史
```

## 接口

- `GET /health/`：各角色基础健康，不导入/启动 GPU 模型。Web 自身健康和后端是否在线分别显示。
- `GET /api/capabilities/`：实际后端模块开关、设备配置、准备证据和当前已加载模块。不在此触发 CUDA 自检。
- `WS /ws/control`：一个实例只接受一个活跃控制客户端，返回短期 `session_id`。每5秒 ping，22秒未收到控制消息就回收。第二控制连接明确拒绝，不抢占已有学生。
- `WS /ws/scene`：首条 JSON `{session_id}`，后续小 JSON `{op:"camera",request_id,client_time,state:{yaw,pitch,zoom}}`。`reset` 生成新 epoch。固定真实尺寸来自配置。
- `WS /ws/traffic`：首条同样校验控制租约，订阅只读已完成帧。浏览器摄像头可通过同连接上行二进制 JPEG，含 `source_id/sequence/capture_ms`。
- `POST /api/traffic/control/`：start/pause/stop/reset/roi；start 传服务器视频 asset_id、camera 或 RTSP。HTTP 返回当前会话 ID，旧源结果不会进入新面板。
- `POST /api/traffic/upload/`：100MB 内视频，生成 ID、校验实际解码。原上传文件名不成为存储路径。
- `GET /api/face/people/`、`history/`；`POST submit/` multipart、`delete/`、`clear/` JSON。识别 request_id 在同一进程合并，在事件文件中跨重启去重。
- `GET /media/...`：只允许 UUID 人员JPG/PNG原图、对齐JPEG和历史JPEG，不能下载任意文件、模型或特征。网关按块转发并关闭上游流。

所有业务 HTTP POST 在 Web 经过 Django CSRF；GPU 服务间 API 使用实例认证头（若配置）和控制租约。WS 两端检查 Origin，控制会话通过首条消息传递。实例令牌只保存在服务端环境变量 `CAMPUS_INSTANCE_TOKEN`，不进入 JS、URL 或日志。默认回环/SSH；没有账号系统，不应直接暴露无保护管理端口。

## 帧协议 v1

一条二进制消息为 `SCG1`（4字节）+ little-endian `u32 JSON长度` + `u32 JPEG长度` + UTF-8 JSON + JPEG。元数据和图片是同一个原子消息。单图上限8MB、元数据128KB。

GS 元数据包括 protocol_version、stream、session_id、epoch、frame_id、request_id、client_time、输入/原始/实际/可见高斯数、尺寸、SH、质量参数、CUDA核心/转换/拷贝/CPU像素转换/JPEG/服务墙钟及缓冲覆盖数。交通数据还含源序号、源时间基准和同帧统计。

输入延迟只用浏览器单调时间相减：`提交时 performance.now() - 原样回传 client_time`。没有相减两台机器的时钟。提交表示 decode+rAF 后更新图片，未测显示器扫描。

## 有界任务与显存

GPU 调度器只有一个执行线程，scene/traffic/face 轮转，每模块最多一个已提交项。推理、CUDA同步和编码不会堵塞 ASGI 事件循环。没有 Redis、Celery 或复杂 stream 调度；CUDA events 使用当前实际 stream。

GS 每条流仅一个执行项+一个可覆盖相机待办；输出队列1，慢客户端覆盖未发送帧。网关直接 await 双向发送传递背压；前端单解码项+一个最新待办，释放旧 blob URL。持续拖动使用最新完成帧，绝不因输入又变化而全部丢弃。frame_id 在 epoch 内递增；reset/重连产生 epoch，静止状态不渲染。

视频逐帧读取，媒体时间不受推理墙钟影响；快时按媒体节奏等待，慢时允许慢放。RTSP独立采集线程只存最新帧，读超时有界。浏览器使用采集端单调时间及序号，丢帧不重新编号压缩时间。暂停视频保留在途帧到恢复，直播丢弃暂停期间结果。

ByteTrack ID是本次会话中的跟踪编号，不是永久身份。遮挡、漏检和类别抖动可能导致ID断裂，进而增加累计；本工程不做ReID，也不把累计值解释成准确的独立自然人数。vehicle合并COCO car=2/motorcycle=3/bus=5/truck=7，person=0和bicycle=1单列。

场景/模型延迟加载并常驻，普通帧不 empty_cache。GS 停止关闭流、等待当前执行结束后卸载场景；控制断开结束交通并卸载实例模型；模块关闭由重启配置生效，关闭接口和 UI 且不导入专属依赖。正常服务退出经 ASGI lifespan 等待工作结束和释放线程池。

GPU端是唯一业务存储权威。索引原子替换，事件追加 fsync，基本锁保护。模型与特征格式指纹绑定，改变预处理不能混用旧特征。历史复制独立候选快照，所以删除人员不会破坏过去图片。

每组一个进程实例、端口、data_root。模型文件可在同一只读工程内共享，各进程显存仍会叠加；没有按单人 FPS 推算无限并发人数。
