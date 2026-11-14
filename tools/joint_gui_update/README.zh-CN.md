# 头环标定工具：已有数据计算和验证入口

针对已安装的 20261114-YAML-DROP 版本，复用本机 Docker 环境，不重新安装依赖。
先在头环工具的启动终端按 Ctrl+C 退出，再解压 joint-ui.zip，运行：

```bash
cd "$(xdg-user-dir DOWNLOAD)" &&
unzip -oq joint-ui.zip &&
/usr/bin/python3 joint-ui/update.py
```

程序会核对版本、备份旧程序、更新同一个桌面入口并启动。
界面版本：20261114-JOINT-GUI。关闭浏览器不等于停止程序；运行中不允许更新。

## 使用已有数据

点击页面顶部“已有数据计算／验证”，无需再次录制。

1. 选择“计算联合外参与时间偏移”或“验证已有联合参数”。
2. 从本机列表选择录制或已准备 BAG。列表显示完整路径，不用手动寻找或上传大文件。
3. 计算时选择或拖入 Camera YAML 与 IMU 噪声 YAML。
4. 验证时选择或拖入 Camera–IMU 联合外参 YAML 与 IMU 噪声 YAML。
5. 确认实验时间映射说明，点击开始。板配置读取所选录制目录中的 aprilgrid.yaml。
6. 等待完成，查看日志、下载 YAML/PDF/TXT 或点击“打开结果目录”。

两项任务均写入新的结果目录，不覆盖原数据或旧结果。原始录制会自动生成 BAG 并读回校验；
已有 BAG 会核对 SHA256 后创建独立副本。仅扫描当前容器数据根目录中已知的工具目录。
其他目录的 YAML 可直接拖入；其他磁盘的录制需要先妥善复制到当前数据根目录。

验证锁住相机内参、双目基线、Camera–IMU 外参及时间偏移，只拟合该段轨迹、重力方向和
IMU 偏置曲线。应选择另一段独立录制；它是条件一致性检查，不是完全开环预测。
当前固定验证适配器只支持已复核的 Kalibr 源码版本，不匹配会保留日志并停止。
无论成功生成文件与否，都不自动宣布质量验收；实验噪声与时间定义仍需复核。

## 当前 2UQ2 常用路径（仅本次设备，不是通用默认参数）

- 独立数据 BAG 目录：`/home/key/文档/kalibr/data/camera_imu/2UQ2/joint_experimental_input_t70cgnxk`
- Camera YAML：`/home/key/文档/kalibr/data/camera_imu/2UQ2/camera_recheck_qo1Ycf3T/camera-camchain.yaml`
- IMU YAML：`/home/key/文档/kalibr/data/camera_imu/2UQ2/joint_experimental_input_t70cgnxk/imu-experimental.yaml`
- 联合外参 YAML：`/home/key/文档/kalibr/data/camera_imu/2UQ2/joint_camera_updated_hDPklVhP/camera_imu-camchain-imucam.yaml`
- 已完成固定验证：`/home/key/文档/kalibr/data/camera_imu/2UQ2/joint_fixed_check_45b8s7du`

## 验证范围

后台计算及固定验证已通过此前独立脚本实机执行。新增界面与后台连接经过软件检查，
尚待本次桌面 App 实机验证。停止按钮只停止本次任务；关闭启动终端也会停止当前任务。
失败时数据保留，可下载 offline_review.tar.gz 供排查。不要在运行中拔插设备或修改源数据。
