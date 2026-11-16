> 历史版本记录。当前双语版安装与使用请从[最新下载与教程](https://github.com/EgoOneLabs/Ego-Capture/blob/feat/english-default-code20/docs/releases/README.zh-CN.md)开始。以下版本和发布状态保留作历史参考。

# 统一头环标定 App README

[English](README.md) · [仓库总览](../../README.zh-CN.md)

本目录为 Linux Camera、IMU、Camera–IMU 统一工具源码。完整英中使用教程位于本次项目检查包 `01-documentation/docs/calibration/`，包含下载安装、测量板、现场录制、已有文件导入、两份 YAML 来源、日志、输出与排障。

普通用户优先运行检查包根目录的 Linux 安装入口。源码安装在仓库根目录执行：

```bash
bash ego_stereo/camera_easy/install.sh /实际路径/kalibr-environment.tar.gz
bash ego_stereo/camera_easy/start.sh
```

面向 Ubuntu 22.04/24.04 x86_64 桌面，需要联网和 sudo。启动终端保持打开，网页端口可能变化，退出在终端 Ctrl+C。新页面默认英文，按钮切换中英；浏览器偏好按源保存，新端口可能重新英文默认。

相机：固定头环、移动板，无需 IMU 参数。IMU：头环放稳，立即录制无预热，可自定义 1 分钟至 24 小时，建议 2～3 小时而非硬性下限。联合：固定板、移动整套头环，可先录制；计算需第一步相机 YAML 与第二步 IMU 噪声 YAML，不能用 PDF/TXT 代替。

开始/结束和进度位于连续预览旁；计算显示实时日志及真实输出路径。已有录制可拖入或手动选择，联合结果复核默认折叠。保留原始数据、板配置、参数、版本、报告和日志。实验时间映射与噪声权重不等于正式验收，生成文件不等于最终精度或硬件同步已验证。

本次双语源码尚待浏览器、真机和新机安装验证，不能当作已经发布的整包。旧说明可从 Git 历史追溯。
