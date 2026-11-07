# 智慧校园演示系统 · GPU版

GPU 第 1 版：中央三维高斯场景、左侧人车流量、右侧人员识别。使用 Django 和原生 JavaScript，Web 与 GPU 服务分别运行。无需数据库、Node.js 或云推理服务。

![智慧校园 GPU 第 1 版](docs/performance/ui/dashboard-blue.png)

已在 Windows 11 / RTX 3050 Laptop 4 GB 验证全量 Houseplant（113648 个高斯，640×480）、YOLOv8n + ByteTrack 与 YuNet/SFace 的 CUDA 执行。性能实测和范围见 [性能报告](docs/GPU_PERFORMANCE.md) 与 [验收记录](VALIDATION.md)。

## 从零上手：Windows 本机运行全部功能

下面的命令在 **Anaconda Prompt** 中执行。本机全部运行需要 NVIDIA 显卡；**没有独显的学生电脑只做第 1、2 步，再按[远程接入](#没有-gpu学生电脑如何接入)连接 GPU 服务**。

### 1. 克隆项目

```bat
git clone --recurse-submodules https://github.com/Dwyanelittle64c/smart_campus_demo_gpu.git
cd smart_campus_demo_gpu
```

私有仓库需先获得访问权限。使用 Git 克隆，下载 ZIP 不包含 gsplat 和 GLM 子模块。若已普通克隆，在项目根目录补执行 `git submodule update --init --recursive`。项目自带可用的公开场景、权重、示例视频和测试照片，不需要旧 CPU 项目。素材许可与来源见 [ASSETS](docs/ASSETS.md)。

### 2. 创建 Web 环境（Windows x64）

```bat
conda env create -f environments\windows-web.yml
conda activate smart-campus-gpu-web
python -m pip install -r environments\windows-web.freeze.txt
python -m pip check
```

Web 只需要 Django、ASGI 服务和网络转发依赖，不安装 PyTorch、CUDA 或 OpenCV。已经创建同名环境时，可跳过 `conda env create`，直接激活并核对依赖。

### 3. 创建 GPU 环境并编译 gsplat（Windows x64）

先准备可运行 `nvidia-smi` 的 NVIDIA 驱动、**CUDA Toolkit 12.1**、Visual Studio 2022 Build Tools（选 **使用 C++ 的桌面开发**、**MSVC v142 14.29 x64/x86 工具集**和 Windows SDK），以及 PowerShell 7（`pwsh`）。`nvidia-smi` 显示的是驱动支持上限；即使能看到 GPU，也仍需要 Toolkit 的 `nvcc.exe` 才能编译扩展。

```bat
conda env create -f environments\windows-runtime.yml
conda activate smart-campus-gpu-runtime
python -m pip install -r environments\windows-runtime.lock.txt
python scripts\check_assets.py
python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available()); print(torch.cuda.get_device_capability(0))"
pwsh -NoProfile -File scripts\build_gsplat.ps1
python scripts\check_environment.py runtime --gpu
```

锁文件固定 PyTorch 2.4.1 + CUDA 12.1、OpenCV、ORT GPU 等已验证依赖。构建脚本默认使用 Toolkit 路径 `C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.1`，目标架构 `8.6`（本机 3050）。路径不同可传 `-Cuda "实际路径"`；其他显卡以自检返回的计算能力设置 `-Architecture`，前提是工具链支持该架构。首次编译约数分钟，日志在 `docs/setup/gsplat-build-windows.log`。现有 GPU 服务运行时请先停掉它再重编译，以释放 `.pyd`。

自检失败时，先核对子模块、Toolkit 和 MSVC 工具集，详见 [GPU 环境与排障](docs/GPU_SETUP.md)。Linux/A100 按该文档单独编译，不能复用 Windows 二进制。

### 4. 启动服务

打开两个 **Anaconda Prompt** 窗口，都进入克隆后的项目根目录。

```bat
:: 窗口 1：GPU 算法服务，127.0.0.1:8011
conda activate smart-campus-gpu-runtime
python scripts/run.py gpu
```

```bat
:: 窗口 2：Web 页面和同源网关，127.0.0.1:8010
conda activate smart-campus-gpu-web
python scripts/run.py web
```

两个窗口保持开启，访问 [智慧校园网页](http://127.0.0.1:8010/)，点击“开始三维场景”或“开始交通检测”。如果网页提示 GPU 未连接，先打开 [GPU 健康检查](http://127.0.0.1:8011/health/) 或查看窗口 1 的输出。首页和健康检查不加载模型。

停止时在各自窗口按 **Ctrl+C**，或在项目根目录激活 Web 环境后执行 `python scripts/stop.py all`。停止脚本只处理本项目登记的进程；独立实例需传对应 `--config` 与 `--port`。

## 没有 GPU：学生电脑如何接入

学生电脑完成克隆和 Web 环境安装后，向管理员获取服务器和组实例信息。在一个终端保持 SSH 隧道（把 `USER@SERVER` 换成实际账号和地址；`18011` 为示例远端端口）：

```bat
ssh -N -L 8011:127.0.0.1:18011 USER@SERVER
```

另一终端在项目根目录启动 Web，然后打开 [8010 页面](http://127.0.0.1:8010/)：

```bat
conda activate smart-campus-gpu-web
python scripts/run.py web --config config/student-remote.json
```

服务器端部署、组实例配置和端口转发见 [学生交接](docs/STUDENT_HANDOVER.md)。A100/Linux 服务器方案尚未实机验收。

## 一次完整演示

1. 三维点击“开始三维场景”，左键拖动旋转，右键/中键或Shift＋左键拖动平移；点选三维窗口后也可用方向键平移（Shift加速）。滚轮/＋－缩放，重置同时清除旋转、缩放和平移；停止后释放GS场景。默认实际使用全部113648高斯，640×480，SH0来自素材本身。网页只接收JPEG，静止不重复渲染，网页FPS会回零。
2. 交通保留“服务器示例视频”，点击开始；框、ID、有限轨迹和同帧统计同时显示。拖动矩形ROI会开启新统计轮次；暂停/继续、停止、重置语义分开。10FPS的vtest视频按原媒体时间播放，检测处理能力不等于播放FPS。
3. 新克隆的人员库和历史为空。先在“人员管理”点击“录入公开示例 · Obama 2009”，再打开“识别一次”：Obama 2012 是同一人的另一张照片，Biden 2021 是未登记者。照片来源与许可见 [ASSETS](docs/ASSETS.md)。
4. 浏览器摄像头必须主动授权，来自打开网页的电脑；与人脸预览共享受控MediaStream，最后一个消费者关闭才释放tracks。照片/视频不需要摄像头权限。RTSP连接发生在GPU服务器，不接受学生本机任意文件路径。
5. 需要复验时展开GS“执行设备与性能验收”，运行GS单独/交通并行/三模块并行/10分钟稳定性。三模块模式会用公开照片做若干次真实识别，产生明确标记的公开示例记录。保持图像与页面可见，不在别人的统计演示中运行测试。

## 配置和数据

默认 `config/local-3050.json`。可复制为自己的配置并传 `--config`，或设置 `CAMPUS_CONFIG`；不包含真实凭证。变更后重启，三模块开关在GPU端强制执行并同步页面。

|配置|用途|
|---|---|
|local-3050.json|本机双进程，完整场景640×480|
|student-remote.json|学生只运行Web，8011经SSH转发远端GPU|
|linux-a100.json|组实例示例，端口18011/data_root独立；未A100实测|

scene.package指向data_root下包含scene.ply/camera.json/source.json/许可的包。支持标准INRIA PLY位置、log scale、logit opacity、wxyz、完整可用SH；普通XYZ/RGB点云和任意.pth拒绝。`max_gaussians=null`表示全量，`sh_mode=auto`使用真实可用阶数；公开DC/抽样性能对照可以配置，但不能当作全量基线成绩。尺寸是实际输出像素，不是CSS放大尺寸。

相机支持CV world_to_camera和完整fx/fy/cx/cy/width/height/near/far，也兼容原position/center/up；不改世界尺度。换包后重启，检查两视角及输入数量。Houseplant由量化.splat转换，原本只有DC；GPU不会恢复已丢失的高阶细节。

业务权威存储在GPU的data_root：

|路径|重启行为|
|---|---|
|scenes / videos / test_faces / uploads|保留素材；上传生成asset_id|
|faces/people.json、UUID目录|保留原图、对齐脸、单位特征与版本|
|recognitions/events.jsonl、images|历史最新在前，独立快照保留|
|runtime/traffic-roi.json|ROI保留|
|交通计数、Tracker、活动相机|重启清零/关闭|

删除人员与清空历史是不同操作；前者不会破坏旧快照，后者不删除人员、模型、视频或场景。损坏索引不自动覆盖为空库。余弦阈值0.363只是已用公开夹具核验的起点，不是准确概率；没有活体或真实门禁安全承诺。

## 学生和后续开发

无GPU电脑只安装web，使用 [STUDENT_HANDOVER](docs/STUDENT_HANDOVER.md) 的SSH转发路径。服务器配置/组数据根可由 `scripts/init_instance.py` 创建，只复制公开样例，不复制业务库。训练是可选第三环境，参见 [3DGS_TRAINING](docs/3DGS_TRAINING.md)；流程为COLMAP→训练服务器→导出完整场景→GPU加载→学生网页，不让轻薄本本地渲染。

[ARCHITECTURE](docs/ARCHITECTURE.md) 解释协议、背压、会话与调度；[DEVELOPMENT](docs/DEVELOPMENT.md) 解释模块、开关、新增功能和测试。正常运行不自动下载或重新编译扩展。缺模型只影响对应模块；GPU不可用会明确失败，不偷偷转CPU。

Git 中只保存代码、依赖锁、公开演示素材、报告和代表性截图。上传文件、人员库、历史、本机配置、编译日志和逐帧原始记录不会提交；需要原始记录时按 [VALIDATION](VALIDATION.md) 在自己的机器生成。
