# Hardware Setup README

[简体中文](README.zh-CN.md) · [Project overview](../../../README.md)

Prepare the assembly before installing software. This project targets the matching 2UQ2 stereo USB headband; matching appearance or VID:PID alone does not establish compatibility.

## Equipment

| Item | Requirement |
|---|---|
| Cameras | Two matching cameras secured to the same rigid frame |
| Mainboard | Matching headband board with its IMU |
| Cables and mount | Matching ribbon cables, locks and reliable fasteners |
| USB cable | Data-capable; phone connection also requires USB Host / OTG |
| Phone for capture | Android 12+, arm64-v8a, OTG; reference: Huawei STG-AL00 |
| Computer for calibration | Ubuntu 22.04/24.04 desktop, x86_64, network, sudo and stable power |
| Target for Camera / Camera–IMU | Flat AprilGrid on a rigid backing; not needed for stationary IMU |

Reference USB ID: `1bcf:0b15`. Consult the kit/vendor instructions for connector orientation, pinout and power ratings; do not infer them from this software guide.

## Assembly

1. Disconnect power before inserting or adjusting ribbon cables. Check orientation and locks against the kit instructions.
2. Secure both cameras and the mainboard. When the frame moves, none of them should rotate, slide or swing relative to the others.
3. Provide cable slack and strain relief. Move the frame, not the USB cable or loose board.
4. Clean the lenses. Mount the target flat and use even lighting without glare or significant motion blur.
5. During joint motion, move the complete rigid assembly. Do not support a loose mainboard separately by hand.

Re-taping the mainboard can change camera–IMU extrinsics. Recompute the affected joint parameters. Reuse of camera parameters depends on whether the camera/lens geometry changed; board movement alone does not prove every parameter is invalid.

## Connections

| Task | Connection and app |
|---|---|
| Daily capture | Headband → phone over OTG; Android capture app |
| Three calibration modules | Headband → Linux USB; unified calibration tool |
| Recompute existing data | Files on Linux; existing-recording workflow |

Use only one device-owning program at a time. Grant the requested permissions and confirm continuous stereo images before recording.

## Space and recording conditions

Initially allow at least 30 GiB for Linux deployment, plus recording/import space indicated by the app. This is a planning recommendation, not a hardware-derived minimum. Phone storage includes both raw Episodes and exports.

For stationary IMU recording, disable sleep, maintain power, use a stable surface and leave the cable slack. Do not touch the device or table. No forced level orientation or warm-up countdown is required. Two to three hours is recommended for long-term noise observation; custom durations are supported.

Next: [Downloads](../releases/README.md), [Target printing](../calibration-targets/README.md), [Capture](../capture/README.md), or [Calibration](../calibration/README.md).
