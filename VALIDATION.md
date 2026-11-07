# GPU版验收记录

Git 仓库保存报告与代表性画面。下文 `docs/setup/`、逐帧 JSON、CSV 和其他原始记录属于本机生成的验收证据，未纳入版本库；新克隆可按复现命令生成。

2026-11-06～07（Asia/Shanghai），新工程 `D:\Project\smart_campus_demo_gpu`。Windows11 / i5-12500H / 16GB / RTX3050 Laptop4GB，驱动596.21；原生Windows CUDA toolkit12.1.105、MSVC14.29、Python3.11.18、torch2.4.1+cu121、gsplat1.5.3。没有安装WSL、驱动、系统CUDA，没有操作旧CPU环境或8000服务。

本文件区分**实测通过、实现未测、外部条件不足**。没有把配置存在、模拟输入、上游成绩或CPU参考当作GPU/网页通过记录。

## 实测通过

|验收项|实际结果|原始证据（相对本工程）|
|---|---|---|
|独立环境/构建|web无torch/gsplat/ORT/cv2；runtime新命名环境；固定gsplat源码与SM8.6 CUDA扩展构建成功，pip check通过；最终复用object重建87.94秒|docs/setup/{web,runtime}-environment.json、first-cold-build.log、gsplat-build-windows.log、gsplat-build-timing.json；third_party/gsplat-pin.json|
|全量原生GS|113648真实高斯、原相机、SH0；640×480/720p/1080p各4视角，每组预热20+300不同RGB，共3600帧；640默认/极近景核心P95 4.78/5.36ms|docs/performance/native-113648.json、native-stages.csv、TABLES.md、native-*.png|
|真实画质与格式|两真实视角正常盆栽，无镜像/倒置/点云替代；椭圆/旋转/前后透明遮挡、完整偏心K、CV矩阵、非零degree1 SH方向；ASCII标准PLY激活/排序及原始导出保留|docs/setup/gpu-selfcheck.json、docs/performance/fixtures/results.json、tests/test_ply.py|
|可见网页GS单独60秒|2475张不同新帧，**41.25FPS**；核心P95 6.78ms，交互至解码提交P95 24.8ms|docs/performance/web-gs-only.json|
|网页GS+交通60秒|2427张不同新帧，**40.45FPS**；延迟P95 54.8ms，交通实际持续处理新视频且前向输入/输出CUDA|docs/performance/web-gs-traffic.json|
|网页GS+交通+真实人脸60秒|2408张不同新帧，**40.13FPS**；延迟P95 54.7ms，6次真实公开照片比对完成，未只加载模型|docs/performance/web-gs-traffic-face.json|
|10分钟重复交互|24722张不同新帧，**41.20FPS**，0重连；后端RSS首尾中位+0.62MB，张量40.46～40.96MB；整卡显存中位+63MB，不宣称整卡完全无漂移|docs/performance/web-stability.json|
|手动交互/背压|鼠标按下拖动期间frame3→10，按钮/滚轮缩放和重置epoch生效；100输入突发交付最新请求；模拟每帧发送延迟120ms，单槽覆盖23项，最后请求160到达|docs/setup/ui-interaction.json、gateway-check.json、slow-consumer.json|
|真实交通视频/暂停|官方vtest真实CUDA YOLO+ByteTrack框/ID/轨迹，按10FPS媒体时间播放；暂停后统计时钟冻结，停止/重置/切源与ROI新轮次|docs/setup/gateway-check.json、docs/performance/traffic-real.jpg|
|坏视频与媒体范围|通过Web/CSRF上传不可解码AVI返回400，清理无效上传；模型路径下载404，能力和人脸历史仍可读|docs/setup/invalid-video-http.json|
|真实上传与ROI黑边|通过网页上传30.8MB的640×360公开视频衍生夹具；黑边拖动不改变ROI；图内拖动正确映射约[.199,.201,.800,.798]并重置源/计数；恢复全画面|docs/setup/roi-upload-check.json、wide-video-fixture.json、docs/performance/ui/roi-wide-video.jpg|
|真实浏览器摄像头|用户明确授权并手动允许；Integrated Camera640×480持续产生新采集/检测帧，CUDA前向；打开/关闭人脸预览不打断交通共享流；最后关闭tracks|docs/setup/camera-check.json；只保存元数据，不保存摄像头画面、不做真实身份比对|
|真实人脸CUDA/数值|YuNet/SFace节点profile主要Conv/Gemm均CUDA；官方CPU YuNet在640输入下坐标最大差<0.017px，SFace CPU参考余弦>0.999999；不同年份Obama匹配0.78155，Biden未知0.24882，阈值0.363|docs/setup/face-gpu-check.json、yunet_*.json、sface_*.json|
|人员/历史与异常|网页录入公开Obama2009、识别2012和未知Biden；幂等重试仅一条事件；坏图/无脸/多人脸拒绝；独立临时库验证空库、持久化、删除后快照保留、清历史不删其他素材、损坏或丢索引保护|docs/setup/gateway-check.json、face-gpu-check.json、unit-tests.log，公开示例截图|
|模块关闭/轻量启动|三个模块分别关闭及全部关闭，web/backend共8组，在无GPU包环境且缺权重条件下启动、隐藏UI、拒绝接口/WS；无算法import/任务|docs/setup/module-isolation.json|
|无GPU/缺文件|三个模块分别隐藏CUDA、分别缺场景/权重，6组明确报错，无CPU回退/自动下载|docs/setup/failure-paths.json|
|准备后的离线算法|独立测试进程拦截Python socket connect/connect_ex，实际执行全量GS、公开视频YOLO/ByteTrack、公开照片YuNet/SFace；均CUDA，0次Python连接尝试；不是系统全网抓包|docs/setup/offline-algorithms.json|
|会话/CSRF/退出|第二控制客户端拒绝，CSRF缺失403；同源固定网关；本工程停止脚本正常ASGI退出/记录移除，不按端口强杀；重启仍可读取新库|docs/setup/gateway-check.json、web-server.log、gpu-server.log|
|最终重启/网页恢复|后端离线时Web首页和健康200、网关503；恢复后自动取得新epoch全量640×480图，快速停开和重置正常；最终原图hash、新库历史、三个开关和缓存释放复核|docs/setup/ui-final-check.json、offline-http.json、final-health.json、duplicate-start.json；docs/performance/ui/final-desktop.jpg|
|独立学生实例/打包|公开素材和许可证逐hash播种独立data_root，不复制人员/历史；已有配置拒绝覆盖；SfM初始化3→2点夹具保留原文件；不是训练通过|docs/setup/packaging-check.json、assets-manifest.json|

逐帧epoch/frame_id/request_id、相机、真实尺寸/数量、JPEG SHA256、采集/接收/解码提交时刻都在原始网页JSON。核心能力估计和实际不同新帧FPS分开展示。浏览器rAF提交不是显示器扫描时间。CPU/RSS报告范围为GPU服务进程；nvidia-smi为整卡，包含桌面与浏览器。详细分段、带宽与资源见[GPU_PERFORMANCE](docs/GPU_PERFORMANCE.md)。

## 实现但未实机验收／外部条件不足

- **A100/Linux、真实校园网RTT/带宽、SSH远程成功链路**：没有服务器连接信息。已交付Linux规格、SM8.0构建、自检、组实例和SSH命令；本机双进程/慢消费者不冒称A100。
- **真实RTSP成功播放**：没有用户提供的可达设备地址。已实现受控采集线程/最新帧/超时/清理；localhost不可达地址实际报错且其他模块继续可用（docs/setup/rtsp-failure.json）。
- **真实校园COLMAP训练、训练扩展兼容、恢复和训练产物闭环**：没有图像/COLMAP与训练任务，未创建可选train环境、未占用未知GPU。已核对固定Graphdeco源码CLI、提供3050/A100路径；高阶PLY导出与SfM准备仅夹具通过。
- **许可明确的真实高阶SH场景/更多真实场景**：Houseplant本来只有DC；非零degree1夹具通过，真实高阶外观尚待素材。没有填零冒称恢复信息。
- **720p/1080p网页并行20FPS**：只有各300帧原生测试，未作网页60秒验收。默认档保持全量640×480，不预先承诺高分辨率或更多高斯也达标。
- 摄像头**拒绝权限/设备不存在**有超时/错误处理；本轮真实设备走的是允许分支，未修改系统权限去制造拒绝。摄像头人脸真实身份识别未授权也未执行；公开照片链路已验证。

主要本机全量640×480单模块和并行性能目标已达标；上述外部项保留待验收，没有降低数量/尺寸替代。

## 最小复现

在新工程根目录PowerShell，先按[README](README.md)启动两个角色；网页录入带“公开示例”标记的测试人员。以下均使用新环境：

```powershell
conda run --no-capture-output -n smart-campus-gpu-web python scripts/check_environment.py web
conda run --no-capture-output -n smart-campus-gpu-runtime python scripts/check_environment.py runtime --gpu
conda run --no-capture-output -n smart-campus-gpu-runtime python -m unittest discover -s tests -v
conda run --no-capture-output -n smart-campus-gpu-web python scripts/check_isolation.py
conda run --no-capture-output -n smart-campus-gpu-runtime python scripts/check_geometry.py
conda run --no-capture-output -n smart-campus-gpu-runtime python scripts/check_scene_gpu.py
conda run --no-capture-output -n smart-campus-gpu-runtime python scripts/check_face_gpu.py
conda run --no-capture-output -n smart-campus-gpu-runtime python scripts/check_failure_paths.py
conda run --no-capture-output -n smart-campus-gpu-runtime python scripts/check_packaging.py
conda run --no-capture-output -n smart-campus-gpu-runtime python scripts/check_offline.py
conda run --no-capture-output -n smart-campus-gpu-runtime python scripts/check_slow_client.py
# 关闭网页控制标签，避免独占拒绝；这条会实际产生一条公开人脸识别事件
conda run --no-capture-output -n smart-campus-gpu-web python scripts/check_gateway.py
conda run --no-capture-output -n smart-campus-gpu-runtime python scripts/benchmark_scene.py --sizes 640x480 1280x720 1920x1080
conda run --no-capture-output -n smart-campus-gpu-web python scripts/verify_reports.py
conda run --no-capture-output -n smart-campus-gpu-runtime python scripts/summarize_performance.py
```

原生性能复测时停止网页算法，避免其他推理改变计时。网页打开“执行设备与性能验收”，依次选择三种60秒及600秒模式，保持页面图像可见；按钮会实际运行相机、检测和公开照片识别并保存新报告，不是播放已保存帧。后续重测会覆盖同名成绩，先备份本轮docs/performance再执行。


## 2026-11-07：科技风看板与相机交互调整

按用户要求仅做最小验证，未重跑性能基准或长时间测试：桌面蓝色三列布局、全量640×480实际出图、左键旋转修正、方向键平移、缩放与重置、交通视频出帧、人员管理和识别弹窗入口均正常。场景帧号1→12，无渲染错误；平移保持旋转矩阵和内参，更新世界相机位置。右键/中键或Shift＋左键亦接入同一平移逻辑；本轮浏览器通过方向键验证平移。未开启摄像头、未新增识别记录。截图见docs/performance/ui/dashboard-blue.png。此前性能数据保留为此前版本实测，不作为本轮重新测量的成绩。
