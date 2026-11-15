# Development Guide

[简体中文](DEVELOPMENT.zh-CN.md) · [Project overview](../../../README.md)

Ordinary users should use [Release packages](../releases/README.md). This repository owns Android capture; [Ego-Calib-Tools](https://github.com/EgoOneLabs/Ego-Calib-Tools) owns Linux calibration. Android source/documentation and Linux source are reviewed in their respective repository branches/PRs, without automatic merges to main.

## Source versions

Published Android code19 corresponds to `feat/single-page-code19`, commit `755dbe3cfd0a8d2dbf24c0f4b46b9aba37bb0b4b`. Do not infer main's source version from a new homepage.

```bash
git clone --branch feat/english-default-code20 \
  https://github.com/EgoOneLabs/Ego-Capture.git
cd Ego-Capture
```

The current code20 review branch is `feat/english-default-code20`; it changes fresh-install language defaults and retains explicit saved preferences. It is not yet a published APK. Preserve uncommitted work before changing checkouts.

## Android build

| Tool | Baseline |
|---|---|
| JDK | 17 |
| Gradle wrapper | 8.7 |
| Android Gradle Plugin | 8.6.1 |
| Kotlin | 1.9.24 |
| SDK | compile/target 35, minimum 31 |
| NDK | 27.3.13750724, according to project configuration |

Install/configure the SDK and `ANDROID_HOME`, then run:

```bash
./gradlew :app:testDebugUnitTest :app:assembleDebug
```

Output: `app/build/outputs/apk/debug/app-debug.apk`. Initial Gradle/Maven/SDK downloads require network access. Download failures are not headband failures. Use the same signing identity for an in-place update; do not advise uninstalling before backing up app data. Successful compilation still requires device checks for permissions, preview, recording, export and language switching.

Code20 was subsequently built on the reference workstation with this toolchain: all 46 JUnit tests passed. The debug APK and certificate were checked; phone runtime evidence and remaining limits are recorded in [Validation](VALIDATION.md).

## Linux source and package

Current PROCESS-WAIT source is on `feat/calibration-bilingual-20261115`. UI catalogs are separate from data; switching does not reload or modify parameters, paths or raw logs.

The checked-in [small installer](https://github.com/EgoOneLabs/Ego-Capture/blob/feat/english-default-code20/docs/downloads/headband-calibration.zip) and [manifest](https://github.com/EgoOneLabs/Ego-Capture/blob/feat/english-default-code20/docs/downloads/BUILD_MANIFEST.json) describe the bilingual PROCESS-WAIT source. The local final package contains code20 plus the full image-backed Linux installer; its hashes must be refreshed together after future source changes. The complete suite also includes a verified historical Kalibr image, whose provenance is retained separately.

```bash
# Check an existing installer without installing it.
unzip -oq headband-calibration.zip camera.run
bash camera.run --check
```

Source modules and responsibilities are described in [Architecture](ARCHITECTURE.md). Do not modify solver algorithms as part of documentation/localization work.

## Contributions and publication

Keep ordinary usage guides in English `README.md`, with complete Chinese `README.zh-CN.md` counterparts. Use English UI as the fresh-install default while respecting explicit language choices. Preserve third-party licenses and original diagnostics.

Every PR should state the trigger, resulting behavior, tests and remaining limits. Never force-push over others' work, write directly to main or auto-merge. Do not upload private datasets or device parameters as defaults. The project-wide license and third-party redistribution scope still require maintainer decisions.
