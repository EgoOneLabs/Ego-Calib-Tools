# 开发与源码说明（Development Guide）

本仓库维护 Android 采集 App。Linux 标定工具由 Ego-Calib-Tools 维护，本仓库提供配套教程和可校验的程序快照，Android 源码和文档在同一候选分支检查，Linux 另仓库提交。

## 1 选择对应版本

公开 APK 基线 code19 / 0.3.8-glass-page 对应分支 `feat/single-page-code19`，已核对源提交 `755dbe3cfd0a8d2dbf24c0f4b46b9aba37bb0b4b`。默认分支的历史源码版本不应仅根据最新首页文字推断。

```bash
# 开发电脑：首次克隆，使用本次 code20 审查分支
git clone --branch feat/english-default-code20 \
  https://github.com/EgoOneLabs/Ego-Capture.git
cd Ego-Capture
```

不要直接覆盖有未提交改动的现有工程。复现历史 code19 时检出上述历史提交；本次默认英文版本使用 feat/english-default-code20。

## 2 构建工具链

| 项目 | 已使用基线 |
|---|---|
| JDK | 17 |
| Gradle | Wrapper 8.7 |
| Android Gradle Plugin | 8.6.1 |
| Kotlin | 1.9.24 |
| Android SDK | compileSdk / targetSdk 35；minSdk 31 |
| NDK | 27.3.13750724，原生组件按项目配置构建 |

本机设置 `ANDROID_HOME` / SDK 路径后执行：

```bash
./gradlew :app:testDebugUnitTest :app:assembleDebug
```

APK 通常位于 `app/build/outputs/apk/debug/app-debug.apk`。首次下载 Maven、Gradle、SDK 需要网络；SSL / EOF 错误应先查依赖下载，不要误判为头环故障。构建通过仍需真机验证权限、预览、保存和输出。

详细模块与审查发现见 [架构说明与审查（Architecture Review）](ARCHITECTURE.zh-CN.md)。

## 3 源码职责

| 目录 / 文件 | 职责 |
|---|---|
| `MainActivity.kt`、`ui/` | 权限、界面、连接和按钮状态 |
| `camera/UvcCameraSource.kt` | UVC 生命周期、原始回调及预览分流 |
| `camera/LatestPreviewDelivery.kt` 等 | 连续预览与显示帧率 |
| `recording/EpisodeRecorder.kt` | 原始会话及停止后保存任务 |
| `recording/XuImuReader.kt`、`ImuPacketParser.kt` | XU 包读取、计数和解析 |
| `recording/UsbAudioRecorder.kt` | USB 音频路由和录音 |
| `export/StereoEpisodeExporter.kt` | 左右 MKV、时间文件、名义 SI 与副本导出 |
| `export/EgoRecordFormat.java` | 文件级数据契约与时间映射 |
| `third_party/uvcandroid/` | USB/UVC 原生实现及组件许可 |
| `app/src/test/` | 状态、数据契约和组件回归检查 |

路径均相对于 `app/src/main/java/com/egouvc/phone/`，第三方与测试目录除外。

## 4 Linux 程序快照

`docs/downloads/headband-calibration.zip` 为独立 `camera.run` 自解压程序小包，来自标定仓库 PROCESS-WAIT 候选源码归档，不含 1.8 GB Docker 镜像。`BUILD_MANIFEST.json` 记录完整提交与 SHA-256。其内部保留源码和相应许可信息，可用：

```bash
unzip -oq headband-calibration.zip camera.run
bash camera.run --check
```

`--check` 只核对文件，不安装系统软件。安装脚本在需要时复用已发布环境分卷，仅提取镜像，不运行旧版 App。

后续升级应先在标定仓库提交、通过针对改动的检查，再重新构建小包和校验文件。不要仅替换 ZIP 而忘记更新校验及文档版本，不把设备私有标定参数包装成其他设备默认值。

完整用户套件另将同版源码与原镜像重新打包，放到 Release，不把大文件加入 Git。文件与发布步骤见[完整套件说明](../releases/README.md)。

## 5 文档和贡献

主页提供项目总览和上手路线；硬件、手机采集和标定分别放在 hardware、capture、calibration 的 README；架构、数据字段和验证证据放在 guides。历史 STATUS 保留但标记为历史，不与当前使用入口混写。

提交改动使用独立分支和 Pull Request，说明触发场景、行为改变、验证方法及已知边界，等待仓库维护者审批。不要在没有任务授权时强推、覆盖其他人的提交或自动合并 PR。

原始数据、媒体、设备参数或截图涉及个人和设备信息时，先确认适合公开。第三方组件许可沿用各目录；本次文档不新增或更换覆盖全项目的顶层许可证。

## 本轮构建与交付更新

code20 已在工作站构建，46 项 JUnit 全通过；不是仍未构建。当前 Linux 候选为 PROCESS-WAIT，含双语与等待求解进程修复。Android 源码与文档在同一候选分支，Linux 另仓库提交；公开 code19 克隆命令仅用于复现旧版。未推送的新分支应从交付源码快照或 Git bundle 获取，不能假定远程分支已存在。
