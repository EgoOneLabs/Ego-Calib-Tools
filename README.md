# Ego-Calib-Tools

[简体中文](README.zh-CN.md) · [Unified Calibration App README](ego_stereo/camera_easy/README.md)

Linux acquisition, input preparation and Kalibr orchestration for headband calibration. The unified 2UQ2 app provides Camera, stationary IMU noise analysis and Camera–IMU in one interface. Historical Orange Pi four-camera tools remain separate and use different inputs.

## Start here

Ordinary users should use the complete installer and the separate English/Chinese user guides delivered with the project. Source checkout is for development. The proposed `20261115-BILINGUAL` app starts in English and offers a Chinese switch; it is under review, not a published release. The previous source baseline is `6b5ebcb` / RECORD-FIX.

1. Secure the mainboard and both cameras. Use a data-capable USB cable and connect directly to Linux.
2. Use Ubuntu 22.04/24.04 desktop on x86_64, internet access and sudo. Allow at least 30 GiB plus recording/import space.
3. Print a flat 6×6 AprilGrid at actual size and measure it. Camera/Camera–IMU need the target; stationary IMU does not.
4. Follow the packaged English `README.md` or Chinese `README.zh-CN.md` for installation, recording, import and result paths.

For a source installation, open a terminal at this repository root:

```bash
bash ego_stereo/camera_easy/install.sh /actual/path/to/kalibr-environment.tar.gz
bash ego_stereo/camera_easy/start.sh
```

The image argument is needed only when no suitable environment exists. System dependencies still require network access. Keep the launcher terminal open; its local web port can change. Exit with Ctrl+C.

## Inputs and outputs

| Module | Input | Main result |
|---|---|---|
| Camera | Stereo images/BAG and measured target geometry | Camera YAML, PDF and TXT |
| IMU | Stationary data; CSV + capture JSON for reanalysis | Allan data/report; candidate YAML only when fitting permits |
| Camera–IMU | Joint data, Camera YAML, IMU-noise YAML and target geometry | Joint extrinsics/time-offset YAML, PDF and TXT |

Camera and IMU can be done in either order. Joint motion can be recorded before importing parameters. IMU starts immediately without warm-up; 2–3 hours is a recommendation and custom duration is supported. Original data is retained. Experimental time mapping/weights remain experimental; generated files do not prove hardware synchronization or final accuracy.

## Architecture and checks

`ego_stereo/camera_easy/` contains local HTTP/UI orchestration, hardware capture, bounded imports, job logs, BAG preparation, solver adapters and reports. `i18n.js`/`i18n.json` translate UI text without changing parameters or raw logs. Kalibr supplies the solver; this update does not change its algorithms.

The proposed language work passed eight targeted UI/catalog checks and syntax checks. Full regression is blocked here by missing OpenCV; browser launch is blocked by socket restrictions. New-package Docker/hardware and fresh-Ubuntu tests remain pending. See the project review bundle for the exact test record and source commits.

Contributions use independent branches and PRs for human approval. Do not merge automatically or commit large images. Retain third-party licenses; project-wide licensing and redistribution scope still need maintainer confirmation.
