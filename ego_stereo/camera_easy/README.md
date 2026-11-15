# Unified Calibration App README

[简体中文](README.zh-CN.md) · [Repository overview](../../README.md)

This is the source directory for one Linux app with Camera, stationary IMU and Camera–IMU modules. The project review bundle contains full English and Chinese operating tutorials under `01-documentation/docs/calibration/`. That is the complete user guide; the old Chinese notes in this source tree are retained as historical references.

## Source setup

From the repository root, on Ubuntu 22.04/24.04 desktop x86_64:

```bash
bash ego_stereo/camera_easy/install.sh /actual/path/to/kalibr-environment.tar.gz
bash ego_stereo/camera_easy/start.sh
```

Installation uses sudo and network access for dependencies. The verified image is embedded in the complete camera.zip installer included in the project review bundle. Normal users should use its root Linux installer instead of configuring ROS on the host.

## Basic use

1. Confirm continuous stereo preview. English is the default; use the language button for Chinese. The preference is browser-origin-specific, and a new port can start in English again.
2. Select a module and either record now or process existing data. Start/finish controls are beside the preview.
3. Camera: fix the headband, move the target, enter measured dimensions; no IMU parameters.
4. IMU: keep still, select duration and record immediately without warm-up; no Camera parameters.
5. Joint: fix the target and move the complete headband. Recording may precede parameter import; calculation requires Camera YAML and IMU-noise YAML.
6. Read the live calculation log and use the displayed result directory. Original diagnostic logs may retain their original language.
7. Optional joint-result review is collapsed; it uses another motion recording with existing parameters and is not required for normal use.

Inputs: Camera accepts a ROS1 BAG, optionally target YAML; IMU reanalysis uses both `imu_samples.csv` and `imu_capture.json`; joint input is a BAG or complete recording folder, plus the two parameter YAML files. Dropping PDF/TXT reports does not supply parameters.

Outputs: Camera `camera-camchain.yaml`/PDF/TXT; IMU curves/analysis/report and conditional candidate YAML; joint `joint-camchain-imucam.yaml`/PDF/TXT. Keep parameters, target geometry, versions and logs with the original data. File generation is workflow evidence, not final accuracy acceptance.

This bilingual source still needs browser, hardware and fresh-install validation before release.
