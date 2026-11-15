# 数据格式与时间语义（Data Formats & Timestamp Semantics）

本文说明 Android code20 和 Linux 标定工具 20261115-PROCESS-WAIT 的数据契约。两者服务同一套头环，但采集格式和时间依据不同，不能仅改扩展名互相替代。

## 1 Android 原始 Episode

根目录为应用外部文件目录下的 `episodes/episode_<日期时间>/`。原始数据是停止后导出的来源，也用于保存故障证据。

| 相对路径 | 主要内容 |
|---|---|
| `video.mjpg` | 设备原始双目 MJPEG 字节拼接 |
| `video_index.csv` | 帧偏移、长度、保存序号及主机/原生回调时间等索引 |
| `imu_packets.bin` | UVC XU 原始包，每次读取 252 字节 |
| `imu_samples.csv` | 原始轴计数与包/请求关联字段 |
| `imu_attempts.csv`、其他诊断 CSV | 读取、失败及调度诊断；具体文件以版本输出为准 |
| `metadata.json`、`quality.json` | 版本、采集参数、计数与时间语义 |
| `audio.wav`、`audio_metadata.json`、`audio_index.csv` | 录音和路由/时间说明，是否有效以元数据判断 |

每个 XU 包包含 14 个样本，每样本 18 字节：`DE C8` 头、原始大端计数字段及六轴有符号 16 位计数。计数值不直接等同 Unix 时间或已确认的硬件采样时刻。

## 2 Android 正式导出

目录：`files/data/<任务名>/<设备号>_session_<本地日期时间>/`。创建时先用 `.partial` 目录，完成后才成为正式目录；已有同名目录不会直接覆盖。

| 相对路径 | 格式和语义 |
|---|---|
| `videos/left.mkv`、`right.mkv` | MJPEG in Matroska，左右各 1920×1080；不调整分辨率，不把预览重新编码成正式视频 |
| `timestamps/left_timestamps.txt`、`right_timestamps.txt` | 每行 `导出帧序号 Unix秒`，小数 9 位；左右来自同一幅原始双目图像 |
| `imu/imu0.csv` | 下述 11 列名义 SI 数据 |
| `imu/imu_raw_counts.csv` | 原计数与包级关联，便于核对换算 |
| `audio/audio.wav` | 音频路由已核对、PCM 数据非空并封装完整时导出 |
| `audio/audio_metadata.json`、`audio_index.csv` | 音频状态、实际路由和时间依据 |
| `meta.json` | 会话、源目录、帧/样本、导出与数据状态、时间来源 |
| `export_video_index.csv`、`export_skipped_frames.csv` | 导出映射及损坏帧跳过记录；不要假设保存帧全部一定导出 |
| `calibrations/` | 预先存在时复制的参数目录；不表示内容已自动匹配或验收 |

示例时间行只展示语法：

```text
0 1790000000.123456789
1 1790000000.156790122
```

视频容器时间码精度与文本纳秒书写精度不同；当前 MKV timecode 精度为 1 ms。小数写到纳秒不代表传感器真实采样精度达到纳秒。

### IMU 正式 CSV

```text
timestamp,orientation_x,orientation_y,orientation_z,orientation_w,angular_velocity_x,angular_velocity_y,angular_velocity_z,linear_acceleration_x,linear_acceleration_y,linear_acceleration_z
```

| 字段 | 单位 / 规则 |
|---|---|
| `timestamp` | 主机 USB 请求区间中点映射到 Unix 秒，同包 14 个样本共用包级时间 |
| `orientation_*` | 四个零表示姿态不可用；不是合法估计四元数，不能当作已测姿态 |
| `angular_velocity_*` | rad/s，名义换算 `原计数 / 16.4 × π / 180` |
| `linear_acceleration_*` | m/s²，名义换算 `原计数 / 4096 × 9.80665`；保留静止重力响应 |
| 轴序 | 保留原始 XYZ；未自动应用相机坐标转换、单台比例因子或偏置校正 |

视频时间来自 native 回调 `CLOCK_BOOTTIME`，录制开始时锚定映射到 Unix；不是曝光时间。IMU 时间来自主机 USB 读取区间，不是逐样本硬件时间。音频时间也不能直接视为 ADC 采样与相机曝光同步。

`meta.json` 中的 `data_status=INCOMPLETE`、`ready_for_kalibr_camera_imu=false` 等标记体现时间或标定语义边界，不应只凭标记判定所有媒体文件丢失。应结合 `export_status`、实际文件、帧数及错误诊断区分“文件已导出”和“数据已具备完整同步标定条件”。

## 3 Linux Camera 数据

常见位置：`<数据根>/camera_easy/<设备号>/<录制>/`。图像原尺寸保存；彩色连续预览与标定灰度图分工不同。

| 文件 | 作用 |
|---|---|
| `images/cam0/`、`images/cam1/` | 原尺寸灰度图 |
| `camera_manifest.json` | 选中图像、时间与校验记录 |
| `camera.bag` | `/cam0/image_raw`、`/cam1/image_raw`，不含 IMU |
| `aprilgrid.yaml` | 板行列、米制边长、相对间距 |
| `camera-camchain.yaml` | DS 模型参数和双目外参 |
| PDF、TXT、`calculation.json`、日志 | 报告、状态和耗时；生成文件不自动等同精度验收 |

现场生成 BAG 可与原图逐帧读回；导入外部 BAG 的结构/时间检查不等于已经拿到最初原图做像素一致性验证。

## 4 Linux 静止 IMU 数据

常见位置：`<数据根>/imu/<设备号>/<录制>/`。

`imu_samples.csv` 列顺序：

```text
segment,tick_index,counter_raw,packet,host_before_ns,host_after_ns,ax_raw,ay_raw,az_raw,gx_raw,gy_raw,gz_raw,ax_m_s2,ay_m_s2,az_m_s2,gx_rad_s,gy_rad_s,gz_rad_s
```

| 字段 | 含义 |
|---|---|
| `segment` | 连续片段编号，缺口/跳变后不伪装为连续 |
| `tick_index` | 解析后的相对样本位置，保留可辨识缺口；不是直接硬件时间 |
| `counter_raw` | 原始计数值 |
| `packet` | 读取包关联编号 |
| `host_before_ns`、`host_after_ns` | 主机读取请求开始、结束的单调时钟纳秒 |
| `*_raw` | 原始轴计数 |
| `*_m_s2`、`*_rad_s` | 名义 SI 六轴值 |

`imu_capture.json` 保存状态、实际时长、样本、错误、重复、缺口、未识别跳变和名义换算系数。重算必须保留 CSV 与这个元数据文件。Allan 分析使用连续片段，不跨缺口补零或插值。候选 YAML 只有符合当前拟合条件时生成；实验混合模型权重单独标识。

Linux 的已观察计数回绕处理不能推导为 Android APK 已同步同样解析规则；两端版本需分别确认。

## 5 Linux 联合录制与计算

原始联合录制常见位置：`<根>/camera_imu/<设备号>/camera_imu_<时间和随机标识>/`。

| 输入或输出 | 内容 |
|---|---|
| 相机清单和 `images/` | 与 Camera 结构相近的图像和主机帧完成时间 |
| `imu_samples.csv`、`imu_capture.json` | 同段运动 IMU 记录 |
| `joint_clock.json` | 本次主机时钟锚点及时间来源 |
| `joint_dependencies.json` | 保存了哪些参数、还缺什么 |
| `input-camera.yaml`、`input-imu.yaml` | 提供时保存的计算输入副本 |
| 联合 BAG | 图像和 `/imu0` 的联合求解输入 |
| `joint-camchain-imucam.yaml` 等 | 联合参数与报告；旧版本前缀可能不同 |

录制不要求两份参数先齐全；求解必须有 Camera 参数、IMU 噪声参数和板配置。原始主机时间/计数可构建实验映射，但不把估计时间偏移当作硬件同步证明。

导入文件复制到 `<根>/imports/<模块>/<随机目录>/`，原文件保留；重算创建新结果目录。大 BAG 不应通过改名、删除时间间隔、补零或借其他设备参数来“凑齐”格式。

## 6 交接约定

每台头环保留设备号、装配状态、APK/工具版本、板实测尺寸与输入参数来源。视频、BAG、图像单独存储时，交接清单要指出对应路径和 SHA-256。小检查包适合反馈问题，但不替代大原始记录的备份。

[数据采集 App README（Data Capture App）](../capture/README.md) · [相机与 IMU 标定 App README（Camera & IMU Calibration App）](../calibration/README.md)
