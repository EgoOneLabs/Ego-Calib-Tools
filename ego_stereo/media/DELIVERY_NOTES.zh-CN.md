# Ego-Capture 双目相机标定准备：媒体读回核验 v1

用途：先核验安卓 code11 正式导出的 MKV、视频时间戳、导出索引和 WAV 本体。
此包是进入相机标定流程前的文件检查工具，不是相机标定工具本体，也不是 Kalibr 标定结果。

## 当前决定

纯双目相机标定继续推进，不以解决全部 IMU 间隙为前提。
相机内参与双目外参由官方 Kalibr 求解，后续工具只负责数据准备、调用和结果整理，不改官方算法。
现有 DS 双目链、实验 IMU 参数和原录制均保留，不自动替换参数。

## Linux 工作站运行

需要 Python 3、ADB、FFmpeg 与 FFprobe，无额外 Python 包。
手机接到工作站并允许 USB 调试；不需要再接头环或录制新数据。

```bash
unzip -n /home/key/Downloads/Ego-Capture-camera-preflight-v1.zip -d /home/key/Downloads

python3 /home/key/Downloads/Ego-Capture-camera-preflight-v1/pull_and_check.py
```

默认拉取已验证元数据的 app_export_unplug_01/2UQ2_session_20261103_185545。
每次在 /home/key/Downloads/EgoStereoIMU-test-data 下创建独立目录，不覆盖旧结果。
结束后上传终端提示的 check/media_check.json 即可，无需上传约 169MB 的媒体本体。
如缺少 FFmpeg，可在 Ubuntu 工作站执行 `sudo apt install ffmpeg`。
如 ADB 报设备不存在，请重新插入手机并运行 `adb devices -l`；换手机时用 `--serial` 显式指定。

已有本地会话时不必再拉取：

```bash
# 【每次修改】替换下面的会话路径；输出路径必须是尚不存在的新目录。
python3 /home/key/Downloads/Ego-Capture-camera-preflight-v1/check_session.py \
  --session /实际/会话目录 \
  --output /实际/新的检查目录
```

## 检查范围

- 左右视频完整逐帧解码，帧数、分辨率与 meta.json 一致。
- 左右时间戳逐行相等、严格递增、索引从 0 连续。
- 时间戳支持明确的 Unix 秒或整数纳秒；不自动猜测毫秒或微秒。
- export_video_index.csv 与时间戳相对时间映射精确一致；有录制起点锚时额外核验绝对映射。
- MKV 相对 PTS 与文本时间戳偏差不超过 1ms，符合当前导出器毫秒精度；不以播放器默认帧率重建时间。
- WAV 头、PCM 实际字节、采样率、声道数、时长和完整音频解码。
- 记录媒体 SHA256 和解码帧摘要，检查过程只读源文件。

MEDIA_READBACK_PASS 仅表示文件读回通过，不表示标定板可见、角点覆盖充分、图像清晰度合格、相机硬件同步或 IMU 连续性通过。
这条约 10 秒的拔线验收记录不自动当成标定素材；完成文件链路检查后，再使用合适的标定板数据。

## 下一阶段

从正式导出视频按相同帧索引选左右图像，保留时间戳，生成仅含相机的 ROS1 BAG；
调用工作站现有 kalibr 容器内的官方 kalibr_calibrate_cameras；
记录 real/user/sys 和输入摘要，保留 YAML、PDF、TXT 及日志；结果先待复核，不按退出码直接判定标定通过。

参考： https://github.com/ethz-asl/kalibr/wiki/multiple-camera-calibration
相机固定、标定板移动；左右同时覆盖，包含边缘、倾斜及不同距离。
板参数沿用待实物核对的 6×6、tagSize=0.088m、tagSpacing=0.3，不静默套用历史其他尺寸。

## 本地验证边界

使用 FFmpeg 生成的合成 MJPEG/PCM 会话验证：正常样本通过；左右时间戳不一致、WAV 截断和 MKV 截断均被拒绝。
本工具尚未在用户当前真实 MKV/WAV 上运行；这正是以上命令需要完成的验证。
