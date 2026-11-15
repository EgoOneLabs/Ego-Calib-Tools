# Camera & IMU Calibration App README

[简体中文](README.zh-CN.md) · [Project overview](../../../README.md) · [Phone capture](../capture/README.md)

One Linux app handles **Camera**, **stationary IMU analysis** and **Camera–IMU calibration**. Connect the headband directly to Linux, not through the phone app. The current local candidate is `20261115-PROCESS-WAIT`, with English as the default and a Chinese switch. It has passed all three existing-data calculation workflows on the reference workstation; it is not yet a public release.

The immediate goal is to demonstrate recording, calculation and result-file generation. Optional joint-result review stays collapsed. It is not a prerequisite for normal use.

## 1. Prepare and install

Use Ubuntu 22.04/24.04 desktop on x86_64, network access and sudo. Previous new-machine calculation evidence is from Ubuntu 22.04; 24.04 lacks equivalent complete hardware coverage. Allow at least 30 GiB initially, plus the recording/import space shown in the app. Disable sleep for long recordings.

Secure both cameras and the mainboard. Close other apps that own the device. Prepare a flat target for Camera and Camera–IMU; stationary IMU needs no target. Follow [Hardware Setup](../hardware/README.md) and [Target Printing](../calibration-targets/README.md). Measure your printed target: the A4 example is 25 mm / 7.5 mm; the full-size example is 88 mm / 26.4 mm.

1. Follow [Release Downloads](../releases/README.md) to obtain the complete ZIP and checksum. Confirm that the intended version is public; do not substitute a source ZIP or old installer.
2. Verify SHA-256 and extract into a fresh directory using the commands on that page.
3. Open a terminal in the directory containing `camera.run`, then run as your normal user:

```bash
bash camera.run
```

4. Enter the local sudo password when requested; invisible password entry is normal. System dependencies still need internet access. The complete package includes the Kalibr image.
5. Wait for file checks, dependency/USB-rule setup, image import or reuse, and Kalibr checks.
6. Reconnect the headband if USB permissions have changed. Log out and back in if group membership has not taken effect.
7. Open the application menu entry and confirm the displayed version and device state. Installation alone is not calibration.

For an update, finish current recording/calculation and exit the old launcher with Ctrl+C first. Existing data is retained; actual paths may follow a reused container mount.

<details><summary>Advanced: lightweight update with an existing environment</summary>

Download [install-calibration.sh](https://github.com/EgoOneLabs/Ego-Capture/blob/feat/english-default-code20/docs/downloads/install-calibration.sh), [headband-calibration.zip](https://github.com/EgoOneLabs/Ego-Capture/blob/feat/english-default-code20/docs/downloads/headband-calibration.zip) and its [checksum](https://github.com/EgoOneLabs/Ego-Capture/blob/feat/english-default-code20/docs/downloads/headband-calibration.zip.sha256) into one directory, then run `bash install-calibration.sh` there. This small package does not contain the image. On a new machine, it downloads verified historical environment parts and extracts only the image, without executing the old app. The checked-in snapshot contains PROCESS-WAIT, including bilingual UI and correct waiting for calculation subprocesses. Developers should use the [Development Guide](../guides/DEVELOPMENT.md).

</details>

## 2. Open, change language and exit

Search for **Headband Calibration Tool** in the application menu after installing the bilingual update. Older installations use **头环标定工具**. The stable launcher command is:

```bash
gio launch "$HOME/.local/share/applications/ego-camera-calibration.desktop"
```

Keep the launcher terminal open. The browser uses a local `127.0.0.1` address with a port that may change; do not bookmark an old port. Closing the browser does not delete data and may leave the task running. Exit with Ctrl+C in the launcher terminal.

The proposed bilingual page defaults to English, with a **中文 / English** switch. Switching must not reload the page or interrupt recording. Browser language preference is local to the page origin; a new launch port may start in English again. Original backend/third-party diagnostic logs are preserved and may be in Chinese. File names, user input, parameters and recorded data are never translated.

## 3. Choose your workflow

| Workflow | Action |
|---|---|
| Record now | Connect USB, enter settings, start beside the live preview, then finish or wait for automatic stop |
| Existing recording | Drop files/folders or browse locally; after import, start calculation |

Controls, progress and instructions sit beside the preview. During computation, the live log shows actual process output. A quiet log alone does not prove a stall. At completion, the page displays file links, the actual directory and **Open result folder**.

Recommended order: Camera → IMU → Camera–IMU. Camera and IMU can be done in either order. Joint motion may be recorded first; calculation is the point at which the two parameter files are required.

## 4. Camera: record and calculate

**Keep the headband fixed and move the target.** No IMU parameters are required.

1. Select **Camera: stereo calibration** and the recording workflow.
2. Enter the device ID, target rows/columns, measured black tag edge and white gap in **millimetres**.
3. Choose 60, 90 or 120 seconds. Confirm both cameras can see a clear target.
4. Start. Move the target slowly through the centre, edges and corners, varying distance, tilt and in-plane rotation.
5. Keep it visible to both cameras where possible. Avoid glare, bending and fast blurred motion. Not every image needs the entire board.
6. Wait for automatic stop or finish early after enough images. The 40-pair early-stop threshold is a program condition, not a quality threshold.
7. Wait for BAG preparation, readback checks and Kalibr DS stereo calculation. Open the results.

| Output | Purpose |
|---|---|
| `camera.bag` | Camera input data |
| `camera-camchain.yaml` | Camera intrinsics and stereo extrinsics; the **Camera input for step 3** |
| `camera-report-cam.pdf` | Calibration report |
| `camera-results-cam.txt` | Parameter/error summary |
| `aprilgrid.yaml` | Target geometry used for this run |
| Verification JSON, calculation JSON and logs | Input checks, status and timing |

Preview is color; saved calibration images may be full-resolution grayscale. No manual focal-length entry is required. An imported camera BAG uses its accompanying target configuration, or the measured values in the current form if none was supplied.

## 5. IMU: stationary recording and noise analysis

**Keep the complete headband stationary.** No target or Camera parameters are required. Data comes from the headband IMU.

1. Select **IMU: stationary noise analysis** and enter the device ID.
2. Put it on a stable surface with cable slack. Exact leveling is not required.
3. Start with the 60-second readout check. Inspect samples, errors, duplicates and gaps.
4. For long-term noise analysis, aim for at least **2–3 hours**. This is a recommendation, not an official Kalibr minimum or a hard software gate. Custom duration supports **1 minute to 24 hours**.
5. Start recording. There is **no warm-up countdown or discarded warm-up interval**. Do not touch the device, table or cable. Maintain power and disable sleep.
6. Wait for automatic analysis or stop early. Analysis uses continuous segments; it does not zero-fill gaps or concatenate away real elapsed time.
7. Review the Allan curves, per-axis results and output path.

| Output | Purpose |
|---|---|
| `imu_samples.csv` + `imu_capture.json` | Paired input for reanalysis |
| `imu_packets.bin`, `imu_requests.csv` | Raw packets and readout diagnostics |
| `imu-allan.csv`, `imu-report.pdf` | Allan data and report |
| `imu-analysis.json`, `imu-results.txt` | Analysis status and per-axis results |
| `imu-candidate.yaml` | Generated only when the current fitting conditions are met |
| `imu-experimental.yaml` | Explicitly generated experimental weights; not formal noise acceptance |

A term marked **Not identified** does not establish a faulty sensor. Retain the data and curves. Stationary noise analysis is not a complete scale-factor, axis, bias or temperature calibration.

### If step 3 needs an IMU YAML

- If `imu-candidate.yaml` exists, use it and review its report.
- To test the joint workflow with explicitly accepted experimental weights, after **live IMU analysis** click **Generate experimental mixed-model weights** beneath the per-axis table. Retain both `imu-experimental.yaml` and `imu-experimental-fit.json`.
- If fitting rejects the available time range or fails, there are no usable weights from that attempt. Do not rename reports to YAML, fill missing values with zeros or borrow another device's parameters.

The existing-data analysis page currently lacks the same generation button. The optional command below calls the installed fitting module without recording again.

<details><summary>Experimental fallback for an existing IMU analysis result</summary>

Copy the real result path from **Open result folder**. It must contain `imu-allan.csv` and `imu-analysis.json`. Reuse an existing experimental YAML rather than regenerating it.

```bash
# Linux computer. CHANGE ONLY RUN to the actual IMU analysis directory.
(
  set -euo pipefail
  RUN="/actual/path/to/IMU-analysis"
  /usr/bin/python3 - "$RUN" <<'PYCODE'
from pathlib import Path
import shlex
import subprocess
import sys

run = Path(sys.argv[1]).expanduser().resolve()
for name in ('imu-allan.csv', 'imu-analysis.json'):
    if not (run / name).is_file():
        raise SystemExit(f'Missing required analysis file: {run / name}')
entry = Path.home() / '.local/share/applications/ego-camera-calibration.desktop'
command = next(line[5:] for line in entry.read_text().splitlines()
               if line.startswith('Exec='))
root = Path(shlex.split(command)[1]).parent
module = root / 'imu_experimental.py'
if not module.is_file():
    raise SystemExit(f'Installed fitting module not found: {module}')
subprocess.run(['/usr/bin/python3', str(module), str(run)], check=True)
print('Generated:', run / 'imu-experimental.yaml')
PYCODE
  xdg-open "$RUN"
)
```

Insufficient data or an unsuccessful fit can still cause rejection. This is an experimental workflow, not a way to bypass noise-observation requirements.

</details>

## 6. Camera–IMU: record and calculate

**Keep the target fixed and move the entire rigid headband.** This estimates the camera–IMU relationship and time offset, using:

| Required for calculation | Where it comes from |
|---|---|
| Joint motion recording / BAG | This step's recording or an imported complete joint dataset |
| `camera-camchain.yaml` | Camera calculation in step 1; includes camera intrinsics/stereo geometry |
| `imu-candidate.yaml` or explicitly accepted `imu-experimental.yaml` | IMU analysis in step 2 |
| Target geometry | Measured form values or the recording's target configuration |

Drop the two **YAML parameter files** into the named boxes. PDF and TXT reports are not substitutes. Files must match the same device and fixed assembly. Parameters explicitly generated or selected for that device may be restored; check their names and provenance.

1. Select **Step 3 — Camera–IMU calibration**, the recording workflow, device ID, measured target geometry and duration.
2. Both files present: **Record and calculate** starts automatic calculation after capture. Files missing: **Start joint recording** still records and saves data.
3. Begin briefly at rest, then smoothly rotate about all three axes: yaw, pitch and roll. Add combined rotations and some translation with changing speed.
4. Keep the target visible in both cameras. Avoid shocks, violent shaking and blur.
5. Finish or wait for automatic stop. If parameters were missing, choose the existing-recording workflow, select this saved recording, add both YAML files and calculate. There is no need to record again just to add parameters.
6. Follow the live log, then save the result files and displayed paths.

Outputs normally include `joint-camchain-imucam.yaml`, `joint-report-imucam.pdf`, `joint-results-imucam.txt`, status/log files and a review archive. Older versions may use a `camera_imu-` prefix. Raw recording and calculation results can be in different directories; the page shows the actual locations.

## 7. Import existing recordings

| Module | Drop or select |
|---|---|
| Camera | One ROS1 camera `.bag`, optionally `aprilgrid.yaml`, or a single recording folder containing them |
| IMU | Both `imu_samples.csv` and `imu_capture.json`, or the complete stationary-recording folder; arbitrary IMU BAGs are not supported |
| Camera–IMU | A joint BAG or complete raw folder with images, manifests, CSV, clocks and metadata; also supply the two parameter YAML files |

Use drag-and-drop, **Browse local files** or **Browse recording folders**. Successful import selects the dataset automatically. The discovered-local-recordings list is an optional shortcut. Files are copied in chunks into local `imports/`; nothing is uploaded to the internet and originals are retained. Keep the page and terminal open. Import supports at most 20,000 files and 100 GiB per request; reserve space for copies and computation.

BAG topics are `/cam0/image_raw` and `/cam1/image_raw` (`sensor_msgs/Image`), plus `/imu0` (`sensor_msgs/Imu`, SI units) for joint input. The app checks structure and timing; it does not guess units, rename topics or repair backward timestamps automatically.

## 8. Results, optional review and troubleshooting

A workflow run is complete when calculation exits successfully and the expected files and paths appear. A saved recording without its result YAML is not a completed joint calculation. File generation does not establish final accuracy or hardware synchronization.

Keep the device ID, assembly state, versions, measured target dimensions, parameter provenance, reports and logs. New installations normally use `~/EgoStereoIMU/calibration_data/`; existing systems may reuse another Docker `/data` mount. **Use the actual path displayed in the app.**

Optional joint-result review is collapsed at the bottom of step 3. It holds joint extrinsics/time offsets fixed while fitting trajectory, gravity and IMU biases on another independent motion recording. It is neither recalibration nor fully open-loop validation, and is not required for normal recording/calculation.

| Symptom | First action |
|---|---|
| Joint record button disabled | Confirm RECORD-FIX or later. Live recording does not require YAMLs; existing-data calculation does require data and both YAMLs |
| Cannot finish early | Wait for at least 40 image pairs or the automatic end time |
| Missing imported files | Select the module's complete input set; a joint folder needs more than CSV and IMU input needs more than reports |
| Missing output YAML | Find the first real error in the calculation log; do not assume target dimensions caused it |
| No preview | Check cable, USB access and competing programs; reconnect without starting duplicate instances |
| Insufficient disk space | Back up before cleaning or changing disks; do not remove active inputs |
| Git / rosdep error | Use the current installer and retain the log; do not repeatedly reinstall everything |

See [Data Formats](../guides/DATA_FORMAT.md) and [Validation and Limits](../guides/VALIDATION.md).
