# Ego-Capture 纯双目相机标定流程 v1

已接好：安卓正式会话 → 左右同帧选择 → mono8 图像 → 仅含相机的 ROS1 BAG → 完整 BAG 读回 → 官方 Kalibr 相机标定调用。
此包不修改安卓 APK、官方 Kalibr 算法、原始会话或已有 camchain。没有自动生成有效姿态、补 IMU 样本或宣称硬件同步。

## 现在先运行：真实 BAG 通路核验

当前 app_export_unplug_01 的真实媒体报告为 MEDIA_READBACK_PASS：左右各 286 帧，1920×1080，完整解码；WAV 完整解码并有非零信号。
视频 PTS 相对文本时间戳的最大差为 999999ns，符合毫秒封装精度；最大相邻帧间隔 67.387604ms，不能宣称每帧都稳定 30FPS。
已验证的视频本体无需重新拉取，手机和头环均不需要接入。

依赖：Linux 工作站 Python3、FFmpeg、Docker，以及已有 kalibr 容器（ROS Noetic、sensor_msgs、rosbag）。
默认使用宿主 /home/key/文档/kalibr/data 与容器 /data 的已有绑定挂载；程序读取实际挂载核对，不猜测映射。
如容器已停止，程序会启动这个指定容器，不创建新容器。

下载 ZIP 到 Downloads 后，在 Linux 工作站执行（本次路径无需修改）：

```bash
unzip -n /home/key/Downloads/Ego-Capture-camera-workflow-v1.zip -d /home/key/Downloads

python3 /home/key/Downloads/Ego-Capture-camera-workflow-v1/camera_workflow.py prepare \
  --session /home/key/Downloads/EgoStereoIMU-test-data/camera_media_20261104_102803_clfuz9en/session \
  --media-report /home/key/Downloads/EgoStereoIMU-test-data/camera_media_20261104_102803_clfuz9en/check/media_check.json \
  --purpose smoke
```

这条命令只准备图像并写入/读回 BAG，不运行 Kalibr 优化。成功标记为 CAMERA_BAG_READBACK_PASS。
结果位于 /home/key/文档/kalibr/data/2uq2_camera/camera_smoke_随机值。
结束后仅上传提示的 camera_workflow_small_review.tar.gz，无需上传图像/BAG。
正常源数据不重做全媒体验收：先核对已验收报告与媒体 SHA256，再在必要的图像提取过程中完整解码视频。

## 抽帧与数据含义

- 左右使用同一份原始输出帧索引，时间戳精确相等，保留原 Unix 纳秒值。
- 默认 sample-hz=4：保留首帧，再选择距离上次所选帧至少 0.25s 的实际帧，实际选取频率可能低于 4Hz；不插值、不按固定帧率改时间。
- 保留完整分辨率，FFmpeg 解码为灰度 mono8；不裁切、缩放、去畸变或重编码成有损 JPEG。PGM 是未压缩灰度图像，不等于原始彩色 JPEG 码流。
- BAG 话题固定为 /cam0/image_raw（左）、/cam1/image_raw（右）；不含 /imu0。
- 每个 BAG 消息的时间、Header、图像尺寸、编码和像素 SHA256 都与准备输入逐条比较。
- 视频时间仍为宿主 UVC 回调时间，并非已验证的曝光时间；左右同源帧不等于已证明传感器硬件同步。
- camera_manifest.json 保存所选索引、原帧索引、UVC 序号、纳秒时间、图像摘要与来源。
- PGM+BAG 会使用额外空间，4Hz 双目 1920×1080 约每秒录制素材合计 33MB（含 PGM 与 BAG，粗估）；程序按预选帧数检查空间。

## 后续真正标定

这条拔线短记录不是标定板数据，程序明确拒绝对 smoke 输入执行标定。
后续需要实际相机标定板会话。相机固定、移动板，涵盖两眼共同视野、边缘、倾斜和不同距离；不需要先补姿态解算或解决所有 IMU 问题。
如已有合适板录制，优先复用，不默认重录。

1. 用配套 check_session.py 对实际板会话生成 MEDIA_READBACK_PASS 报告。
2. 用相同 prepare 命令替换实际会话及报告路径，改成 `--purpose calibration`。
3. 核对实际标定板尺寸与图像覆盖后，再执行下面标定命令。

```bash
# 【每次修改】--root 为实际 camera_calibration_* 输出目录。
# 【执行前核对】以下示例是 6×6 AprilGrid，黑色 tag 边长 0.088m，间隙/tag边长=0.3（间隙0.0264m）。
python3 /home/key/Downloads/Ego-Capture-camera-workflow-v1/camera_workflow.py calibrate \
  --root /实际/camera_calibration_目录 \
  --model ds-none \
  --tag-size-m 0.088 --tag-spacing 0.3 --cols 6 --rows 6 \
  --confirm-calibration-inputs
```

`--confirm-calibration-inputs` 表示操作者已核对板尺寸、拍摄清晰度、覆盖和左右共同观测；程序不会自动证明这些条件成立。
`ds-none` 沿用本项目先前 DS 模型选择，仍是本次待拟合模型，不是所有设备都已验证的最终模型；显式支持 pinhole-equi / pinhole-radtan，不自动切模型或填焦距556。
Kalibr 的默认初始化、角点提取、优化和过滤保持原样。默认无需显示 GUI 报告；不加 --verbose 或 --show-extraction，保留官方默认多线程路径。
脚本核对 /catkin_ws/src/kalibr 中没有已暂存或未暂存的受版本控制源码改动；若存在改动则停止并保留日志，不回滚或覆盖。
记录源码 commit/status、容器镜像 ID、输入 BAG/板配置摘要、完整日志和 real/user/sys。
若初始化要求手动焦距，当前非交互调用会失败并保留日志，需先复核原因；不盲目重跑或自动答556。

输出：camera-camchain.yaml、camera-results-cam.txt、camera-report-cam.pdf。
三份文件齐全且退出码0时仅标记 OUTPUTS_COMPLETE_REVIEW_PENDING，仍需要复核重投影误差、覆盖和几何合理性；不会自动替换旧参数。
每次准备生成独立目录；禁止在已尝试的目录覆盖 BAG 或重跑优化，失败证据完整保留。

## 验证情况和边界

合成数据的 5 项验证通过：左右配对与 BAG 全像素/时间读回、输入摘要变化拒绝、smoke 标定拒绝、图像被修改拒绝、挂载路径边界识别。
本地 BAG 集成测试使用 rosbags 的 ROS1 Noetic 类型定义，验证序列化与读回；用户运行默认使用容器原生 ROS1 rosbag，尚待本次真实运行核验。
本环境没有运行用户 Docker 容器，也没有实际执行 Kalibr 优化。首版不能宣称相机标定结果已经通过。

官方接口参考：
- https://github.com/ethz-asl/kalibr/wiki/multiple-camera-calibration
- https://github.com/ethz-asl/kalibr/blob/master/aslam_offline_calibration/kalibr/python/kalibr_calibrate_cameras

## 常见问题

- Docker 权限失败：使用用户既有 Docker 权限配置；不自动 sudo 或改用户组。
- 提示路径不在挂载内：检查 `docker inspect kalibr`，用 --output-root 指向实际绑定的宿主数据目录。
- 图像或媒体摘要不一致：保留旧文件及报告，检查是否用错会话；不跳过检查。
- BAG 失败：上传本次小复核包，其中有 bag_write.log 与失败状态；不删除源数据重录。
- 后台中断：先检查容器是否还有 rosrun/Kalibr 任务，避免同时启动第二个优化任务。
