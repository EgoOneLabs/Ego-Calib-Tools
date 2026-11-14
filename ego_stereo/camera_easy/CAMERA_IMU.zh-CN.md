# Camera–IMU：录制、计算和验证顺序

本模块在“头环标定工具”中，与 Camera、IMU 共用安装入口。

## 1. 三项一定要按顺序录吗

| 步骤 | 能否先录 | 计算前需要什么 |
|---|---|---|
| Camera | 可以独立录制 | 相机图像、正确的标定板配置 |
| IMU | 可以独立录制，与 Camera 顺序可互换 | 静止 IMU 数据、单位和采样时间依据 |
| Camera–IMU | 可以先录运动数据，之后补参数 | 同一套头环的相机参数、IMU 噪声参数、板配置、图像与 IMU 联合运动数据及可用时间轴 |

新用户推荐 **Camera → IMU → Camera–IMU → 独立数据验证**，便于逐项发现问题。Camera 与 IMU 并不互相依赖，不用为了调整顺序重录。

采集可以先做；联合计算不能省略相机与 IMU 参数。已有匹配、可靠且经过复核的参数也可以使用，不要求每次重新计算前两项。参数必须对应同一套传感器、分辨率、镜头设置和固定结构；设备结构变化后需要重新评估相关标定。

IMU 噪声 YAML 与完整 IMU 内参是两回事。官方要求应用 IMU 比例、轴不正交等修正，或使用能估计相应参数的 IMU 模型。本开发版正式求解封装使用 calibrated 模型，必须先有对应修正依据，不能仅凭噪声 YAML 声称满足此条件。

## 2. 当前版本能做什么

- 已接入联合运动数据录制，同时保存左右灰度图像、IMU 原始包、六轴数据、主机时间记录和本次板配置。
- 图像按约 10 对/秒保存；不把它描述成已验证的 20 Hz 采集。实际频率写入检查报告。
- 可以选择 Camera 参数 YAML 和 IMU 噪声 YAML，程序检查格式、分辨率、话题、有限数值与外参格式，并保存本次输入和 SHA256。
- 缺少参数仍允许先录制，检查结果会逐项列出缺失内容。
- 当前图像使用主机完整帧读取时间，IMU 保留包请求时间和原始计数器。主机时间区间有重叠，不等于逐样本时间和图像曝光已经对齐。
- 因此此版不会自动从这些未复核数据生成正式联合 BAG 或启动正式求解。先上传联合小检查包，核对时间与数据绑定，再完善时间转换和 BAG 生成。
- 官方 Kalibr 求解调用、输入检查及输出检查封装已编写；缺少 BAG、相机/IMU YAML、板配置、匹配的时间复核记录或 IMU 内参修正依据时，会拒绝正式求解。
- “联合采集完成”只表示本次原始数据已保存和初步检查，不表示已经有联合外参或通过质量验证。

## 3. 等正在进行的 IMU 长录结束后再更新

当前长录期间不要安装新版、关闭旧终端、重新插拔头环或启动另一份占用同一设备的程序。

本次开发不修改正在运行的那一份程序，也不访问你的头环。等长录结束并保存后，再退出旧工具安装开发包。

```bash
# 原 Linux：本次 IMU 长录结束后再执行
cd "$(xdg-user-dir DOWNLOAD)" &&
INSTALL_DIR="$(mktemp -d "$PWD/headband-joint.XXXXXX")" &&
unzip -oq headband-joint-dev.zip -d "$INSTALL_DIR" &&
bash "$INSTALL_DIR/camera.run"
```

新版标记：`20261114-JOINT-DEV`。

## 4. 第一次录制联合运动数据

1. 用数据线将完整固定的头环连接 Linux，等待左右连续预览。
2. 选择 **Camera–IMU：联合数据采集与前置检查**。
3. 核对设备编号、板行列和实测标签边长/间隔。准备光照均匀、平整且固定不动的 AprilGrid。
4. 已有参数时，选择 Camera 输出的 `camera-camchain.yaml` 和经复核的 IMU 噪声配置。还没有参数时可以留空，先保存运动数据。
5. 默认选 90 秒。把板固定住，人拿着整套头环移动，保持相机与主板 IMU 之间的固定关系。
6. 点击“录制联合标定数据”。先短暂静止，随后做左右摇头、上下点头、左右侧倾，变化一些速度，再加少量前后/左右平移，最后逐渐恢复静止。
7. 尽量让左右相机持续看清板和角点，增加不同位置、距离和角度；避免撞击、拖影、反光以及拿起放下时突然抖动。
8. 结束后看“前置检查”，将 `camera_imu_small_review.tar.gz` 上传复核。

## 5. 当前联合采集输出

页面显示宿主机真实目录：`<容器数据根目录>/camera_imu/<设备编号>/<本次运行>/`。

| 文件 | 用途 |
|---|---|
| images/cam0、images/cam1 | 左右 1920×1080 灰度图像，保持原尺寸 |
| camera_manifest.json | 图像索引、主机时间映射、数量与文件校验和 |
| imu_packets.bin | 解析通过的 IMU 原始包 |
| imu_requests.csv、imu_samples.csv | 包请求时间、原始计数器、原始值与名义 SI 换算 |
| imu_capture.json | IMU 计数、错误、缺口及停止状态；由图像结束通知停止的原始记录会标记提前结束，联合整体状态另见 joint_capture.json |
| joint_clock.json | 图像主机时间与 Unix 时间映射的锚点，明确时间依据 |
| aprilgrid.yaml、board_measurements.json | 本次板配置和实测尺寸输入 |
| input-camera.yaml、input-imu.yaml | 用户选择的参数快照；未选择则不生成 |
| joint_dependencies.json | 参数是否齐全、缺项及校验和 |
| joint_capture.json | 图像数量/频率、IMU 数量、主机区间重叠、请求延迟及待复核项 |
| camera_imu-results.txt | 原始采集检查摘要，不是联合标定参数结果 |
| camera_imu_small_review.tar.gz | 本次配置、摘要、日志，不包含大图像和原始 IMU 文件 |

## 6. 正式联合计算的输入与输出

正式计算前需准备并核对：

| 条件 | 要求 |
|---|---|
| Camera 参数 | 双目内参与外参、分辨率、左右话题顺序匹配，并检查相机标定质量 |
| IMU 参数 | 正值、有限、单位正确的噪声密度和随机游走参数、话题与采样率；另确认内参修正依据 |
| 板配置 | 与运动数据中的实体板匹配，尺寸实测 |
| 联合 BAG | 同一段运动的左右图像和 IMU，单位与消息格式正确 |
| 时间复核 | 逐样本时间递增、缺口和抖动有据可查，图像与 IMU 时基可用；复核记录与 BAG、配置校验和匹配 |

维护者求解封装使用：

```bash
rosrun kalibr kalibr_calibrate_imu_camera \
  --bag camera_imu.bag \
  --cam input-camera.yaml \
  --imu input-imu.yaml \
  --target aprilgrid.yaml \
  --imu-models calibrated \
  --dont-show-report
```

这条命令只说明正式求解接口；当前采集开发包不会绕过前置检查自动执行它。

| 求解输出 | 用途 |
|---|---|
| camera_imu-camchain-imucam.yaml | 相机相对 IMU 的变换和时间偏移 |
| camera_imu-report-imucam.pdf | 联合残差、时间间隔等图表 |
| camera_imu-results-imucam.txt | 官方求解结果摘要 |
| joint_calculation.json、joint_calibration.log | 输入核查、求解状态、运行时间和日志 |

`T_cam_imu` 把 IMU 坐标变换到相机坐标；`timeshift_cam_imu` 单位为秒，官方定义为 `t_imu = t_cam + shift`。

## 7. 怎么算验证完成

1. Camera：检查重投影误差、全画面覆盖、基线与实物一致性。
2. IMU：检查单位、计数连续性、静止条件、曲线和参数拟合是否有依据；时长只是参考。
3. Camera–IMU：检查图像/IMU 时间间隔、运动覆盖、重投影和惯性残差、外参合理性。
4. 再录一段独立运动数据，检查参数适用性或重复标定的稳定性。不能只在训练数据上计算一次就宣称全套完成。

Camera、IMU 的结果是联合计算的前提之一，但不是联合结果通过的充分条件。即使三类 YAML/PDF/TXT 都生成，仍需完成上述复核。

官方依据：

- [Camera–IMU calibration](https://github.com/ethz-asl/kalibr/wiki/camera-imu-calibration)
- [YAML formats](https://github.com/ethz-asl/kalibr/wiki/yaml-formats)
