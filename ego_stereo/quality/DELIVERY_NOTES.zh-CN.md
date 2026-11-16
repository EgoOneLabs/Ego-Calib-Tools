# 2UQ2 纯双目标定：固定参数离线核查 v1

目的：补充已有 DS 候选的双眼几何一致性与图像覆盖证据。不重新拟合内参或双目外参，不运行相机—IMU 联合标定，不修改官方 Kalibr 源码，不覆盖 BAG、参数或原报告。

现有报告已经核对过拟合误差及文件身份，本轮不再重复“导入结果是否成功”。本工具读取已知 230 对标定板图像，使用容器内官方 Kalibr 的 DS 相机几何、AprilGrid 检测和每帧板位姿估计接口，随后按官方 kalibr_camera_validator 的单眼/交叉重投影计算方式输出离线统计。它是自编离线适配器，不是直接运行官方 ROS GUI 验证器。

## Linux 工作站执行（手机、头环均不需要连接）

将压缩包下载到 /home/key/Downloads 后，执行：

```bash
unzip -n /home/key/Downloads/Ego-Capture-camera-quality-v1.zip -d /home/key/Downloads &&
python3 /home/key/Downloads/Ego-Capture-camera-quality-v1/run_quality.py
```

沿用现有 kalibr 容器、/catkin_ws、ROS Noetic 及宿主数据绑定挂载。容器已停止时启动该容器，不创建新容器，不需要 roscore 或显示器。输出独立目录：/home/key/文档/kalibr/data/2uq2_camera_quality/ds_fixed_quality_随机值。

默认参数来源：
/home/key/文档/kalibr/data/2uq2_camera_170451_v11_l4CPjq/model_eval_ds_camera/camera_4hz/ds-none_allviews_20261102T025830Z_0RCfrkJp/camera_4hz-camchain.yaml

默认先检查同一准备目录根部 camera_4hz.bag；不在根部时仅在该准备目录内寻找同名 BAG，必须匹配已知完整 SHA256，不自动选其他录制。若提示未找到 BAG，提供报错即可，不因此重录或重新标定。

- DS YAML SHA256：153ab87359e8efd07be55a3d5c4734911bfbd7b7277452eb91087c4976c97aaf。
- 原 230 对 BAG SHA256：21dddddd7ee6dc05b8d4e72f3255d7dccb8b29e076f70892d06aeecf5f633580。
- AprilGrid 6×6、tagSize=0.088m、tagSpacing=0.3，来自匹配 DS 原报告；这不替代实物尺寸核对。
- 左右话题 /cam0/image_raw、/cam1/image_raw，图像1920×1080，必须按相同精确时间戳配对；拒绝重复或不完整配对。

结束后只上传打印的 camera_quality_small_review.tar.gz。包含统计、逐角点CSV、覆盖图、首个和最差共同观测叠加图、源码与日志，不含 BAG 或全部图像。失败时同样保留日志，不自动重试。

## 如何解释输出

1. 单眼重投影：使用固定内参和每帧估计的标定板姿态，预测本眼角点；这是固定参数下的板位姿拟合残差。
2. 交叉重投影：将左眼估计的板姿态通过固定双目外参变换到右眼，预测右眼同编号角点；再反向检查。没有用右眼观测重新优化左→右的预测。
3. 两者均报告样本数、有符号均值、分量标准差、二维L2 RMS/中位数/P95/最大值，单位为原1920×1080图像的像素。近零有符号均值不等于误差接近零。
4. 覆盖是8×6网格的角点计数。非空格比例不是实际覆盖面积百分比，也没有自动“及格线”。热图上方cam0、下方cam1；网格中的数字是计数。
5. 叠加图：绿色实测角点，红色另一眼预测，黄色连线；显示缩小0.5倍，统计仍用原像素。
6. 检测器沿用filterCornerOutliers=True；统计针对检测器保留的观测。记录检测失败和共同观测对数，不把未检测到的帧伪装成零误差。
7. 只估计每帧板位姿；所有相机内参和双目外参保持固定。不会输出新的camchain替换原件。

## 明确的停止条件和边界

仅对这份230对BAG运行一次；输出后复核交叉误差、异常帧及覆盖，再决定是否已有足够证据。不要为了获得更好数字自动换模型、裁掉高误差区域或反复重跑。

原230对图像已参与参数拟合，所以本轮是同数据固定参数一致性核查，不是独立留出集泛化验证。仅靠重投影不能确定整体尺度、实物板尺寸、设备唯一编号关联或硬件同步正确；质量状态始终保留待复核，不擅自声明正式验收通过，也不默认要求重新采集。

## 当前本地验证

- 4项核心数学检查通过：双向变换与乱序共同ID配对；错误基线方向会产生明显误差；有符号均值抵消不会掩盖RMS；覆盖边界及非有限值拒绝。
- 所有Python语法检查通过。
- 当前环境没有用户Kalibr/ROS绑定和原始230对BAG，因此没有完成真实AprilGrid检测、DS投影API与容器端到端执行，必须以工作站本次输出为准。

计算方法参考：
https://github.com/ethz-asl/kalibr/wiki/calibration-validator
https://github.com/ethz-asl/kalibr/blob/master/aslam_offline_calibration/kalibr/python/kalibr_camera_validator
