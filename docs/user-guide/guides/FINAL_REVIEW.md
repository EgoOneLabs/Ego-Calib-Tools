# Final Review & Release Readiness

[简体中文](FINAL_REVIEW.zh-CN.md) · [Project overview](../../../README.md)

Date: 2026-11-15. English-first documentation and app candidates are ready for local inspection. Both source PRs are open. Both software packages have been published as public pre-releases by Blue88ight, and unauthenticated download checks passed.

## Completed

- Code20 built on the configured Android workstation; 46 unit tests passed; APK hash, ABI and signing certificate checked. English phone use and a completed export are evidenced by screenshot/metadata.
- Camera reprocessing produced YAML/PDF/TXT in 78.90 seconds.
- Existing short IMU data produced Allan analysis and reports; missing random-walk terms remain explicit, with no fabricated complete YAML.
- Camera–IMU reprocessing produced joint YAML/PDF/TXT in 185.71 seconds using existing experimental IMU weights.
- Corrected premature completion: `setsid --wait` now waits for all three solver subprocesses; nine focused regression checks passed.
- Separate bilingual capture/calibration/hardware guides, original target pairs, output format/architecture documentation, and explicit input requirements are included.

## Findings requiring an explicit boundary

| Finding | Treatment |
|---|---|
| Debug-signed APK | Name it accordingly; production signing remains a maintainer decision. The certificate matches code19 |
| Fresh-machine installation not passed | Workstation upgrade/reuse passed; apt TLS/mirror issues remain documented, not hidden |
| Short IMU input | Analysis path passes; full noise YAML is not accepted or guaranteed |
| One older IMU counter input rejected | Preserve diagnosis data; do not claim arbitrary legacy compatibility |
| English fresh-default acceptance incomplete | Source default/static checks and English usage exist; complete fresh-install/persistence checks remain |
| Licensing and third-party image/target redistribution | Confirm before public publication; no license is invented by this change |
| GitHub delivery | PR #2 in Ego-Capture and PR #1 in Ego-Calib-Tools are open; both releases are public pre-releases |

## Remaining publication checks

1. Review both source PRs and the bilingual instructions.
2. Compare uploaded asset sizes and hashes with the workstation files.
3. Complete clean-machine and language-default checks when the required device/system is available.
4. Public release pages and download URLs have been verified without authentication; continue source PR review.
5. Retain private recordings on the workstation. Source approval and release publication are separate actions.

See [Validation](VALIDATION.md) for evidence and coverage limits.
