# Data Formats & Timestamp Semantics

[简体中文](DATA_FORMAT.zh-CN.md) · [Project overview](../../../README.md)

This contract describes Android code20 and Linux PROCESS-WAIT. Language changes do not change recorded fields. The two applications use different capture/time contracts; renaming files does not make them interchangeable.

## 1. Android raw Episode

Root: `files/episodes/episode_<date-time>/` in the app's external-files directory.

| Relative path | Content |
|---|---|
| `video.mjpg` | Concatenated original stereo MJPEG bytes |
| `video_index.csv` | Frame offsets, lengths, saved indices and host/native callback timing |
| `imu_packets.bin` | Raw UVC XU packets, 252 bytes per read |
| `imu_samples.csv` | Raw axes with packet/request associations |
| `imu_attempts.csv` and diagnostics | Read failures and scheduling evidence; exact files depend on version |
| `metadata.json`, `quality.json` | Version, settings, counts and timing semantics |
| `audio.wav`, `audio_metadata.json`, `audio_index.csv` | Audio and routing/timing records; validity comes from metadata |

Each XU packet contains 14 samples of 18 bytes: `DE C8` magic, a big-endian counter and six signed 16-bit axes. The raw counter is not directly a Unix or confirmed hardware sampling timestamp.

## 2. Android exported session

Root: `files/data/<task>/<device>_session_<local-date-time>/`. Export starts in a `.partial` directory and becomes final after completion. Existing final directories are not silently overwritten.

| Relative path | Format / meaning |
|---|---|
| `videos/left.mkv`, `videos/right.mkv` | MJPEG in Matroska, 1920×1080 per eye; not resized/re-encoded preview |
| `timestamps/left_timestamps.txt`, `right_timestamps.txt` | Exported frame index and Unix seconds with nine decimal digits; both eyes originate from one stereo image |
| `imu/imu0.csv` | Nominal SI data, columns below |
| `imu/imu_raw_counts.csv` | Raw counts and packet-level associations |
| `audio/audio.wav` | Exported only for a checked route, nonempty PCM and complete container |
| Audio metadata/index | Actual route, availability and timing |
| `meta.json` | Session, source, frame/sample counts, export/data status and time sources |
| `export_video_index.csv`, `export_skipped_frames.csv` | Export mapping and damaged-frame skips |
| `calibrations/` | Copy of a pre-existing parameter directory; no automatic matching/acceptance |

Timestamp syntax example:

```text
0 1790000000.123456789
1 1790000000.156790122
```

MKV timecode precision is currently 1 ms. Nine decimal digits in text do not establish nanosecond sensor accuracy.

IMU CSV header:

```text
timestamp,orientation_x,orientation_y,orientation_z,orientation_w,angular_velocity_x,angular_velocity_y,angular_velocity_z,linear_acceleration_x,linear_acceleration_y,linear_acceleration_z
```

| Field | Units / rule |
|---|---|
| `timestamp` | Host USB-request midpoint mapped to Unix seconds; 14 samples share one packet time |
| `orientation_*` | Four zeros indicate unavailable attitude; not a valid estimated quaternion |
| `angular_velocity_*` | rad/s: raw / 16.4 × π / 180 |
| `linear_acceleration_*` | m/s²: raw / 4096 × 9.80665; stationary gravity response retained |
| Axes | Original XYZ, without automatic camera-frame conversion or per-device scale/bias correction |

Video uses native `CLOCK_BOOTTIME` callback time anchored to Unix at recording start, not exposure time. IMU time is host request timing, not individual hardware sample timing. Audio timing likewise does not establish exposure/ADC synchronization.

Flags such as `data_status=INCOMPLETE` and `ready_for_kalibr_camera_imu=false` describe semantic limits. Distinguish completed file export from readiness for synchronized calibration using `export_status`, actual files, counts and diagnostics.

## 3. Linux Camera

Typical root: `<data-root>/camera_easy/<device>/<recording>/`.

| File | Purpose |
|---|---|
| `images/cam0/`, `images/cam1/` | Full-resolution grayscale images, separate from color preview |
| `camera_manifest.json` | Selected images, times and checks |
| `camera.bag` | `/cam0/image_raw`, `/cam1/image_raw`; no IMU |
| `aprilgrid.yaml` | Rows/columns, edge in metres and spacing ratio |
| `camera-camchain.yaml` | DS parameters and stereo extrinsics |
| PDF/TXT, calculation JSON and logs | Reports/status/timing, not automatic accuracy acceptance |

Locally generated BAGs can be read back against original images. External BAG structure/timing checks do not establish pixel identity with unavailable original images.

## 4. Linux stationary IMU

Typical root: `<data-root>/imu/<device>/<recording>/`. CSV header:

```text
segment,tick_index,counter_raw,packet,host_before_ns,host_after_ns,ax_raw,ay_raw,az_raw,gx_raw,gy_raw,gz_raw,ax_m_s2,ay_m_s2,az_m_s2,gx_rad_s,gy_rad_s,gz_rad_s
```

| Field | Meaning |
|---|---|
| `segment` | Continuous-segment ID; gaps/jumps are not disguised as continuity |
| `tick_index` | Parsed relative sample position retaining identifiable gaps; not direct hardware time |
| `counter_raw`, `packet` | Original counter and read-packet association |
| `host_before_ns`, `host_after_ns` | Monotonic host request start/end in nanoseconds |
| `*_raw` | Original axis counts |
| `*_m_s2`, `*_rad_s` | Nominal SI axes |

`imu_capture.json` retains status, duration, samples, errors, duplicates, gaps, unidentified jumps and scale assumptions. Reanalysis needs it alongside the CSV. Allan analysis does not interpolate across gaps. Candidate YAML generation is conditional; experimental weights are labeled separately. Linux counter-wrap handling does not imply identical Android parsing.

## 5. Linux joint data

Typical root: `<data-root>/camera_imu/<device>/camera_imu_<time-id>/`.

| File | Purpose |
|---|---|
| Camera manifest and `images/` | Images and host frame-completion timing |
| `imu_samples.csv`, `imu_capture.json` | IMU from the same motion recording |
| `joint_clock.json` | Host-clock anchors/time sources |
| `joint_dependencies.json` | Present and missing parameters |
| `input-camera.yaml`, `input-imu.yaml` | Supplied calculation-input copies |
| Joint BAG | Images and `/imu0` for optimization |
| `joint-camchain-imucam.yaml` and reports | Joint result; older prefixes can differ |

Recording can precede parameter import. Calculation requires camera parameters, IMU noise parameters and target geometry. Estimated time offsets do not prove hardware synchronization.

Imported files are copied into `<root>/imports/<module>/<random-directory>/`; originals are retained and recomputation creates a new result directory. Never repair a contract by renaming data, removing elapsed gaps, zero-filling or borrowing another device's parameters.

## 6. Handoff

Retain device ID, assembly state, software versions, measured geometry and input provenance. If large media/BAG/images are stored separately, record their paths and SHA-256 hashes. A small review archive does not replace original-data backup.
