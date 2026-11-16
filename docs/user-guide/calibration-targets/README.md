# Calibration Targets & Dimensions

[简体中文](README.zh-CN.md) · [Project overview](../../../README.md)

The four files below are preserved byte-for-byte from the supplied [original ZIP](april_6x6_4x4.zip).

| PDF | Matching YAML | Page | Grid | Black tag edge | White gap |
|---|---|---|---|---|---|
| [Full-size PDF](april_6x6_88mm_full.pdf) | [88 mm YAML](april_6x6_88mm.yaml) | 700 × 700 mm | 6 × 6 | 88 mm | 26.4 mm |
| [A4 PDF](april_6x6_25mm_A4.pdf) | [25 mm YAML](april_6x6_25mm_A4.yaml) | 210 × 297 mm | 6 × 6 | 25 mm | 7.5 mm |

Both use tag36h11, IDs 0–35 and `tagSpacing: 0.3`. The ZIP filename's “4x4” does not define the actual tag family. Electronic checks covered page dimensions, all 36 tag bounds and exact tag-code comparison against Kalibr's tag36h11 generator, allowing rotation. See [verification records](target-verification.json). This does not replace physical measurement or camera detection tests.

## Print and measure

1. Choose the matching PDF/YAML pair. A PDF supplies the printed pattern; YAML describes its geometry.
2. Print at **100% / actual size** with fit-to-page disabled. The 700 mm page requires a suitable printer; do not reduce it to A4 while retaining 88 mm settings.
3. Mount it flat on a rigid backing without tape crossing the tags, glare, bending or occlusion.
4. Measure one tag's **outer black edge**, not the paper, white margin or internal cells.
5. Measure the white gap between adjacent black outer edges.
6. Enter measured edge/gap values in **mm** in the app. YAML `tagSize` is **metres**; `tagSpacing` is **gap / edge**, not millimetres. Rows and columns are both 6.
7. If printing changed the dimensions, update the actual configuration rather than just renaming it.

Camera: keep the headband fixed and move the target. Camera–IMU: keep the target fixed and move the entire headband. Stationary IMU needs no target.

[Kalibr targets](https://github.com/ethz-asl/kalibr/wiki/calibration-targets) · [Official downloads/generator](https://github.com/ethz-asl/kalibr/wiki/downloads) · [Camera–IMU method](https://github.com/ethz-asl/kalibr/wiki/camera-imu-calibration)

The original generation command and complete redistribution-license record were not supplied with the ZIP. Maintainers must check applicable permissions before a formal release; this change does not invent a license.
