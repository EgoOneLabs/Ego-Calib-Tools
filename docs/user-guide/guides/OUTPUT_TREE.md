# Capture Output Directory Tree

The tree shows the main files. After export completes, back up the entire session directory. Audio availability depends on the recording.

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

[English](OUTPUT_TREE.md) · [中文](OUTPUT_TREE.zh-CN.md) · [Data formats](DATA_FORMAT.md)

## Linux calibration outputs

Paths start at the data root displayed by the app. A reused workstation can have a different root. Imported calculations use imports/<module>/<job>/.

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

IMU candidate noise YAML is conditional on adequate fitting evidence. Failed jobs can retain only status/log files. Joint recordings before processing live under camera_imu/<device>/<recording>/. Exact report prefixes may vary for older data; use the displayed result links. See [Data Formats](DATA_FORMAT.md).
