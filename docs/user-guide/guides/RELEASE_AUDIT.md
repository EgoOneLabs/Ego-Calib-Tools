# Documentation and Release Audit — 2026-11-15

[简体中文](RELEASE_AUDIT.zh-CN.md)

## Corrections

- Replaced the unavailable suite download and install-linux.sh workflow with the actual camera.zip, checksum and camera.run installation flow.
- Updated source submission status to open PRs and software status to draft release assets. Draft version URLs can return 404 until publication.
- Added complete local English and Chinese user guides to Ego-Calib-Tools. Users can reach hardware, target printing, installation, recording/import, required YAMLs, logs and output paths from either repository.
- Corrected developer checkout instructions to the code20 review branch, and added Linux calibration results to the separate output directory reference.
- Marked historical documents and checked filenames against the capture/export and calibration implementations.

## Installer mismatch found

The workstation built its uploaded complete ZIP from the BILINGUAL installer with SHA-256 c7f2437a83d868c3012c2312686a7e043595171d3c11e6dd02cc208560803ddf. Comparing its application files with calibration PR #1 revealed five differences. The old installer lacked setsid --wait in three solver paths. The PR source includes the fix. Replace the Linux draft attachment using an installer built from that fixed source before publication. This documentation review does not establish that the old draft attachment has already been replaced.

## Checks performed

- Markdown relative links across both repositories resolve after corrections, including target files and image references.
- Bash examples pass bash -n. JSON manifests parse. These syntax checks do not execute installation, USB or sudo commands.
- All four target PDF/YAML files match the supplied original ZIP byte for byte. Existing target-verification records describe page dimensions and tag checks.
- Existing process-wait regression passed for successful and failing detached children. Existing localization tests passed for English defaults, saved Chinese, switching and UI text coverage.
- The repaired installer application files are compared with repository source and its internal check is run when packaging. Device behavior still relies on the recorded workstation functional evidence.
- External Markdown URLs were requested without GitHub authentication. Expected draft-release 404s are recorded separately from broken public links. Public asset downloads and checksums require another check after publication.

## Remaining checks

Replace and verify the Linux draft asset, submit these documentation corrections to the two existing PR branches under Blue88ight, and review the changes. Fresh-machine installation of the final installer, full device language-persistence acceptance, production signing and calibration accuracy acceptance remain pending. The short IMU run generated reports without a complete noise YAML; joint functional testing used experimental noise weights. Keep private recordings, temporary test logs and build outputs on the workstation.

## Publication check completed

Both releases are public pre-releases authored by Blue88ight. All seven release-page/asset URLs returned HTTP 200 without authentication. The downloaded APK and its checksum agree. The public Linux checksum agrees with GitHub’s asset digest. The old Linux draft was replaced with the fixed complete package, size 1,806,624,824 bytes. Public Linux SHA-256: `2dac03ce782d2882784e3a9e704ef4c63707fcabb4ac17d54f4439870360046c`. The full Linux ZIP was not downloaded again during this public-access check. Source PRs remain under review.
