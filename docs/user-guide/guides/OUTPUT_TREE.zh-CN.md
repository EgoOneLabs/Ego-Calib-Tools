# 采集数据输出目录树

下方列出主要文件。停止并保存后，备份整个会话目录。音频取决于实际录音状态。

```text
Android/data/com.egouvc.phone/files/
├── episodes/episode_<time>/
│   ├── video.mjpg
│   ├── video_index.csv
│   ├── imu_packets.bin
│   ├── imu_samples.csv
│   └── metadata.json
└── data/<task>/<device>_session_<time>/
    ├── videos/{left,right}.mkv
    ├── timestamps/{left,right}_timestamps.txt
    ├── imu/imu0.csv
    ├── imu/imu_raw_counts.csv
    ├── audio/audio.wav
    └── meta.json
```

[English](OUTPUT_TREE.md) · [中文](OUTPUT_TREE.zh-CN.md) · [Data formats](DATA_FORMAT.zh-CN.md)

## Linux 标定输出目录树

根目录以页面显示为准，复用工作站可能沿用旧路径。导入计算使用 imports/<module>/<job>/。

```text
<data-root>/
├── camera_easy/<device>/<recording>/
│   ├── camera.bag
│   ├── aprilgrid.yaml
│   ├── camera-camchain.yaml
│   ├── camera-report-cam.pdf
│   └── camera-results-cam.txt
├── imu/<device>/<recording>/
│   ├── imu_samples.csv
│   ├── imu_capture.json
│   ├── imu-allan.csv
│   ├── imu-analysis.json
│   ├── imu-report.pdf
│   └── imu-results.txt
└── imports/camera_imu/<job>/
    ├── camera.yaml
    ├── imu.yaml
    ├── joint-camchain-imucam.yaml
    ├── joint-report-imucam.pdf
    ├── joint-results-imucam.txt
    ├── job.log
    └── job_status.json
```

IMU 噪声候选 YAML 在拟合依据充分时生成。失败任务可能只有状态和日志。联合原始录制位于 camera_imu/<device>/<recording>/。旧数据的报告前缀可能不同，以页面链接为准。详见[数据格式](DATA_FORMAT.zh-CN.md)。
