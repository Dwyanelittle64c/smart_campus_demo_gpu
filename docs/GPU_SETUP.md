# GPU 环境与实际构建

本机实际采用 **原生 Windows**。现有 WSL2 Debian 能看到 GPU，但没有 Linux Conda、nvcc 或 g++；没有安装 WSL、修改驱动、重启或重装系统 CUDA。旧 `smart-campus-cpu` 环境及8000服务未操作。

## 已安装并运行的组合

- 新命名环境位于 Conda 默认外部目录：`smart-campus-gpu-web`、`smart-campus-gpu-runtime`。Python 3.11.18 / Django 5.2.19；训练环境未创建，因没有训练数据与任务。
- RTX 3050 Laptop 4GB，驱动596.21。nvidia-smi 的 CUDA13.2是驱动能力上限，实际编译使用**已有 toolkit12.1.105**，不是安装了CUDA13.2。
- torch2.4.1+cu121 / torchvision0.19.1+cu121，自带 CUDA12.1 runtime / cuDNN9.1。3050 CUDA 架构8.6。
- gsplat1.5.3，commit `937e29912570c372bed6747a5c9bf85fed877bae`，Apache-2.0；glm 子模块为父仓库固定版本。现成 CUDA 前向，不修改投影/排序/合成核心。
- ONNX Runtime GPU1.20.0（CUDA12 / cuDNN9），Ultralytics8.3.228，OpenCV唯一发行包 opencv-python4.10.0.84，NumPy1.26.4。Windows wheel 不因设置 DNN target 就支持 CUDA，本项目不走 OpenCV 网络推理。
- ORT先 import torch 预载兼容 DLL。`face-gpu-check.json` 与原始节点 profile 证明 YuNet/SFace 主要网络算子实际 CUDA；不是只查看 provider 列表。YOLO hook 记录实际前向输入/输出 CUDA 与 events；ByteTrack 的结果框转 CPU 属于正常后处理。

精确实际依赖与检查日志见 `environments/`、`docs/setup/`。普通 ORT/OpenCV CPU 参考仅用于验证数值，不是运行失败回退。

## Windows 复现

在项目根目录 PowerShell，使用现有 Conda：

```powershell
conda create -n smart-campus-gpu-web python=3.11 pip -y
conda create -n smart-campus-gpu-runtime python=3.11 pip -y
conda run --no-capture-output -n smart-campus-gpu-web python -m pip install -r environments/web.txt
conda run --no-capture-output -n smart-campus-gpu-runtime python -m pip install torch==2.4.1 torchvision==0.19.1 --index-url https://download.pytorch.org/whl/cu121
conda run --no-capture-output -n smart-campus-gpu-runtime python -m pip install -r environments/runtime.txt
./scripts/build_gsplat.ps1
conda run --no-capture-output -n smart-campus-gpu-runtime python -m pip check
conda run --no-capture-output -n smart-campus-gpu-runtime python scripts/check_scene_gpu.py
conda run --no-capture-output -n smart-campus-gpu-runtime python scripts/check_face_gpu.py
```

构建脚本仅导入现有 VS2022 / MSVC14.29 的当前进程环境，设置 CUDA_HOME12.1、SM8.6、MAX_JOBS=2，安装固定本地源码扩展。setuptools 固定75.1.0，避免旧 torch 在未初始化 MSVC 时走到新版缺失的 distutils 接口。首次构建日志窗口约6分钟（文件时间边界，非精密计时），原始日志保存在first-cold-build.log；最终固定依赖下复用object重建实测87.94秒，详见gsplat-build-timing.json。没有逐网页请求 JIT；若 `gsplat.csrc` 缺失，明确要求先准备，不自动编译或退回CPU。

网络失败只重试目标下载，不关 TLS 验证、不改系统代理、不往 base 安装。先前官方 PyTorch wheel 命中本机下载缓存；没有复用其他环境目录。缺依赖可在关闭代理后执行同一目标环境命令。

在线服务显式设置Ultralytics固定版本支持的YOLO_OFFLINE=true、YOLO_AUTOINSTALL=false，sync=false只写实例data_root/runtime下的配置。模型文件缺失即报错，不触发下载。Windows重编译前先正常停止GPU角色，以释放已加载的.pyd文件；Web无需安装或编译这些包。

## Linux A100 路径：配置已交付，未实机验证

使用服务器已有 Conda、支持 CUDA12.1 的驱动/toolkit与兼容gcc/g++；先检查，不照抄 nvidia-smi 的 CUDA数字。不要复制 Windows `.pyd` 或环境目录到 Linux。

```bash
conda create -n smart-campus-gpu-runtime python=3.11 pip -y
conda run -n smart-campus-gpu-runtime python -m pip install torch==2.4.1 torchvision==0.19.1 --index-url https://download.pytorch.org/whl/cu121
conda run -n smart-campus-gpu-runtime python -m pip install -r environments/runtime.txt
git -C third_party/gsplat checkout 937e29912570c372bed6747a5c9bf85fed877bae
git -C third_party/gsplat submodule update --init --recursive
export CUDA_HOME=/usr/local/cuda-12.1  # 按实际已有路径修改
export PATH="$CUDA_HOME/bin:$PATH"
export TORCH_CUDA_ARCH_LIST=8.0
export MAX_JOBS=2
conda run -n smart-campus-gpu-runtime python -m pip install ./third_party/gsplat --no-build-isolation --no-deps
conda run -n smart-campus-gpu-runtime python -m pip check
# 仅首次创建该组：复制公开样例和许可，业务人员/历史为空；已存在配置拒绝覆盖。
conda run -n smart-campus-gpu-runtime python scripts/init_instance.py --data-root data/instances/group01 --config-output config/group01.local.json --gpu-port 18011 --name group01
export CAMPUS_CONFIG=config/group01.local.json
conda run -n smart-campus-gpu-runtime python scripts/check_scene_gpu.py
conda run -n smart-campus-gpu-runtime python scripts/check_face_gpu.py
conda run -n smart-campus-gpu-runtime python scripts/run.py gpu --config config/group01.local.json --port 18011
```

上面是按固定源码/接口核对的可执行路径，**不是 Linux/A100 安装或性能通过记录**。A100 不需要显示器/OpenGL/X11；统一 CPU JPEG，不依赖 NVENC。学生无需这些包，只装 web。

本机实际完整freeze在windows-*.txt；重装Windows可使用windows-web.freeze.txt及windows-runtime.lock.txt，后者仍需单独编译固定gsplat。Linux的environments/linux-runtime.yml是待验证规格，不是本机生成的Linux锁文件。Linux的opencv-python可能需要系统已有libGL/libglib等动态库；先执行import检查，缺库由服务器管理员按系统处理。不要再同时安装headless发行包来掩盖依赖冲突，本服务不会调用imshow。

常见故障：CUDA DLL缺失先核对torch/ORT同一CUDA与cuDNN大版本；编译错误检查真正的nvcc/cl路径；OOM先停止同GPU上的训练或其他实例并记录资源，不能悄悄改基线数量/尺寸；后端断开时Web仍启动，页面明确报错。

参考：[gsplat v1.5.3](https://github.com/nerfstudio-project/gsplat/tree/v1.5.3)、[gsplat API](https://docs.gsplat.studio/main/apis/rasterization.html)、[ORT CUDA兼容表](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html)。
