# COLMAP → 独立训练 → 完整场景包 → GPU后端

唯一推荐训练主路径：[Graphdeco gaussian-splatting](https://github.com/graphdeco-inria/gaussian-splatting/tree/54c035f7834b564019656c3e3fcc3646292f727d)，固定 commit **54c035f7834b564019656c3e3fcc3646292f727d**。选择其标准INRIA PLY、cameras.json和完整优化器检查点恢复契约。在线渲染仍使用gsplat，不把训练器放进在线服务。

已核对固定官方版本的 train.py、arguments、dataset_readers、camera_utils 和许可；Git 仓库在 `training/reference/` 保留第三方许可，完整训练源代码按下文命令从官方克隆。**没有用户训练图像/COLMAP，也没有A100访问条件，所以本轮未创建训练环境、未编译训练扩展、未执行3050/A100训练或恢复。** 导出脚本已用带非零高阶SH的夹具验证逐字节保留和相机转换；不能当成真实训练产物闭环通过。训练仓库的研究/评估许可见参考 LICENSE.md，与gsplat Apache-2.0不同。

## COLMAP输入契约

由用户完成SfM与去畸变，目录如下：

```text
campus_small/
  images/                 # 去畸变照片，文件名与模型一致
  sparse/0/
    cameras.bin           # 或对应txt
    images.bin
    points3D.bin
```

固定版本支持 PINHOLE / SIMPLE_PINHOLE；OPENCV、RADIAL、鱼眼必须先去畸变。世界坐标和单位没有统一向上/米制保证，图像、外参、稀疏点必须来自同一重建。不要单独旋转点云或缩小世界单位。

训练 `--resolution 1/2/4/8` 表示缩放倍数，其他正数如320/800表示目标宽度，源码会同步计算相机内参；不要只改照片尺寸而保留原K。Graphdeco的FoV相机导出主点居中，无法从该JSON恢复本来未保存的偏心主点。本在线适配器能保存/处理完整K，其他来源如有cx/cy可明确提供。

## 可选独立环境

以下在训练机器执行。不要向Web或在线runtime安装训练依赖，先检查实际驱动/nvcc/C++工具。版本组合与本机在线 CUDA12.1 torch2.4.1一致便于排障，但**训练扩展的兼容性仍待实机确认**。

```bash
conda create -n smart-campus-gpu-train python=3.11 pip -y
conda run -n smart-campus-gpu-train python -m pip install torch==2.4.1 torchvision==0.19.1 --index-url https://download.pytorch.org/whl/cu121
conda run -n smart-campus-gpu-train python -m pip install -r environments/train.txt
git clone https://github.com/graphdeco-inria/gaussian-splatting.git training/graphdeco
git -C training/graphdeco checkout 54c035f7834b564019656c3e3fcc3646292f727d
git -C training/graphdeco submodule update --init submodules/diff-gaussian-rasterization submodules/simple-knn submodules/fused-ssim
conda run -n smart-campus-gpu-train python -m pip install ./training/graphdeco/submodules/diff-gaussian-rasterization ./training/graphdeco/submodules/simple-knn ./training/graphdeco/submodules/fused-ssim
conda run -n smart-campus-gpu-train python -m pip check
```

Windows需在已有MSVC x64环境中编译，CUDA_HOME指向实际12.1，架构8.6；Linux A100用实际兼容gcc/g++、CUDA_HOME和架构8.0。子模块由父commit固定，不能换成最新HEAD。无需初始化SIBR viewer，不需要显示器、X11或远程桌面。首次编译与模型训练耗时分别保存日志，不让第一位学生打开网页时编译。

## 3050 4GB保守试验

先用15～30张约320px的小物体/小区域图像。4GB能渲染11.4万高斯不等于能训练它；图像缓存、梯度与优化器远比在线前向占显存。先复制一份独立训练数据，由COLMAP为副本导出TEXT，然后只限制副本的初始化点：

```bash
colmap model_converter --input_path /DATA/campus_COPY/sparse/0 --output_path /DATA/colmap_text --output_type TXT
conda run -n smart-campus-gpu-train python training/prepare_sparse.py --points-txt /DATA/colmap_text/points3D.txt --output /DATA/campus_COPY/sparse/0/points3D.ply --maximum 5000
```

该输出只是SfM点，不能当标准高斯场景导入在线服务。固定源码优先读取已存在points3D.ply；原始数据保留。进入训练仓库，用GPU训练环境：

```bash
python -u train.py -s /DATA/campus_COPY -m /OUTPUT/campus_3050 --disable_viewer --data_device cpu --resolution 320 --sh_degree 0 --iterations 3000 --densify_until_iter 0 --test_iterations 3000 --save_iterations 1500 3000 --checkpoint_iterations 1500 3000
```

这会禁用致密化，目的为最小流程验证，画质较低。上游不存在 `--max_gaussians`；5000初始化点与停止致密化才是这里的限制方式。若OOM，记录参数/峰值后降低试验输入或转A100，不承诺完整校园在4GB训练成功。

## A100无头训练与恢复

同一固定仓库，先小场景确认依赖，训练与在线演示错开GPU。路径均为待用户替换的示例，无真实服务器信息：

```bash
mkdir -p /OUTPUT /LOGS
conda activate smart-campus-gpu-train
cd training/graphdeco
nohup python -u train.py -s /DATA/campus_small -m /OUTPUT/campus_a100 --disable_viewer --data_device cpu --resolution 800 --iterations 7000 --sh_degree 3 --densify_until_iter 5000 --densification_interval 200 --densify_grad_threshold 0.0004 --test_iterations 7000 --save_iterations 3000 7000 --checkpoint_iterations 3000 7000 > /LOGS/campus_a100.log 2>&1 &
```

真实中断后复用同一数据与优化参数，仅增加：

```bash
python -u train.py -s /DATA/campus_small -m /OUTPUT/campus_a100 --disable_viewer --data_device cpu --resolution 800 --iterations 7000 --sh_degree 3 --densify_until_iter 5000 --densification_interval 200 --densify_grad_threshold 0.0004 --start_checkpoint /OUTPUT/campus_a100/chkpnt3000.pth --save_iterations 7000 --checkpoint_iterations 7000
```

保留完整日志、cfg_args、检查点和原始PLY；检查点仅训练端使用。预览可以用固定上游 `render.py --model_path ... --skip_test` 无界面输出 PNG（该脚本本轮未执行），或直接把导出包交给本GPU渲染服务。不要用在线服务加载任意.pth。

## 场景导出加载闭环

在含numpy/plyfile的训练环境或runtime执行本工程脚本。它不调用训练算法，不把高阶SH改成DC，不改坐标，不抽样：

```bash
conda run -n smart-campus-gpu-train python scripts/export_scene.py --ply /OUTPUT/campus_a100/point_cloud/iteration_7000/point_cloud.ply --cameras /OUTPUT/campus_a100/cameras.json --camera-index 0 --output /EXPORT/campus_demo --source "本组校园训练数据" --license "请填写真实数据/模型使用许可"
```

输出scene.ply原样复制并核对SHA256；camera.json保留完整CV world-to-camera、K、初始position/center/up与裁剪面；source.json记录版本/数量/SH/hash；LICENSE.txt记录用户声明。center沿原相机前方设置，因此初始朝向不变。Graphdeco自身没有导出cx/cy时只能取中心，不能伪造恢复。

把完整包部署到**GPU服务**data_root/scenes/campus_demo，配置scene.package后正常重启该实例。在GPU机器执行自检/两视角和网页交互，再给学生对应Web地址/SSH隧道；不再让学生下载场景做CPU渲染。不同训练来源需修改真实repository/commit/许可元数据，不沿用本示例冒充。

待真实数据验收时补：训练环境完整freeze、扩展编译、检查点恢复、最终PLY/SH、导出相机、GPU两视角和网页表现。目前已通过的是公开Houseplant在线Demo和导出格式夹具。
