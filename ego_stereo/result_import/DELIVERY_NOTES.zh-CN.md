# 已有 DS 相机结果导入 v1

此工具只读取已有结果并创建独立归档，不运行 Kalibr，不重新采集，不修改 APK，不覆盖或激活正式参数。

## 为什么这一步

当前安卓正式视频与原生 ROS1 BAG 通路已经通过；历史 DS 参数也已经存在。
重新找回的早期同名 camera_4hz YAML/PDF/TXT 实际为 pinhole-equi，不能和后续 DS 参数混用。
本工具从已知的工作站 DS 结果目录读取正确的一组文件，并核对 YAML 摘要及 PDF/TXT 摘要页中的模型、内参和双目平移。
这属于结果归档和身份核对，不是再做一轮标定实验。

## Linux 工作站执行

下载 ZIP 到 Downloads，执行以下完整命令，本次路径无需修改：

```bash
unzip -n /home/key/Downloads/Ego-Capture-camera-result-import-v1.zip -d /home/key/Downloads

python3 /home/key/Downloads/Ego-Capture-camera-result-import-v1/import_existing_calibration.py
```

默认来源：
/home/key/文档/kalibr/data/2uq2_camera_170451_v11_l4CPjq/model_eval_ds_camera/camera_4hz/ds-none_allviews_20261102T025830Z_0RCfrkJp

文件：camera_4hz-camchain.yaml、camera_4hz-report-cam.pdf、camera_4hz-results-cam.txt。
默认要求 YAML SHA256=153ab87359e8efd07be55a3d5c4734911bfbd7b7277452eb91087c4976c97aaf。
如提示来源不存在，保留报错输出，不需要重跑标定或改成其他同名目录。

Python 需要 PyYAML；未安装时自动借用既有 kalibr 容器中的 PyYAML，不安装 Python 软件。
PDF 摘要页读取需要 pdftotext；Ubuntu 缺少时可执行 `sudo apt install poppler-utils`。

输出：/home/key/文档/kalibr/data/2uq2_camera_profiles/ds_existing_随机值。
每次独立归档三个原文件、camera_profile.json 和导入说明，不覆盖旧目录。
最后上传终端提示的 existing_camera_result_small_review.tar.gz 即可；不需要上传 BAG 或重新连接手机。

## 状态含义

EXISTING_CAMERA_RESULT_IMPORTED_REVIEW_PENDING：原文件身份及基础结构核对成功，质量尚待复核。
PDF 与 TXT 的 DS 模型、内参、双目平移必须分别与 YAML 在 1e-6 绝对精度内匹配；不按文件同名推断归属。
源码还核对左右分辨率与话题顺序、有限内参、旋转正交性/行列式，记录实际双目基线，不用接近89mm作为质量通过标准。
没有自动证明图像覆盖、完整误差分布、标定板真实尺寸、设备唯一编号或硬件同步。
camera_profile.json 不会把结果写回安卓 App，也不将候选参数标记为正式验收通过。

reference_camera_ds.yaml 是已知历史 DS 基线的只读校验参考，不是为任意 2UQ2 设备通用的标定参数。

## 已验证范围

5 项针对性测试通过：归档不修改源文件且保留待复核状态；YAML 摘要不符拒绝；缺失报告拒绝；反射旋转拒绝；混入非 DS 报告拒绝。
合成 PDF 的摘要文本在单元测试中作了模拟，不冒充真实 PDF 质量审阅。
早期上传的实际 equi 结果已被真实 SHA 核对拒绝，没有误写为 DS 结果。
用户工作站上的正确 DS 三文件尚待以上命令核对；当前没有为解决归档问题重复运行 Kalibr。
