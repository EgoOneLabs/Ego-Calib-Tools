# Runtime files and local inputs

| Category | Location / supply route |
|---|---|
| Media validation, BAG preparation/writer, Kalibr wrapper, importer and audit | Tracked Python sources in media/, workflow/, result_import/, quality/ |
| Known historical DS parameters and matching reports | Tracked reference/2uq2-ds-20261102/ YAML/PDF/TXT, original SHA256SUMS |
| AprilGrid example | Tracked configs/aprilgrid_6x6_88mm.yaml; measure the actual printed board |
| Host test dependencies | requirements-test.txt; use a disposable Python environment |
| Actual ROS/Kalibr/OpenCV | Existing documented Docker container and bind mount; not a bundled private local folder |
| Phone exports / raw recordings / original historical BAG | Explicit operator-selected input; retained on the workstation, not automatically published |
| Generated runs and output directories | Explicit --output-root; separate from source/reference files |
| SDK keys or credentials | Not inputs to the stereo scripts and must not be committed |

`python3 ego_stereo/verify_checkout.py` checks every distributed stereo Python,
requirements, example configuration and reference input against required_files.json.
It does not prove that the current container or hardware is installed or accepted.

The generic workflow writes its effective AprilGrid configuration from explicit
CLI dimensions, stores the hash and uses sibling Python modules that are tracked.
The old DELIVERY_NOTES documents describe historical workstation executions;
their author-specific paths are not installation dependencies.

Reference files are experimental evidence, not a quality approval or device
association. Neither these reports nor template files should be loaded into the
Android app as universal calibration. The repository-distribution change does
not alter the four-fisheye directories or Kalibr's official algorithms.
