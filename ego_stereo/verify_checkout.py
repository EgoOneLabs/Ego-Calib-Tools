#!/usr/bin/env python3
"""Verify repository-distributed stereo runtime inputs; no ROS execution."""
import hashlib
import json
from pathlib import Path
import sys


def verify(root):
    root = Path(root).resolve()
    manifest = json.loads((root / 'required_files.json').read_text())
    errors = []
    for name, expected in manifest['files'].items():
        path = (root / name).resolve()
        if root not in path.parents or not path.is_file():
            errors.append('Missing/unsafe input: ' + name)
        elif hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            errors.append('Input checksum mismatch: ' + name)
    if errors:
        raise ValueError('\n'.join(errors))
    return {'status': 'REPOSITORY_STEREO_INPUTS_VERIFIED',
            'files': len(manifest['files']), 'ros_kalibr_executed': False,
            'recordings_included': False, 'calibration_quality_accepted': False}


if __name__ == '__main__':
    try:
        print(json.dumps(verify(Path(__file__).resolve().parent), indent=2))
    except Exception as exc:
        sys.exit(str(exc))
