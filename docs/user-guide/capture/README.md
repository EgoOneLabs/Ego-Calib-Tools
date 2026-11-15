# Data Capture App README

[简体中文](README.zh-CN.md) · [Project overview](../../../README.md) · [Linux calibration](../calibration/README.md)

> **Android phones only:** Android 12 or later, arm64-v8a (64-bit), and USB Host / OTG. The APK does not run on iPhone, iOS or HarmonyOS NEXT.

This guide covers phone installation, connection, recording and backup. Ordinary recording does not require calibration or a Linux computer. The published baseline is code19 (`0.3.8-glass-page`), package `com.egouvc.phone`. Code20 (`0.3.9-english-default`) has been built and tested on the reference phone as a local candidate; it is not yet public. The code20 APK has been uploaded as a draft; see Release Downloads for availability.

## 1. Prepare the hardware

Use the matching 2UQ2 stereo headband, mainboard, ribbon cables and a data-capable OTG cable. Disconnect power before adjusting cables. Secure both cameras and the mainboard to the frame, leaving slack in the cables. Connect the headband to either the phone or the Linux computer, not to competing capture programs. The IMU is on the headband mainboard, not in the phone.

Huawei STG-AL00 is the tested reference phone. Other models require a short compatibility test. A Type-C connector alone does not establish OTG support. See [Hardware Setup](../hardware/README.md).

## 2. Install the APK

1. Obtain `Ego-Capture-code20-debug.apk` from the code20 release after publication, or check [published download availability](../releases/README.md). The older public code19 is a different version. A Source code ZIP is not an APK.
2. Open the APK from Downloads and allow installation from that source when prompted.
3. Open the app and grant camera, microphone and USB permissions as needed. If access was denied, review system permissions or tap the preview to retry.
4. Connect the headband. Wait for continuous left and right previews before recording.
5. Published code19 starts in Chinese. Tap **English** near the title. Code20 starts in English when no language preference has been saved; a deliberate existing choice is retained. The switch changes UI text, not user input or recorded files.

[Current download status and checksums](../releases/README.md)

<details><summary>Optional: install using ADB on Linux</summary>

Enable Developer options and USB debugging on the phone. Connect it to the computer and approve the computer's debugging request on the phone.

```bash
sudo apt-get update && sudo apt-get install -y adb
adb devices -l
adb install -r "$(xdg-user-dir DOWNLOAD)/Ego-Capture-code20-debug.apk"
```

Proceed only when the device state is `device`. With multiple phones, use `adb -s ACTUAL_SERIAL ...`. Back up before troubleshooting; do not uninstall or clear app data as a routine fix.

</details>

## 3. Make a short recording

<img src="../assets/capture-code19.png" alt="Published code19 capture screen; the screenshot shows the Chinese UI" width="300">

The single-page interface contains the title/language switch, stereo preview, task and device fields, target save rate, recording controls and final path.

| Setting | What to enter |
|---|---|
| Task | A recognizable name such as `task001` or `indoor_walk`; avoid path separators |
| Device | The actual headband ID, kept consistent across recordings |
| Target save rate | 30, 15 or 10 FPS; a target, not a guarantee of sustained frame rate |
| Language | English or Chinese; saved preferences are respected |

1. Confirm that both previews keep updating. Check battery and free space.
2. Enter task/device names and choose the target save rate.
3. Start recording. Names and frame-rate settings are locked during capture.
4. Record 20–30 seconds first. Keep the app in the foreground; do not lock the phone or open another USB/camera app.
5. Stop and save. Wait through saving/export; do not unplug, force-close or repeatedly press buttons.
6. Wait for the final session path, then long-press to copy it. A raw Episode directory or an enabled button alone is not proof that export succeeded.
7. Back up and inspect the complete session before starting a long task.

Audio availability depends on permissions and the actual input route. Missing audio does not by itself mean the video session was lost. No universal phone compatibility, background-recording or unlimited-duration guarantee is claimed.

## 4. Copy data to a computer

Final sessions:

```text
/storage/emulated/0/Android/data/com.egouvc.phone/files/data/<task>/<device>_session_<date-time>/
```

Raw Episodes:

```text
/storage/emulated/0/Android/data/com.egouvc.phone/files/episodes/episode_<date-time>/
```

Android file managers may restrict `Android/data`. ADB is the recommended backup method; it copies without deleting phone files.

1. Stop recording and wait for export to finish. Disconnect the headband, then connect the phone to the computer with a data cable.
2. Enable Developer options and USB debugging. Unlock the phone and approve this computer.
3. Install ADB and inspect the connection:

```bash
sudo apt-get update && sudo apt-get install -y adb
adb devices -l
```

The state must be `device`. For `unauthorized`, approve the prompt on the phone. For `offline`, check the cable and reconnect. For multiple devices, add `-s ACTUAL_SERIAL` after every `adb`. Resolve host USB permissions if reported.

4. Copy both complete roots:

```bash
# Linux computer; the phone is connected and debugging is authorized.
(
  set -euo pipefail
  mkdir -p "$HOME/EgoCapture-backup"
  adb pull /sdcard/Android/data/com.egouvc.phone/files/data \
    "$HOME/EgoCapture-backup/"
  adb pull /sdcard/Android/data/com.egouvc.phone/files/episodes \
    "$HOME/EgoCapture-backup/"
  xdg-open "$HOME/EgoCapture-backup"
)
```

To copy only one task, replace `task001` below with the actual task name:

```bash
adb pull /sdcard/Android/data/com.egouvc.phone/files/data/task001 \
  "$HOME/EgoCapture-backup/"
```

Retain timestamps, IMU, audio metadata and `meta.json` with the videos. Check the computer copy before considering deletion on the phone.

## 5. Inspect the export

- `videos/left.mkv` and `videos/right.mkv` exist and decode.
- Timestamp files match the exported frame mapping.
- `imu/imu0.csv` and `imu/imu_raw_counts.csv` exist; inspect samples/gaps against metadata.
- If metadata reports valid audio, a complete WAV is present. Otherwise inspect `audio/audio_metadata.json`.
- The selected directory is final, not `.partial`, an export in progress or a failure-diagnostics directory.

Optional decoding check on Linux, after installing FFmpeg with `sudo apt-get install -y ffmpeg`:

```bash
# CHANGE THIS: use the actual session directory on the computer.
SESSION="/actual/path/to/session"
ffmpeg -v error -i "$SESSION/videos/left.mkv" -f null -
ffmpeg -v error -i "$SESSION/videos/right.mkv" -f null -
```

A successful decoding check does not establish frame rate, synchronization or calibration accuracy. See [Data Formats](../guides/DATA_FORMAT.md).

## 6. Include calibration files when needed

This is optional for ordinary capture. Prepare the applicable parameters for this exact device and assembly in a local `calibrations` folder, then copy them before recording:

```bash
adb shell mkdir -p /sdcard/Android/data/com.egouvc.phone/files/calibrations
adb push calibrations/. /sdcard/Android/data/com.egouvc.phone/files/calibrations/
```

The exporter copies an existing directory; it does not generate, match or accept parameters automatically. Make a short recording and confirm the files appear in the final session. Reattaching the mainboard may change camera–IMU extrinsics without necessarily invalidating camera intrinsics or stationary-noise observations.

## 7. Troubleshooting

| Symptom | Next action |
|---|---|
| No preview / USB permission | Check the OTG data cable and permissions; close competing apps, reconnect and tap the preview |
| One camera abnormal | Retain diagnostics and inspect ribbon connections; do not infer export corruption from preview alone |
| Saving takes time | Allow local splitting and disk writes to finish; check free space and retain raw Episodes |
| Unplugged after stopping | Local export is designed to continue without USB; inspect its actual completion before restarting |
| No audio | Inspect permission, input route and audio metadata; do not create a dummy WAV |
| `INCOMPLETE` or unsynchronized status | Read timing and export metadata; these flags do not mean all media files are missing |
