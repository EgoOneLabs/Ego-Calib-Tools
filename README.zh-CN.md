# Ego-Calib-Tools 头环标定工具

[English](README.md) · [完整标定教程](docs/user-guide/calibration/README.zh-CN.md)

Linux 上的 2UQ2 双目头环标定工具，统一提供 Camera、静止 IMU 噪声分析和 Camera–IMU 联合标定。历史 Orange Pi 四鱼眼工具保留在独立目录，按各自输入和设备说明使用。

## 从安装到使用

1. 固定主板和左右相机，连接配套排线与 USB 数据线。联合采集时部件保持刚性连接。
2. 准备 Ubuntu 22.04/24.04 x86_64 桌面环境、联网和 sudo 权限，预留至少 30 GiB 加录制空间。最终完整包的全新系统安装仍待验证。
3. 按[硬件准备](docs/user-guide/hardware/README.zh-CN.md)和[标定板打印说明](docs/user-guide/calibration-targets/README.zh-CN.md)准备平整、实测的 AprilGrid。
4. 按[下载安装说明](docs/user-guide/releases/README.zh-CN.md)取得 camera.zip 与校验文件。新版完整包含 Kalibr 镜像，已由 Blue88ight 上传至 camera-easy-v1.9-bilingual 公开预发布版。
5. 按[标定 App 教程](docs/user-guide/calibration/README.zh-CN.md)录制或导入已有数据、查看实时计算日志、取得输出文件与保存路径。首次默认英文，可切换中文。

## 输入与输出

| 模块 | 输入 | 主要输出 |
|---|---|---|
| Camera | 双目图像或 ROS1 BAG、实测板尺寸 | camera-camchain.yaml、PDF、TXT |
| IMU | 静止录制；重算需 imu_samples.csv 与 imu_capture.json | Allan 曲线、分析与报告；拟合条件满足时生成候选噪声 YAML |
| Camera–IMU | 联合数据、Camera YAML、IMU 噪声 YAML、板尺寸 | joint-camchain-imucam.yaml、PDF、TXT |

Camera 与 IMU 可互换顺序。联合数据可先录制，计算前补齐两份参数。静止 IMU 立即开始录制，时长可选，2～3 小时用于较长噪声观测。独立联合结果复核默认折叠。

## 架构与验证范围

`ego_stereo/camera_easy/` 包含本地网页、硬件采集、文件导入、任务日志、BAG 准备、Kalibr 调用与报告。Kalibr 负责求解，本工具负责流程编排。i18n.js 和 i18n.json 提供中英文本。

参考工作站已完成三项已有数据计算流程。短 IMU 数据生成了分析报告，尚未生成完整噪声 YAML；联合功能测试使用实验 IMU 参数与时间映射。硬件同步、标定精度验收及最终包全新系统安装仍待完成。详见[验证记录](docs/user-guide/guides/VALIDATION.zh-CN.md)、[项目目录树](docs/user-guide/guides/PROJECT_TREE.zh-CN.md)和[输出目录树](docs/user-guide/guides/OUTPUT_TREE.zh-CN.md)。

源码与文档已提交 [PR #1](https://github.com/EgoOneLabs/Ego-Calib-Tools/pull/1) 等待维护者审核。公开发布前确认项目和第三方再分发许可。原始录制与临时构建数据保留在工作站。

[2026-11-15 release audit / 发布检查记录](docs/user-guide/guides/RELEASE_AUDIT.zh-CN.md)
