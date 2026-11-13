# 双目相机标定：下载、安装和使用

适用于 Ubuntu 22.04 / 24.04 桌面版、x86_64 电脑。所有命令都在 Linux 电脑执行。

版本：v1.2，彩色连续预览。新 Ubuntu 22.04 已完成实际标定计算；v1.2 彩色画面和网页自动完成流程待实机复测。

**发布说明：以下 v1.2 下载链接在维护者运行随包上传脚本后生效。**

## 1. 准备

- 一套 2UQ2 双目头环，两个相机和主板固定牢固。
- 一根支持数据传输的 USB 线，将头环连接电脑。
- 一块平整的 AprilGrid 标定板，以及测量尺寸的尺子。
- 电脑联网，知道管理员密码。新电脑建议至少留出 30 GB 磁盘空间。

不需要手机、GitHub 账号，也不用自己编译 Kalibr。普通用户不用下载 Source code 文件。

## 2. 第一次安装

按 **Ctrl + Alt + T** 打开终端，整段复制并运行：

```bash
# 准备下载工具
sudo apt-get update &&
sudo apt-get install -y curl unzip &&

# 下载并启动安装程序
mkdir -p "$HOME/Downloads/Ego-camera-v1.2" &&
cd "$HOME/Downloads/Ego-camera-v1.2" &&
curl --fail --location --retry 5 --retry-all-errors \
  --connect-timeout 20 \
  --output download-install.sh \
  "https://github.com/EgoOneLabs/Ego-Calib-Tools/releases/download/camera-easy-v1.2/download-install.sh" &&
bash download-install.sh
```

按提示输入电脑密码，输入时不显示字符，输完按回车。等待下载、校验和安装完成，浏览器会自动打开。

新电脑会下载约 1.8 GB 的环境分卷，自动合并和校验，再安装新版程序。已有 Kalibr 的电脑只需小程序包。下载中断后重新运行上述命令，完整的环境分卷会跳过，未完成分卷会续传。

使用期间保留启动程序的终端。不要同时打开多个采集软件占用头环。

发布页：[双目相机标定 v1.2](https://github.com/EgoOneLabs/Ego-Calib-Tools/releases/tag/camera-easy-v1.2)。

## 3. 已有 Kalibr 的电脑，安装或更新

下载发布页中的 **camera-color.zip**，保存到系统“下载”文件夹，然后执行：

```bash
# 进入系统下载目录，解压并安装最新版
cd "$(xdg-user-dir DOWNLOAD)" &&
unzip -oq camera-color.zip camera.run &&
bash camera.run
```

原工作站 key@key 和已修复的新电脑 user@usr 都可以使用这一方式。先让正在进行的任务结束，再关闭旧工具的启动终端。

新版会安装到独立版本目录，更新应用菜单入口。已有采集数据和标定结果保留。

## 4. 连接并开始标定

1. 数据线一端插头环主板，另一端插 Linux 电脑。
2. 页面出现左右两幅彩色连续画面后，将头环固定好。
3. 填写设备编号、板的行数和列数。
4. 用尺测量一个标签的黑色外框边长，以及两个相邻标签黑边之间的白色空隙，按 **mm** 填写。页面中的 88 和 26.4 只是示例。
5. 默认采集 60 秒。点击“开始相机标定”，缓慢移动标定板，覆盖画面中心、四边和四角，再做倾斜及远近变化。头环保持固定，两眼尽量同时看到板。
6. 等待自动计算，看到结果文件入口和保存路径后，再打开 PDF 检查误差与画面覆盖。

彩色用于看画面；保存的标定图像仍为每眼 1920×1080 灰度图，约 4 对/秒。预览约 10 FPS，不改变 Kalibr 求解模型。

## 5. 以后怎么打开

在应用菜单搜索 **双目相机标定**，或者运行：

```bash
# 以后直接启动，不用重复安装
gio launch "$HOME/.local/share/applications/ego-camera-calibration.desktop"
```

若首次没有画面，重新插拔头环；提示权限问题时，注销并重新登录电脑，再启动。

## 6. 结果在哪，交哪些文件

页面会显示实际结果目录。原工作站复用现有容器的 `/data` 挂载目录；新建容器默认保存在 `~/EgoStereoIMU/calibration_data/`。

| 文件或目录 | 用途 |
|---|---|
| `camera-camchain.yaml` | 双目内参和外参 |
| `camera-report-cam.pdf` | 标定报告，查看误差和角点覆盖 |
| `camera-results-cam.txt` | 参数与误差摘要 |
| `aprilgrid.yaml` | 本次标定板尺寸 |
| `camera_easy_small_review.tar.gz` | 发给维护者复核的小包，不含大 BAG 和图像 |
| `camera.bag` | 左右原尺寸灰度图像的 ROS1 数据包，无 IMU |
| `images/cam0/`、`images/cam1/` | 左右无损灰度图像 |
| `calculation.json`、日志 | 环境、运行时间和问题记录 |

输出文件齐全说明计算完成。标定质量还要检查尺寸、误差、边缘覆盖及独立验证结果。

## 7. 常见问题

| 情况 | 处理方法 |
|---|---|
| 下载出现 EOF、超时或连接重置 | 恢复网络后重跑第二步 |
| 提示文件不存在 | 确认下载完成，并在文件所在目录执行命令 |
| 提示空间不足 | 腾出空间后重试，保留原始数据 |
| 画面不动或黑屏 | 检查线缆、权限和其他程序占用，重新插拔 |
| 仍看到旧版黑白预览 | 关闭旧工具终端，从应用菜单重新打开新版 |
| 缺少 YAML、PDF 或 TXT | 打开页面运行日志，上传小检查包或报错，保留本次数据 |

v1.2 已修复首次安装时容器退出、运行用户缺少 ROS 缓存、Kalibr 源码目录 Git 权限检查的问题。

## 8. 录屏顺序

展示设备和线缆 → 打开终端复制安装命令 → 展示校验和安装完成 → 连接头环看到彩色左右预览 → 填写实测板尺寸 → 固定头环并移动板 → 等待自动计算 → 打开 PDF/YAML/TXT → 退出后从应用菜单再次打开。
