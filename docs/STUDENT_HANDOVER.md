# 学生交接：无GPU笔记本连接GPU服务器

学生电脑只需要已有 Conda、Python、浏览器和本工程 Web 代码。**不安装 torch/CUDA/gsplat/ORT，不下载模型或高斯数据到浏览器。** Web 进程只做页面、上传与同源网络转发。

```powershell
conda create -n smart-campus-gpu-web python=3.11 pip -y
conda run --no-capture-output -n smart-campus-gpu-web python -m pip install -r environments/web.txt
```

先由服务器维护者为每组准备独立实例/data_root/端口，例如回环18011。真实主机、账号、密钥由老师提供；本工程不包含这些值，也未连接未知服务器。

在学生终端保持 SSH 隧道：

```bash
ssh -N -L 8011:127.0.0.1:18011 USER@SERVER
```

另一个终端，在项目根目录：

```powershell
conda run --no-capture-output -n smart-campus-gpu-web python scripts/run.py web --config config/student-remote.json
```

浏览器访问 http://127.0.0.1:8010 。配置中的后端仍是 localhost8011，现在通过 SSH 转发到服务器；业务 JS 和请求链路不换一套。实例令牌若启用，由老师分别配置在服务器与学生 Web 的 `CAMPUS_INSTANCE_TOKEN` 环境变量，不填进网页、URL或公共配置。

摄像头属于**打开页面的学生电脑**，浏览器授权后向 GPU 服务上传有界 JPEG。上传视频来自学生选的文件；“服务器示例视频”则在 GPU 服务器目录。RTSP 由 GPU 服务器访问，因此学生电脑能看流不代表服务器可达。localhost/HTTPS 是浏览器摄像头安全上下文要求；拒绝授权不会影响照片、视频和 GS。

## 组间隔离与维护

服务器管理员首次创建组实例（在服务器工程根目录，公开样例已准备）：

```bash
conda run -n smart-campus-gpu-runtime python scripts/init_instance.py --data-root data/instances/group01 --config-output config/group01.local.json --gpu-port 18011 --name group01
conda run -n smart-campus-gpu-runtime python scripts/run.py gpu --config config/group01.local.json --port 18011
```

已有组不要重新播种/覆盖配置，直接启动原配置。models可共用本工程只读模型；新data_root只复制公开场景/视频/测试照片与许可，不迁移任何人员或历史。config/linux-a100.json给出同样的静态配置字段；运行前仍须准备其data_root。

- 每组一个GPU进程/端口/data_root，对应自己的Web配置或隧道目标。模型文件可共用只读副本，人员/事件/上传素材不能共用可写库。
- 每实例一个控制客户端；看到“另一控制客户端使用”时应关闭旧页面或等待租约释放，不能反复刷新抢控制。
- 修改算法在 `backend/scene`、`traffic`、`face`，在 GPU 环境执行测试。只改页面在 `templates/static/web`，Web环境即可；缺GPU时仍可做UI和离线错误路径。
- 三模块开关在配置 `modules`，修改后重启对应实例。后端决定能力，不能仅隐藏HTML而继续跑模型。
- 多组会累加CUDA上下文、模型、JPEG编码和显存。用 nvidia-smi、资源原始JSON及进程RSS逐组测量，不按单人FPS推算可容纳人数。训练另开环境并错开在线演示。
- Web在服务器部署也可，但主交付路径仍是学生本地Web + 远端GPU。受控校园网直连可修改固定backend_url，并由管理员提供受保护端口/TLS与令牌；本任务未改防火墙或开放公网。

## 最小排障

1. Web `/health/` 应能打开；失败先看Web终端/端口。
2. `/api/capabilities/` 失败则看SSH进程、目标端口、后端健康与实例令牌；不是安装GPU包到学生电脑解决。
3. 某模块失败看对应中文错误和GPU日志。检查权重、标准PLY、源路径/许可；不要清空整个data修复索引。
4. 用 `scripts/check_gateway.py` 检查本机Web到配置后端的真实HTTP/WS链路；其中交通使用允许的公开视频，人脸需要先录入公开示例。
5. 按 Ctrl+C 或 `conda run -n smart-campus-gpu-web python scripts/stop.py web --config config/student-remote.json` 正常关闭本机Web。停止GPU实例由实例维护者执行对应role/port/config，默认不碰其他组。

A100、真实校园网、真实RTSP设备和校园训练数据尚未提供；这些成功链路需在实际条件下复验，不能引用本机3050结果替代。
