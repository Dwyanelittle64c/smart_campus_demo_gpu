# 模型、场景、视频与公开照片

所有复制限定为需求白名单，源于旧工程明确可用的公开样例；本工程是独立文件副本，运行不依赖旧目录。没有复制旧人员库、识别事件、缓存、CPU helper或环境。精确字节数/SHA256见根目录 `assets-manifest.json`。准备后运行不联网下载。

## Houseplant

Marcel Padilla，[固定数据版本 c3e5ec0a8ddb3ab26f28a067a29d272fe1a23411](https://github.com/marcelpadilla/splats/tree/c3e5ec0a8ddb3ab26f28a067a29d272fe1a23411/data/plant)，CC BY4.0。保留plant.splat、meta.json、完整scene.ply、原camera.json、source.json。

**署名：Houseplant by Marcel Padilla，CC BY4.0。本工程使用由量化.splat转换的标准INRIA PLY，全量113648高斯，示例并非校园实景。** 完整PLY SHA256为 `a3b5d0466105baecceb2119760eee0a646aee378981f1ff24c804b860d490588`。

素材只有SH DC（degree0），量化时已经丢失的高阶系数不能恢复。GPU版主要恢复使用完整数量、提高真实分辨率与速度，不能把GPU等同于重建了缺失信息。检查了gsplat官方Large Scene示例，其路径要求先训练Garden，并不直接提供许可明确的高阶权重；本轮高阶SH真实场景仍待提供，非零degree1合成夹具验证了通道/方向。

## 预训练权重

|文件|固定来源/版本|许可|
|---|---|---|
|models/yolov8n.pt|[Ultralytics assets v8.3.0](https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt)，调用库8.3.228|Ultralytics AGPL-3.0体系，保留对应代码许可|
|face_detection_yunet_2023mar.onnx|[OpenCV Zoo YuNet](https://github.com/opencv/opencv_zoo/tree/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/face_detection_yunet)|MIT|
|face_recognition_sface_2021dec.onnx|[OpenCV Zoo SFace](https://github.com/opencv/opencv_zoo/tree/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/face_recognition_sface)|Apache-2.0|

模型文件以manifest的内容hash锁定；许可参考快照固定到opencv_zoo commit48b10fa…，不声称该快照重新训练了权重。YuNet输出解码依据OpenCV4.10.0 face_detect.cpp，五点对齐直接调用官方alignCrop，SFace输入按官方feature契约。只做预训练推理，未微调。0.363是余弦阈值起点，不是概率或安全门禁保证。

## 视频与人脸公开测试

vtest.avi来自[OpenCV4.12.0 samples/data](https://github.com/opencv/opencv/blob/4.12.0/samples/data/vtest.avi)，795帧/10FPS/79.5秒，CAVIAR研究样例。沿用原样例条件，不为其重新授权；用于真实检测、跟踪、统计，不声称标注准确率。不能用这个视频证明20/30FPS视频播放。

|照片|拍摄/作者|许可和来源|
|---|---|---|
|obama-2009.jpg，登记|2009-01-13，Pete Souza|[Official portrait of Barack Obama](https://commons.wikimedia.org/wiki/File:Official_portrait_of_Barack_Obama.jpg)，CC BY3.0|
|obama-2012.jpg，同人另一拍摄|2012-12-06，Pete Souza|[2012 portrait crop](https://commons.wikimedia.org/wiki/File:President_Barack_Obama,_2012_portrait_crop.jpg)，美国联邦政府公务作品public domain|
|biden-2021.jpg，未登记者|2021，Adam Schultz|[Joe Biden presidential portrait](https://commons.wikimedia.org/wiki/File:Joe_Biden_presidential_portrait.jpg)，public domain|

署名：2009 Obama photograph by Pete Souza，CC BY3.0；本项目缩放、裁剪、五点对齐并提特征用于公开算法示例。2012 Obama photograph by Pete Souza；2021 Biden photograph by Adam Schultz。两张Obama照片是不同年份、不同拍摄，非同图自比对。登记名明确“公开示例”，不表示人物背书。未扫描用户相册。

## 第三方代码与许可保存

- 在线渲染gsplat1.5.3 / commit937e29912570c372bed6747a5c9bf85fed877bae，Apache-2.0，`third_party/gsplat/LICENSE`；没有渲染算法补丁，Windows编译环境适配在本工程脚本。
- OpenCV解码参考、YuNet/SFace、CC BY完整许可及来源hash保存在 `third_party/licenses/`。
- 可选Graphdeco训练固定commit54c035f…，研究/评估许可保留在 `training/reference/LICENSE.md`；本轮未运行训练。
- Django、PyTorch、ORT、Ultralytics等保留安装包自带许可。不能把本工程的业务代码许可当成第三方素材统一再授权。
