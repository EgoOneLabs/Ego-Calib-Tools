# Historical reference files

`2uq2-ds-20261102/` includes the exact DS YAML, matching numeric PDF/TXT report,
and SHA-256 checksums required by the historical importer and fixed-parameter
audit. These files were recovered from the previously verified result archive;
the three identities match the recorded digests. No calibration was rerun.

These are experimental parameters for the original rig, not universal defaults
for another headband. They are not activated in the Android app, and their
presence does not establish production quality, device identity binding,
physical board dimensions, IMU calibration or exposure synchronization.

The original `camera_4hz.bag` is a separate recording input (~910 MB), not an
application runtime dependency. It contains a real workplace scene and is not
published by this change. For historical reproduction supply its local path
explicitly with `--bag`; the existing SHA guard is retained. There is no claimed
public download URL. New sessions use the generic workflow with their own
explicit inputs. The synthetic integration tests need no real recordings.

The board example is tracked at `../configs/aprilgrid_6x6_88mm.yaml`. The generic
workflow generates the effective target file from explicit CLI dimensions and
records its hash; it does not load a hidden workstation YAML.
