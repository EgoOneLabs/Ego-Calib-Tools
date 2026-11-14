# 本次 60 秒记录：实验联合 BAG 准备与完整读回

执行端：原 Linux key@key。无需重新录制，无需重装软件，至少留出 4 GiB 磁盘空间。

```bash
cd "$(xdg-user-dir DOWNLOAD)" &&
unzip -oq joint-prepare.zip &&
/usr/bin/python3 joint-prepare/run.py
```

核对这次既有源记录的摘要，使用已有 kalibr 容器在同级新目录生成 camera_imu_experimental.bag。保留全部 490 对图像与 48160 条 IMU，不根据开头未检出的七对图像自动删除数据；实际源数量以校验后的文件为准。原始记录不修改、不删除。

实验时基：每包末计数与 USB 请求完成时刻做线性拟合，再按观测到的样本计数反推相对时间；图像使用主机完整帧接收时间，共用相对原点。相对原点只做数值平移。缺口时间保留，不插补六轴值，不根据运动信号预先拟合或移动时间偏移。

这是假设性的实验时间映射，不是厂商定义的采样或曝光时刻；传输时延、相位和变化的延迟仍未解决。回归残差不代表同步精度。任何后续优化结果仍需残差与重复性核查。

生成 BAG 后逐条读回，检查消息数量、每张原尺寸 mono8 图像像素摘要、每条 IMU 六轴数值、Header/BAG 时间一致和各话题严格递增。输出 experimental_time_model.json、bag_verification.json、review_status.json 和日志。相机 YAML、实验 IMU 权重与此前全帧角点结果一并保存。

完成或报错后上传 joint_input_review.tar.gz。不上传约 2 GiB 的 BAG。此步骤不运行联合求解，不生成最终 T_cam_imu，也不标记质量通过。

51 项软件测试通过；工具端实际写入并读回了上传的六对原图和全部 IMU，验证通过。完整 490 对 BAG 与用户本机 ROS1 后端执行仍待本次检查。任务设 10 分钟超时；若 Ctrl+C 停止等待，不要立即重复启动，容器任务可能继续运行至超时。
