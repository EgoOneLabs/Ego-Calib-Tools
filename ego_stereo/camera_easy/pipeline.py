"""Camera-only BAG readback and official Kalibr invocation."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import time
from core import inspect_outputs, require, sha
from environment import ROS_ENV


def review(root):
    dest = root / 'camera_easy_small_review.tar.gz'
    with tarfile.open(dest, 'w:gz') as archive:
        for path in sorted(root.iterdir()):
            if path.is_file() and path != dest and path.suffix in ('.json', '.yaml', '.pdf', '.txt', '.log', '.sh', '.patch'):
                archive.add(path, arcname=path.name)
    return dest


def logged_run(command, root, filename, stop, notify):
    (root / (filename + '.command.json')).write_text(json.dumps(command, indent=2))
    with (root / filename).open('w') as log:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        import threading
        def pump():
            for line in process.stdout:
                log.write(line); log.flush(); notify(line.rstrip())
        reader = threading.Thread(target=pump, daemon=True); reader.start()
        try:
            while process.poll() is None:
                if stop.wait(.2):
                    process.terminate()
                    raise InterruptedError('工具已停止；采集文件保留')
            reader.join(timeout=5)
            require(not reader.is_alive(), '计算日志管道未正常结束')
            require(process.returncode == 0, f'{filename} 执行失败，请查看本次日志')
        finally:
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=3)
                except subprocess.TimeoutExpired: process.kill(); process.wait()
            reader.join(timeout=5)
            process.stdout.close()


def calculate(root, docker, container, data_root, info, stop, update, notify):
    inner = '/data/' + root.relative_to(data_root).as_posix()
    status = dict(status='BUILDING_BAG', image_id=info['Image'], model=['ds-none', 'ds-none'],
                  kalibr_algorithm_modified_by_this_tool=False, calibration_quality_accepted=False)
    started = time.monotonic()
    try:
        script = Path(__file__).with_name('bag_writer.py')
        shutil.copy2(script, root / 'bag_writer.py')
        update('BAG', '正在生成相机 BAG 并逐帧读回核对像素和时间记录…')
        logged_run(docker.prefix + ['exec', container, 'bash', '-c',
                   ROS_ENV + 'exec python3 "$1/bag_writer.py" --root "$1" --backend rosbag\n', '_', inner],
                   root, 'bag_write.log', stop, notify)
        verified = json.loads((root / 'bag_verification.json').read_text())
        require(verified['status'] == 'CAMERA_BAG_READBACK_PASS' and
                verified['bag_sha256'] == sha(root / 'camera.bag') and
                verified['manifest_sha256'] == sha(root / 'camera_manifest.json'), 'BAG 核对未通过')
        status['bag_sha256'] = verified['bag_sha256']
        status['target_sha256'] = sha(root / 'aprilgrid.yaml')
        update('CALIBRATING', '正在计算左右相机参数，请等待；取景预览已暂停。')
        shell = ROS_ENV + '''
umask 022
cd "$1"
echo "$$" > .kalibr.pid
git -c safe.directory=/catkin_ws/src/kalibr -C /catkin_ws/src/kalibr rev-parse HEAD > kalibr_source_commit.txt
git -c safe.directory=/catkin_ws/src/kalibr -C /catkin_ws/src/kalibr status --porcelain > kalibr_source_status.txt
git -c safe.directory=/catkin_ws/src/kalibr -C /catkin_ws/src/kalibr diff > kalibr_source_changes.patch
rosbag info camera.bag > bag_info.txt
{ time -p rosrun kalibr kalibr_calibrate_cameras --bag "$1/camera.bag" --target "$1/aprilgrid.yaml" --topics /cam0/image_raw /cam1/image_raw --models ds-none ds-none --dont-show-report; } 2>&1
'''
        (root / 'kalibr_command.sh').write_text(shell)
        # A unique session lets shutdown address only this calibration's subprocesses.
        logged_run(docker.prefix + ['exec', container, 'setsid', 'bash', '-c', shell, '_', inner],
                   root, 'calibration.log', stop, notify)
        status.update(inspect_outputs(root))
        timing = re.findall(r'^(real|user|sys)\s+([0-9.]+)\s*$', (root / 'calibration.log').read_text(), re.M)
        status['timing_seconds'] = {key: float(value) for key, value in timing}
        return status
    except BaseException as error:
        status.update(status='FAILED_OR_INTERRUPTED', error=str(error))
        raise
    finally:
        if stop.is_set():
            docker.kill_group(container, inner)
        status['total_calculation_wall_seconds'] = time.monotonic() - started
        (root / 'calculation.json').write_text(json.dumps(status, ensure_ascii=False, indent=2) + '\n')
        review(root)
