# Validation & Limitations

[简体中文](VALIDATION.zh-CN.md) · [Project overview](../../../README.md)

Updated 2026-11-15. The current goal is functional workflow verification. A completed calculation is distinct from final calibration quality acceptance. No additional two-hour IMU recording is required to repeat these software checks.

| Area | Current evidence | Boundary |
|---|---|---|
| Android build | code20, 0.3.9-english-default; 46 JUnit tests passed, no failures/errors/skips; APK signature and arm64 ABI checked | Debug-signed candidate, not a production release |
| Phone run | English interface and stereo preview; metadata records 35.43 s, 1,048 stereo pairs, 29.58 FPS, video export COMPLETE | This session metadata was inspected; its media were not independently decoded in this review; not a sustained-30-FPS guarantee |
| Phone IMU/audio | 26,292 IMU samples written; metadata reports completed 48 kHz stereo PCM16 audio export | Counter-gap estimate remains unresolved; packet host timestamps, nominal scales and zero orientation placeholders remain |
| Camera | Existing BAG import, DS calibration, YAML/PDF/TXT output; real 78.90 s | Successful reprocessing; live automatic calculation was not separately repeated after the process fix |
| Stationary IMU | Existing CSV + capture JSON import; 48,440 samples; Allan CSV, analysis JSON, PDF and TXT generated | Short input: longest usable segment 42.53 s; NEEDS_REVIEW, no complete noise candidate YAML |
| Camera–IMU | Existing BAG plus Camera and experimental IMU YAMLs; joint YAML/PDF/TXT produced; real 185.71 s | Functional optimization path, not independently accepted noise parameters, hardware synchronization or final accuracy |
| Subprocess fix | All three solver launch paths use `setsid --wait`; nine focused regression tests passed | Correctly waits for and propagates the solver exit code; solver algorithms unchanged |
| Linux installation | Updated on the reference workstation using its existing Kalibr container/image | apt mirror TLS errors occurred; dependencies already existed. This is not a clean-machine installation pass |

## Timing, noise and legacy inputs

Camera times are host frame-completion times, not verified exposure times. Android groups 14 IMU samples under a packet-level host timestamp. Linux counter/host mapping is experimental. Nominal 4096 count/g and 16.4 count/(degree/s) are not per-device scale/axis/bias calibration. Orientation zeros are placeholders.

White-noise/random-walk candidate selection is an application heuristic, not an official universal two-hour Kalibr minimum. Two to three hours is a recommendation for observing longer noise timescales; custom duration starts immediately with no warm-up. A complete YAML is conditional on adequate evidence. Experimental mixed-model weights are explicitly labeled and must not be relabeled as accepted sensor parameters.

One older two-hour CSV/JSON input was rejected because its counter discontinuities were unresolved. The shorter previously analyzed input completed successfully. Arbitrary legacy CSV/BAG compatibility is not established; preserve original packets/request logs for diagnosis. Do not suppress the guard or fabricate missing noise terms merely to obtain a YAML.

## Assembly and UI

Re-taping a mainboard changes its pose relative to cameras. Old/new extrinsic differences alone do not prove a software defect; during each joint recording the assembly must remain rigid. Reuse parameters only for the applicable device and assembly.

Both apps default to English when no preference is saved and preserve explicit saved choices. Phone screenshots show English usage, not a fresh-install reset test. Linux browser-origin storage may vary with the local port. UI/catalog checks do not establish that every raw backend diagnostic is translated.

Remaining coverage: clean Ubuntu 22.04 installation of the final package, equivalent Ubuntu 24.04 hardware coverage, fresh-default/language persistence acceptance on both apps, and general disconnect/background/long-duration reliability. These are documented limits, not reasons to repeat two-hour recording for functional verification.

## Reporting an issue

Provide version, device/OS, action, visible error and output path. Send the small review archive/log first; retain large original data privately. Expected files and displayed paths establish workflow completion, not calibration quality acceptance. Independent joint-result review remains optional and collapsed by default.
