# 用户安装入口

1. 下载 `camera.zip` 到浏览器默认下载目录。
2. 在文件管理器里打开下载目录，右键空白处，选择“在终端打开”。
3. 粘贴这一条命令：

```bash
unzip -oq camera.zip camera.run && bash camera.run
```

命令不包含用户名或目录名称；中文“下载”、英文 Downloads，以及其他用户自选目录都适用。安装过程按需申请 sudo，程序安装到当前用户的固定应用目录，并自动打开。以后从应用菜单打开“**双目相机标定**”，下载文件移走也不影响已安装程序。

首次全新电脑仍需 Kalibr 环境镜像。已安装容器时自动复用；镜像与安装包放在同一目录时自动识别 `kalibr-environment.tar.gz`，无需输入其路径。当前小安装包没有内置大镜像，最终公开发布须提供完整包或配置经核对的自动下载入口。缺少镜像时仍会请求选择文件，不能宣称此时已实现全新电脑完全无人值守安装。

开发检查（不修改系统）：`bash camera.run --check`。

## 维护者生成完整安装包（原工作站只做一次）

下载简化入口包后，在已经配置好 Kalibr 的原 Linux 工作站执行：

```bash
unzip -oq camera.zip camera.run && bash camera.run --make-full
```

自动导出本机 Kalibr 镜像，生成当前目录下 `camera-full/camera.zip`。这是给新用户的完整版，内置环境镜像；之后新用户仍只执行上面的普通安装命令。此打包步骤不是让每位新用户执行的。完整包可能很大，分发前需要确认托管平台单文件大小限制。

## 打包磁盘与已有镜像

打包入口优先复用已下载的 Kalibr 环境包，避免重复导出。正式生成 ZIP 前先检查可用空间；中间文件写在输出磁盘，不再占用默认 /tmp 大空间，也不再额外生成一份大型 camera.run。

维护者可指定另一块磁盘和原有镜像：

```bash
bash camera.run --make-full --output "/另一块磁盘/camera-full" --image-archive "/已有镜像/kalibr-environment.tar.gz"
```

原始镜像包和采集数据保持不变；本次生成 ZIP 的失败临时文件会自动清理。没有压缩包可复用时，导出前按 Docker 镜像大小保守预留空间。
