# 双目相机标定：一键入口 v1

本入口只处理 2UQ2 的 camera 标定。头环直接接 Linux 电脑，不经过手机；固定头环，按页面提示移动标定板。60 秒采集结束后自动生成并读回核对 BAG，再运行 Kalibr 的 ds-none 双目模型。

## 需要什么

| 项目 | 要求 |
|---|---|
| 系统 | 首版安装脚本面向 Ubuntu 22.04 / 24.04 桌面版、x86_64 |
| 硬件 | 完整固定的 2UQ2 双目头环、支持数据的 USB 线、平整的 AprilGrid 标定板 |
| 主机软件 | Python3、OpenCV、NumPy、PyYAML、FFmpeg、V4L2 工具、Docker、浏览器；安装脚本统一安装缺少的依赖 |
| 标定环境 | Kalibr / ROS Noetic 在 Docker 内运行，宿主机不用安装 ROS、catkin 或单独编译 Kalibr |
| 磁盘 | 默认 60 秒约保存 240 对 1920×1080 灰度图，图像和 BAG 通常占数 GiB；工具在采集前检查空间 |
| 计算硬件 | 此相机流程使用 CPU，不要求 CUDA 或独立显卡；运行时间取决于观测量、CPU 和环境 |

首次使用需要取得 `kalibr-environment.tar.gz` 环境镜像。现有工作站已有 `kalibr` 容器时会直接复用。镜像大包未包含在本小工具 ZIP；公开从 0 部署前，还需要将经核对的镜像与校验文件发布到下载入口。不能只给用户这个小 ZIP，就声称新电脑离线可以直接计算。

当前已知工作站上的镜像文件：

`/home/key/Downloads/calibration-bilingual-7FzCw93z/headband-calibration-assistant-v1.10.4-full/environment/kalibr-environment.tar.gz`

新电脑请选择下载的环境镜像文件；不需要沿用以上工作站路径。

## 首次安装，只做一次

在本目录打开终端：

```bash
bash install.sh
```

脚本申请 sudo 安装依赖、配置 Docker 和该设备的视频访问权限。已有 Docker 时不另行安装 docker.io 替换它。已有 Kalibr 容器优先复用；没有时弹出文件选择窗口，导入镜像并创建容器。不会删除旧容器、改旧挂载或覆盖旧结果。

安装完成后重新插拔头环。首次建议注销再登录，使 Docker/video 用户组生效。安装脚本会在应用菜单添加“**双目相机标定**”。

## 每次使用

1. 头环固定好，用 USB 数据线直接接 Linux 电脑；手机端不再占用这根线。
2. 打开应用菜单的“**双目相机标定**”，或执行 `bash start.sh`。
3. 等待浏览器里左右连续画面出现。检查两眼均清晰、没有黑屏。
4. 填写设备编号，核对板行列数、**实测黑色标签外框边长和标签之间空白间距（mm）**。默认 6×6、88 / 26.4 mm 是示例，不是所有板通用。
5. 点击“**开始相机标定**”，按页面提示让板覆盖中心、四角、边缘，做倾斜和远近变化；头环不要动。尽量让两个镜头都能看到板，避免反光、拖影和弯曲。
6. 默认采集 60 秒，然后自动整理图像、生成相机 BAG、读回核对，再计算 DS 双目内参与外参。也可选 90 / 120 秒；提前结束按钮只在至少保存 40 对后可用，40 对不是标定质量通过条件。
7. 结束后页面提供 PDF、YAML、TXT 和小检查包的链接。查看 PDF，确认重投影误差和观测覆盖，并核对基线是否符合实物。

第一次运行本入口仍需在真实 Linux / 头环 / 容器组合上完成验收；这里的自动化测试不能代替实机标定。源码里没有修改 Kalibr 的求解算法。

## 结果目录

旧工作站复用容器 `/data` 对应宿主目录。新建容器默认放在 `~/EgoStereoIMU/calibration_data/`。每次创建独立目录，页面会显示实际路径。

| 文件或目录 | 内容 |
|---|---|
| `images/cam0/`、`images/cam1/` | 原尺寸 1920×1080 的无损灰度 PGM，左右由同一帧拆分 |
| `camera_manifest.json` | 选中图像、整数纳秒时间、文件校验和 |
| `camera.bag` | 左右 `/cam0/image_raw`、`/cam1/image_raw`，不包含 IMU |
| `bag_verification.json` | 全部图像像素、时间和消息数量的读回核对结果 |
| `aprilgrid.yaml` | 用本次实测尺寸生成的标定板配置 |
| `camera-camchain.yaml` | 本次双目内参与外参 |
| `camera-report-cam.pdf` | Kalibr 报告 |
| `camera-results-cam.txt` | 参数和残差文本 |
| `calculation.json` | 状态、镜像 ID、输入校验和、real/user/sys 时间、输出检查 |
| `hardware.json`、`run_status.json`、日志 | 设备、环境、阶段、失败原因和命令记录 |
| `camera_easy_small_review.tar.gz` | 报告、配置与日志，不含大图像和 BAG；复核只需发这个包 |

预览为 10 FPS 的连续 MJPEG 流，FFmpeg 对原 MJPEG 解码为灰度；用于标定的图像按约 4 Hz 保存。只对预览缩小，标定图像不缩放、不矫正、不锐化。相机标定使用的时间是主机完整帧读取时间，不能拿此时间轴直接做 camera_imu。

“结果已生成”表示程序和文件检查完成，**不自动宣称标定质量通过**。没有检测目标、角点不足、优化失败、NaN、缺少输出时会显示失败，保留本次数据。输入流停止有超时，页面不会因拔线一直等待一个不完整帧。

## 关闭与问题处理

浏览器关闭后，启动终端里的任务仍继续。需要停止工具可在该终端按 Ctrl+C；只向本次标定进程组发终止信号，不关闭整个容器。

没有视频：确认插在 Linux 上、只有一套 2UQ2、没有其他应用占用设备，重新插拔或重新登录使权限生效。

提示缺少镜像：先运行 `install.sh`，选择已下载的 Kalibr 镜像。现有 `/data` 挂载不可写时会明确报出实际目录，不自动 chmod 全盘。

DS 初始化或优化失败：先看本次日志和图案是否清晰、尺寸是否正确、姿态是否丰富。不自动切模型、塞焦距或修改 Kalibr 算法来掩盖失败。

## 开发测试

在具有 OpenCV / NumPy / PyYAML / rosbags 的 Python 环境运行：

```bash
python3 -m unittest discover -s . -p test_easy.py -v
```

测试包含无损拆分、真实 ROS1 BAG 读写、尺寸换算、断流超时、输出 NaN 与缺失文件拒绝、HTTP 控制请求，以及用参考结果模拟 Kalibr 的成功/失败编排。模拟器不代表执行过真实 Kalibr。

## 新机容器启动修复

镜像自带 ENTRYPOINT 时，新建容器必须显式覆盖为 /bin/sleep，不能只添加 CMD sleep infinity。当前源码已修复，并检查启动状态。旧 camera-easy-v1 分卷内容未变，发生该故障的新机需使用 camera-fix.zip 继续安装；镜像和数据可复用。真实新机验证仍待完成。

第二版修复补充：镜像内 root 用户的 rosdep 缓存离线复制给运行用户；环境检查改为实际模块导入、DoubleSphere 模型检查及包定位，不把 Kalibr --help 返回 2 误判为环境缺失。camera-fix-v2.zip 可兼容原始安装和第一版修复。
