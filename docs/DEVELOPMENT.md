# 学生开发说明

工程自行编写的Python/JS均为新实现，中文注释说明职责、输入输出和副作用。算法核心全部复用：gsplat CUDA、Ultralytics YOLO/ByteTrack、ORT CUDA + OpenCV官方YuNet解码/SFace预处理。

## 目录与扩展位置

- shared：无GPU依赖的配置、帧边界、Django基础设置。Web可以安全导入，禁止在这里import torch/cv2。
- web：Django页面、CSRF、固定目标HTTP/WS网关。上传的multipart经CSRF解析后转发临时文件流，不能再次读已消费的request.body。媒体分块转发，不无限缓存流。
- backend/core：显式模块注册表、文件索引、控制租约、单线程公平调度、仅基准启用的资源采样。
- backend/scene：标准PLY/高阶SH读取、CV相机、常驻CUDA张量、服务封装。不得把适配扩成新的投影/排序/合成算法。
- backend/traffic：输入源与生命周期、模型/Tracker、媒体时钟、归一化ROI计数。网络前向CUDA的证据在hook/events；跟踪后的框可在CPU，不能据此判断网络退回CPU。
- backend/face：ORT网络适配、模型/特征版本、人员与幂等历史。CPU只做预处理、官方对齐与余弦。
- templates/static：中文页面和三个模块脚本；FrameView负责单解码项+最新待办，Camera负责共享tracks引用。
- scripts：角色启动/优雅停止、环境/素材/基准/导出检查；training独立训练参考/点初始化，在线服务不导入它。

## 模块关闭

修改对应配置modules中的scene/traffic/face，正常停止再启动。后端先检查模块开关才导入service，缺关闭模块的依赖或权重不应影响健康/其他模块。能力接口供Web隐藏UI。不能只删HTML让后台继续执行。

新增第四个模块最短路径：写独立算法service并延迟导入重依赖；注册core/state.REGISTRY与shared配置开关；在API/WS中强制开关和控制租约；用有界任务接入调度器；添加模板/脚本入口；验证关闭时无import/任务、错误独立及资源回收。只把真正通用的协议/存储放shared/core，不耦合其他算法。

## 关键口径

底边中心位于ROI才计数；无ID只计当前，ID首次进入确定分组且跨分钟不重复。视频按PTS或解码序号/FPS回退，不能用慢推理墙钟分桶；直播保留采集相对时间，不能用丢帧后重编号压缩时间。

GS所有真实尺寸/数量/SH/质量参数进入每帧元数据。客户端按epoch和frame_id显示，不按“必须等于最新request_id”丢光结果。WS应用队列和解码队列都只保留一项待办；静止不重复出帧。不要用rAF次数当FPS。

人脸request_id在服务端合并，不能用网络重试制造重复历史；姓名只渲染textContent、不进入路径。索引损坏或已有特征对应索引丢失要报错，不能自动清空。清历史与删人员必须独立。

## 验证命令

```powershell
# 无GPU包的Web环境也能跑计数/协议测试
conda run --no-capture-output -n smart-campus-gpu-web python -m unittest discover -s tests -p test_light.py -v
# Runtime业务/PLY/导出测试；隔离临时新库，不改演示库
conda run --no-capture-output -n smart-campus-gpu-runtime python -m unittest discover -s tests -v
# 显式GPU检查，不在首页执行
conda run --no-capture-output -n smart-campus-gpu-runtime python scripts/check_geometry.py
conda run --no-capture-output -n smart-campus-gpu-runtime python scripts/check_scene_gpu.py
conda run --no-capture-output -n smart-campus-gpu-runtime python scripts/check_face_gpu.py
conda run --no-capture-output -n smart-campus-gpu-runtime python scripts/check_offline.py
conda run --no-capture-output -n smart-campus-gpu-runtime python scripts/benchmark_scene.py --sizes 640x480 1280x720 1920x1080
```

双服务启动、先在网页录入公开示例后，用Web环境执行check_gateway.py检验真实HTTP/WS、独占、epoch、背压、CUDA交通、暂停、幂等识别。它不等于浏览器显示FPS。网页验收必须实际点性能按钮，保持页面可见，保存逐帧hash及资源原始JSON。

设备缺失、A100/RTSP/真实训练数据未提供时写入VALIDATION“未实测”，不能把模拟计数或配置存在写成模型/硬件通过。所有额外性能优化先保留基准，再解释正确性、资源和画质取舍。
