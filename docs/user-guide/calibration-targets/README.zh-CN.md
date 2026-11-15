# 标定板与实际尺寸（Calibration Targets & Dimensions）

## 下载与对应关系

以下四个文件来自用户提供的原始 `april_6x6_4x4.zip`，保持原文件字节。可下载 [完整标定板压缩包](april_6x6_4x4.zip)，或分别下载需要的 PDF 和 YAML。

| PDF | 配套 YAML | 页面 | 行 × 列 | 标签黑色外框边长 | 白色空隙 |
|---|---|---|---|---|---|
| [april_6x6_88mm_full.pdf](april_6x6_88mm_full.pdf) | [april_6x6_88mm.yaml](april_6x6_88mm.yaml) | 700 × 700 mm | 6 × 6 | 88 mm | 26.4 mm |
| [april_6x6_25mm_A4.pdf](april_6x6_25mm_A4.pdf) | [april_6x6_25mm_A4.yaml](april_6x6_25mm_A4.yaml) | A4：210 × 297 mm | 6 × 6 | 25 mm | 7.5 mm |

两套均为 tag36h11、ID 0–35，`tagSpacing: 0.3`。压缩包名中的“4x4”不是本文件实际标签家族的判据。本次核对了 PDF 页面尺寸、36 个标签外框尺寸，并将每个标签内部位图与 Kalibr 官方生成器中的 tag36h11 编码逐一比较（允许旋转）；两套均精确匹配 ID 0–35。核对记录及 PDF SHA-256 见 [target-verification.json](target-verification.json)。这是电子文件检查，不代替打印尺寸实测或真实相机检测测试。

## 如何打印和填写页面

- PDF 是打印图案，YAML 是描述几何尺寸的配置，二者不能互相替代。
- 打印选择 **100% / 实际大小**，关闭“适应页面”。大版需要相应幅面的打印设备；不要缩印到 A4 后仍使用 88 mm 配置。
- 打印后量单个标签的黑色外边界，不是整张纸、白边或内部编码小格。
- 空隙量相邻黑色外边界之间的白色距离。YAML 中 `tagSpacing = 空隙 / 标签边长`，不是毫米。
- YAML 的 `tagSize` 单位是米；页面输入边长与空隙单位是毫米。
- A4 版若实测边长 25 mm、间隔 7.5 mm，则页面填 **25 和 7.5**；大版实测 88 mm、26.4 mm 时才填 **88 和 26.4**。
- 行数、列数均填 **6**，不是内部小格的数量。打印机缩放后应按实测修改配置，不能只改文件名。

贴到平整硬板上，避免纸弯曲、反光、遮挡和透明胶带跨过图案。相机标定时头环固定、移动板；联合标定时板固定、移动整套头环；IMU 静止分析不用板。

## 方法参考

[Kalibr 标定板说明](https://github.com/ethz-asl/kalibr/wiki/calibration-targets) · [官方板下载与生成器](https://github.com/ethz-asl/kalibr/wiki/downloads) · [联合标定说明](https://github.com/ethz-asl/kalibr/wiki/camera-imu-calibration)

原始生成命令及第三方图案的再分发许可未随 ZIP 提供，本次不新增许可声明；维护者发布前应核对相关许可。公开文件检查不代表对任何打印机、镜头或标定精度的通用验收。
