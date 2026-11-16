# 发布下载说明（Release Downloads README）

[English](README.md) · [项目总览](../../../README.zh-CN.md)

手机采集支持 **Android 12+、arm64-v8a、USB Host / OTG**。Linux 标定安装器面向 Ubuntu 22.04/24.04 x86_64 桌面版，本次最终安装包的全新系统安装测试仍待完成。

## 发布状态

截至 2026-11-15，两份安装包已由 **Blue88ight 公开为预发布版**。未登录检查确认两个发布页与五个附件地址均可访问。源码和文档已提交 [Ego-Capture PR #2](https://github.com/EgoOneLabs/Ego-Capture/pull/2) 与 [Ego-Calib-Tools PR #1](https://github.com/EgoOneLabs/Ego-Calib-Tools/pull/1)，等待审核。

| 应用 | 公开版本入口 | 所需附件 |
|---|---|---|
| 安卓采集 | [v0.3.9-code20](https://github.com/EgoOneLabs/Ego-Capture/releases/tag/v0.3.9-code20) | `Ego-Capture-code20-debug.apk`、`SHA256SUMS` |
| Linux 标定 | [camera-easy-v1.9-bilingual](https://github.com/EgoOneLabs/Ego-Calib-Tools/releases/tag/camera-easy-v1.9-bilingual) | `camera.zip`、`camera.zip.sha256`；`environment_manifest.json` 记录环境来源 |

两个版本页及其附件已公开可访问。查看[安卓发布列表](https://github.com/EgoOneLabs/Ego-Capture/releases)或[标定发布列表](https://github.com/EgoOneLabs/Ego-Calib-Tools/releases)。历史 code19 APK 和旧标定包属于其他版本。

## 安装安卓采集 App

1. 从上述安卓版本下载 APK 与 `SHA256SUMS`，放到同一目录。Linux 上在该目录执行 `sha256sum -c SHA256SUMS`。
2. 将 APK 复制到兼容安卓手机，点击安装，允许安装来源和所需权限。此 APK 使用调试签名，证书与 code19 相同。卸载或更换签名前先备份会话。
3. 连接头环，按[数据采集教程](../capture/README.zh-CN.md)操作。首次默认英文，可切换中文，已保存选择会保留。

从源码构建时才需要 Android 开发工具。

## 安装 Linux 标定工具

1. 从上述标定版本下载 `camera.zip` 与 `camera.zip.sha256`，放入新目录。完整 ZIP 内的 `camera.run` 已包含程序与 Kalibr 镜像。
2. 在该目录打开终端，依次运行：

```bash
sha256sum -c camera.zip.sha256
sudo apt-get update
sudo apt-get install -y unzip
unzip camera.zip
bash camera.run --check
bash camera.run
```

每条成功后再执行下一条。以普通用户运行安装器，按提示输入本机 sudo 密码。系统依赖安装需要联网。预留至少 30 GiB，加上录制和导入空间。更新前结束当前任务并关闭旧启动终端。

3. USB 权限规则更新后重新插拔头环，用户组未生效时注销再登录。保留启动终端。从应用菜单打开 **Headband Calibration Tool / 头环标定工具**，或执行：

```bash
gio launch "$HOME/.local/share/applications/ego-camera-calibration.desktop"
```

4. 按[标定教程](../calibration/README.zh-CN.md)使用。浏览器端口可能变化；旧安装可能复用原数据挂载，实际保存位置以页面为准。

## 标定板与教程

从仓库下载[原始 PDF/YAML 对](../calibration-targets/README.zh-CN.md)或[标定板 ZIP](../calibration-targets/april_6x6_4x4.zip)。实际大小打印、贴平并实测。教程、标定板、源码和目录树在仓库中单独提供。

## 维护者发布检查

两个源码 PR 已提交。发布附件大小及可用服务端哈希已与工作站核对；公开 APK 已实际下载并通过 SHA256SUMS 校验。公开 Linux 校验文件与服务端哈希匹配，本次公开入口检查未再次下载 1.8 GB ZIP。维护者仍需确认再分发权限。生产签名、全新系统安装和标定精度验收仍待完成。原始录制、临时测试与构建输出保留在工作站。本地完整项目检查包与两份发布安装器分别管理。
