#!/usr/bin/env python3
"""Workstation entry point: paired frames -> ROS1 BAG -> unmodified Kalibr."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import uuid
from prepare_camera import prepare
from check_session import require, sha


def capture(argv):
    return subprocess.run(argv, check=True, text=True, stdout=subprocess.PIPE).stdout


def container_info(name):
    require(shutil.which('docker'), 'Missing docker')
    info = json.loads(capture(['docker', 'inspect', name]))[0]
    if not info['State']['Running']:
        subprocess.run(['docker', 'start', name], check=True)
    return info


def inner_path(path, info):
    candidates = []
    path = path.resolve()
    for mount in info.get('Mounts', []):
        if mount.get('Type') != 'bind' or not mount.get('RW'):
            continue
        source = Path(mount['Source']).resolve()
        try:
            relative = path.relative_to(source)
        except ValueError:
            continue
        candidates.append((len(source.parts), str(Path(mount['Destination']) / relative)))
    require(candidates, 'Output must be under a writable container bind mount (normally /home/key/文档/kalibr/data -> /data)')
    return max(candidates)[1]


def build_bag(root, container, info):
    inner = inner_path(root, info)
    script = '/tmp/ego_camera_bag_' + uuid.uuid4().hex + '.py'
    subprocess.run(['docker', 'cp', str(Path(__file__).with_name('bag_writer.py')), container + ':' + script], check=True)
    shell = 'set -e\nsource /opt/ros/noetic/setup.bash\nexec python3 "$1" --root "$2" --backend rosbag\n'
    try:
        with (root / 'bag_write.log').open('w') as log:
            p = subprocess.Popen(['docker', 'exec', container, 'bash', '-c', shell, '_', script, inner],
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in p.stdout:
                print(line, end='', flush=True)
                log.write(line)
            require(p.wait() == 0, 'Container BAG build/readback failed; inspect bag_write.log')
    finally:
        subprocess.run(['docker', 'exec', container, 'rm', '-f', '--', script], check=False)
    report = json.loads((root / 'bag_verification.json').read_text())
    require(report.get('status') == 'CAMERA_BAG_READBACK_PASS', 'BAG verification failed')


def review_archive(root):
    # Small reports/configuration only. No images or BAG duplication.
    name = root / 'camera_workflow_small_review.tar.gz'
    with tarfile.open(name, 'w:gz') as archive:
        for file in sorted(root.iterdir()):
            if file.is_file() and file.suffix in ('.json', '.log', '.txt', '.yaml', '.pdf', '.sh'):
                archive.add(file, arcname=file.name)
    print('\n请上传：' + str(name), flush=True)
    return name


def calibrate(root, container, info, model, tag_size, tag_spacing, cols, rows, confirmed):
    require(confirmed, 'Confirm physical target dimensions and calibration-image coverage with --confirm-calibration-inputs')
    require(0 < tag_size < 1 and 0 < tag_spacing < 2 and 2 <= cols <= 30 and 2 <= rows <= 30, 'Invalid AprilGrid parameters')
    m = json.loads((root / 'camera_manifest.json').read_text())
    require(m.get('purpose') == 'calibration', 'Smoke dataset cannot be sent to Kalibr; prepare actual target images with --purpose calibration')
    require(m.get('status') == 'CAMERA_FRAMES_PREPARED', 'Preparation incomplete')
    verified = json.loads((root / 'bag_verification.json').read_text())
    require(verified.get('status') == 'CAMERA_BAG_READBACK_PASS' and verified['bag_sha256'] == sha(root / 'camera.bag'), 'BAG changed since verification')
    require(verified['manifest_sha256'] == sha(root / 'camera_manifest.json'), 'Manifest changed since verification')
    require(not (root / 'kalibr_run.json').exists(), 'Calibration already attempted here; use a new prepared run')
    inner = inner_path(root, info)
    target = root / 'aprilgrid.yaml'
    target.write_text('target_type: aprilgrid\ntagCols: %d\ntagRows: %d\ntagSize: %.12g\ntagSpacing: %.12g\n' % (cols, rows, tag_size, tag_spacing))
    command = '''set -eo pipefail
source /opt/ros/noetic/setup.bash
source /catkin_ws/devel/setup.bash
export MPLBACKEND=Agg
export PYTHONUNBUFFERED=1
unset DISPLAY
umask 022
cd "$1"
git -C /catkin_ws/src/kalibr rev-parse HEAD > kalibr_source_commit.txt
git -C /catkin_ws/src/kalibr status --porcelain > kalibr_source_status.txt
git -C /catkin_ws/src/kalibr diff --quiet
git -C /catkin_ws/src/kalibr diff --cached --quiet
rosbag info camera.bag > bag_info.txt
set +e
{ time -p rosrun kalibr kalibr_calibrate_cameras --bag "$1/camera.bag" --target "$1/aprilgrid.yaml" --topics /cam0/image_raw /cam1/image_raw --models "$2" "$2" --dont-show-report; } 2> kalibr_stderr_and_timing.log
rc=$?
printf '%s\\n' "$rc" > kalibr_exit_code.txt
exit "$rc"
'''
    (root / 'kalibr_command.sh').write_text(command)
    status = {'status': 'RUNNING', 'calibration_quality_accepted': False, 'container': container,
              'container_image_id': info.get('Image'), 'models': [model, model],
              'input_bag_sha256': verified['bag_sha256'], 'target_sha256': sha(target),
              'physical_target_and_image_coverage_confirmed_by_operator': True,
              'official_algorithm_modified_by_this_tool': False,
              'tracked_kalibr_source_changes_allowed': False}
    (root / 'kalibr_run.json').write_text(json.dumps(status, ensure_ascii=False, indent=2))
    print('开始官方 Kalibr 相机标定；输出到：' + str(root), flush=True)
    try:
        with (root / 'kalibr_run.log').open('w') as log:
            p = subprocess.Popen(['docker', 'exec', container, 'bash', '-c', command, '_', inner, model],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in p.stdout:
                print(line, end='', flush=True)
                log.write(line)
                log.flush()
            code = p.wait()
        outputs = {name: (root / name).is_file() and (root / name).stat().st_size > 0 for name in
                   ('camera-camchain.yaml', 'camera-results-cam.txt', 'camera-report-cam.pdf')}
        status.update(status='OUTPUTS_COMPLETE_REVIEW_PENDING' if code == 0 and all(outputs.values()) else 'FAILED_OR_INCOMPLETE',
                      exit_code=code, expected_outputs=outputs)
        # time -p lines are retained verbatim; no time conversion or speedup claim.
        timing = root / 'kalibr_stderr_and_timing.log'
        if timing.exists():
            import re
            values = re.findall(r'^(real|user|sys)\s+([0-9.]+)\s*$', timing.read_text(), re.M)
            status['timing_seconds'] = {key: float(value) for key, value in values}
    except BaseException as e:
        status.update(status='FAILED_OR_INTERRUPTED', error=str(e))
        raise
    finally:
        (root / 'kalibr_run.json').write_text(json.dumps(status, ensure_ascii=False, indent=2) + '\n')
        review_archive(root)
    require(status['status'] == 'OUTPUTS_COMPLETE_REVIEW_PENDING', 'Kalibr failed or outputs incomplete; preserve logs. No automatic focal/model substitution.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='action', required=True)
    prepare_parser = sub.add_parser('prepare', help='Prepare paired images and build/read back camera-only BAG')
    prepare_parser.add_argument('--session', type=Path, required=True)
    prepare_parser.add_argument('--media-report', type=Path, required=True)
    prepare_parser.add_argument('--output-root', type=Path, default=Path('/home/key/文档/kalibr/data/2uq2_camera'))
    prepare_parser.add_argument('--purpose', choices=['smoke', 'calibration'], required=True)
    prepare_parser.add_argument('--sample-hz', type=float, default=4.0)
    prepare_parser.add_argument('--container', default='kalibr')
    cal = sub.add_parser('calibrate', help='Run official Kalibr on actual target data; never smoke input')
    cal.add_argument('--root', type=Path, required=True)
    cal.add_argument('--container', default='kalibr')
    cal.add_argument('--model', choices=['ds-none', 'pinhole-equi', 'pinhole-radtan'], default='ds-none')
    cal.add_argument('--tag-size-m', type=float, required=True)
    cal.add_argument('--tag-spacing', type=float, required=True)
    cal.add_argument('--cols', type=int, default=6)
    cal.add_argument('--rows', type=int, default=6)
    cal.add_argument('--confirm-calibration-inputs', action='store_true')
    a = p.parse_args()
    info = container_info(a.container)
    if a.action == 'prepare':
        inner_path(a.output_root, info)  # Check mount before expensive decoding.
        root = prepare(a.session, a.media_report, a.output_root, a.purpose, a.sample_hz)
        try:
            build_bag(root, a.container, info)
        finally:
            review_archive(root)
    else:
        calibrate(a.root.resolve(), a.container, info, a.model, a.tag_size_m, a.tag_spacing,
                  a.cols, a.rows, a.confirm_calibration_inputs)


if __name__ == '__main__':
    os.umask(0o022)
    try:
        main()
    except Exception as e:
        sys.exit(str(e))
