# 统一头环标定工具：IMU 开发验证版

Camera、IMU、Camera–IMU 共用一个程序和同一个安装入口。手机 Ego-Capture 不需要更换。

本版本增加 IMU 静止采集和噪声分析。Camera–IMU 入口可见但暂未启用。

## 本次先做 60 秒检查

1. 先结束旧工具的任务，关闭旧启动终端。
2. 下载 headband.zip 到 Linux 的系统“下载”目录。
3. 打开终端，执行：

```bash
cd "$(xdg-user-dir DOWNLOAD)" &&
unzip -oq headband.zip camera.run &&
bash camera.run
```

4. 将头环用 USB 数据线直接连接 Linux，等待左右预览出现。
5. 在“标定类型”选择 **IMU：静止噪声标定**。
6. 保持默认 **先做 60 秒读取检查**，把头环放稳，点击“开始 IMU 录制”。不需要标定板。
7. 等待结束，查看样本数、错误、缺口和输出文件。
8. 将 **imu_small_review.tar.gz** 发给维护者复核。读取失败时也会尽量生成这个小包。

60 秒只用于验证读取、解析、连续性与分析流程，不生成正式噪声标定配置。先通过短检查，再开始长录。

## 正式静止长录

选择“正式录制 2 小时”。工具先预热 5 分钟，之后开始计入 2 小时采集。头环保持供电、固定放稳；不要触碰、拉线或在桌面敲击。保持电脑唤醒，避免系统休眠。

正式录制前至少留出 3 GiB 空间。已有环境自动复用；安装脚本补充绘图依赖，不要求用户另装一个 IMU App。

页面显示经过时间、样本、包数、错误、重复和计数缺口。提前结束或异常退出的数据会保留，状态明确记录，不能当作已完成 2 小时采集。

## 输出文件

| 文件 | 用途 |
|---|---|
| imu_packets.bin | 正式记录阶段通过解析的 252 字节原始包 |
| imu_requests.csv | 预热及记录阶段每次请求的主机起止时间、长度、状态 |
| imu_samples.csv | 原始计数器、原始六轴整数与名义 SI 换算；不伪造逐样本硬件时间 |
| imu_capture.json | 时长、计数、重复、缺口、回跳、异常和换算说明 |
| imu-allan.csv | 各轴 Allan 曲线与有效差分数量 |
| imu-report.pdf | 加速度和陀螺仪 Allan 曲线 |
| imu-results.txt / imu-analysis.json | 分析摘要、采样率估计、斜率区间及待复核问题 |
| imu-candidate.yaml | 满足时长、静止与拟合检查时才生成的实验候选参数 |
| imu_small_review.tar.gz | 报告和摘要小包，不含原始大文件 |

结果按设备放在已有容器 `/data` 对应的宿主数据根目录下 `imu/<设备编号>/<本次目录>/`；页面显示实际路径。

## 已实现及仍待实测

- 使用 Linux UVC XU 读取头环主板 IMU：unit 3、selector 1、GET_CUR；沿用已有 Android 代码的 14×18 字节协议。
- 校验数据头、包内步长、大小端和有符号轴值。计数回绕、重复、缺口分别记录，缺口之间不拼接计算 Allan 差分，不做插值。
- SI 换算暂用原 SDK 名义比例 4096 count/g、16.4 count/(°/s)，并非每台精确比例标定。
- 采样率按主机包时间与计数器拟合估计。该估计不证明硬件时间单位，也不证明与图像曝光同步。
- Allan 白噪声与随机游走只有识别到相应斜率区间才给候选参数；短录、疑似运动、回跳或拟合不足会明确提示。
- 本机合成数据及软件测试通过；真实 Linux XU 并行读取、2 小时稳定性、噪声结果仍需本次设备验证。
- 本功能是 IMU 噪声分析，不包含六位置加速度比例、轴不正交等完整内参校准。

协议接口参考：[Linux UVC 驱动文档](https://docs.kernel.org/userspace-api/media/drivers/uvcvideo.html)。噪声模型参考：[Kalibr IMU Noise Model](https://github.com/ethz-asl/kalibr/wiki/IMU-Noise-Model)。Kalibr 求解算法未修改。
