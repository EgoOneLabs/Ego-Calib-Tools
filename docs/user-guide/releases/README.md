# Release Downloads README

[简体中文](README.zh-CN.md) · [Project overview](../../../README.md)

The phone app supports **Android 12+, arm64-v8a and USB Host / OTG**. The Linux calibration installer targets Ubuntu 22.04/24.04 desktop on x86_64. Fresh-machine installation of this final installer remains pending.

## Availability

As of 2026-11-15, both installation packages are **public pre-releases published by Blue88ight**. Their release pages and all five asset URLs were checked without authentication. The source changes are awaiting review in [Ego-Capture PR #2](https://github.com/EgoOneLabs/Ego-Capture/pull/2) and [Ego-Calib-Tools PR #1](https://github.com/EgoOneLabs/Ego-Calib-Tools/pull/1).

| Application | Public release page | Required assets |
|---|---|---|
| Android capture | [v0.3.9-code20](https://github.com/EgoOneLabs/Ego-Capture/releases/tag/v0.3.9-code20) | `Ego-Capture-code20-debug.apk`, `SHA256SUMS` |
| Linux calibration | [camera-easy-v1.9-bilingual](https://github.com/EgoOneLabs/Ego-Calib-Tools/releases/tag/camera-easy-v1.9-bilingual) | `camera.zip`, `camera.zip.sha256`; `environment_manifest.json` records environment provenance |

Both version pages and their asset URLs are publicly accessible. Check the [Android Releases page](https://github.com/EgoOneLabs/Ego-Capture/releases) or [Linux Releases page](https://github.com/EgoOneLabs/Ego-Calib-Tools/releases). The older code19 APK and historical Linux packages are separate versions.

## Android installation

1. Download the APK and `SHA256SUMS` from the Android release above into one directory. On Linux, run `sha256sum -c SHA256SUMS` there.
2. Transfer the APK to a compatible Android phone and open it. Allow the installation source and requested permissions. The APK is debug-signed and uses the same certificate as code19. Back up sessions before uninstalling or changing signing certificates.
3. Connect the headband and follow the [Data Capture App README](../capture/README.md). English is the initial default; the language switch offers Chinese and retains saved choices.

Android build tools are needed only for source builds.

## Linux installation

1. Download `camera.zip` and `camera.zip.sha256` from the Linux release above into a new directory. The complete ZIP contains `camera.run`, which includes the application and Kalibr image.
2. Open a terminal in that directory and run:

```bash
sha256sum -c camera.zip.sha256
sudo apt-get update
sudo apt-get install -y unzip
unzip camera.zip
bash camera.run --check
bash camera.run
```

Continue only when each command succeeds. Run the installer as a normal user and enter the local sudo password when requested. System dependency installation needs internet access. Allow at least 30 GiB plus recording/import space. Finish active tasks and close the old launcher before updating.

3. Reconnect USB after permission-rule updates. Log out and back in if group membership has not taken effect. Keep the launcher terminal open. Reopen **Headband Calibration Tool** from the application menu, or run:

```bash
gio launch "$HOME/.local/share/applications/ego-camera-calibration.desktop"
```

4. Follow the [Calibration App README](../calibration/README.md). The browser port may change. Existing installations may reuse a data mount; use the result path shown in the app.

## Targets and documentation

Download the [original target PDF/YAML pairs](../calibration-targets/README.md) or [target ZIP](../calibration-targets/april_6x6_4x4.zip) from this repository. Print at actual size, mount flat and measure. Tutorials, target files, source and directory trees are available in the repository separately from the installer.

## Maintainer checks

Both source PRs have been submitted. The published asset sizes and available server digests matched the workstation checks. The public APK was downloaded and verified against SHA256SUMS. The public Linux checksum matched the server digest; the 1.8 GB ZIP was not downloaded again during the public-access check. Maintainers retain responsibility for redistribution permissions. Production signing, fresh-machine installation and calibration accuracy acceptance remain pending. Keep raw recordings and temporary test/build outputs on the workstation. The optional local project review bundle is separate from the two release installers.
