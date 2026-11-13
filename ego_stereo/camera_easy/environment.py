"""Reuse an installed Kalibr container or import a published environment archive."""
import json
import os
from pathlib import Path
import shutil
import subprocess
from core import require

ROS_ENV = '''set -eo pipefail
source /opt/ros/noetic/setup.bash
source /catkin_ws/devel/setup.bash
export MPLBACKEND=Agg PYTHONUNBUFFERED=1
unset DISPLAY KALIBR_MANUAL_FOCAL_LENGTH_INIT
export HOME=/tmp/ego_camera_home MPLCONFIGDIR=/tmp/ego_camera_mpl
mkdir -p "$HOME" "$MPLCONFIGDIR"
'''

class Docker:
    def __init__(self, sudo=False):
        self.prefix = ['sudo', '-n', 'docker'] if sudo else ['docker']

    def run(self, *args, timeout=90):
        result = subprocess.run(self.prefix + list(args), capture_output=True, text=True, timeout=timeout)
        require(result.returncode == 0, 'Docker 操作失败：' + (result.stderr or result.stdout)[-1200:])
        return result.stdout

    def exists(self, *args):
        return subprocess.run(self.prefix + list(args), stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=15).returncode == 0

    def prepare(self, container=None, image='kalibr:noetic', archive=None):
        self.run('info', '--format', '{{.OSType}}')
        if not container:
            container = 'kalibr' if self.exists('container', 'inspect', 'kalibr') else 'ego-camera-kalibr'
        if not self.exists('container', 'inspect', container):
            if not self.exists('image', 'inspect', image):
                require(archive and Path(archive).is_file(), '找不到 Kalibr 镜像。首次部署请运行 install.sh，选择 kalibr-environment.tar.gz；不能只安装 Docker 就开始标定。')
                output = self.run('load', '-i', str(Path(archive).resolve()), timeout=1800)
                if not self.exists('image', 'inspect', image):
                    loaded = [s.split(': ', 1)[1].strip() for s in output.splitlines() if s.startswith(('Loaded image: ', 'Loaded image ID: '))]
                    require(len(loaded) == 1, '镜像导入完成，但标签不唯一，请用 --image 指定已导入的 Kalibr 镜像')
                    image = loaded[0]
            root = Path.home() / 'EgoStereoIMU' / 'calibration_data'
            root.mkdir(parents=True, exist_ok=True)
            # Image ENTRYPOINT may launch a non-interactive bash and ignore CMD.
            # Run a persistent process directly, regardless of image defaults.
            self.run('create', '--name', container, '--entrypoint', '/bin/sleep',
                     '--user', f'{os.getuid()}:{os.getgid()}',
                     '--mount', f'type=bind,src={root.resolve()},dst=/data', image, 'infinity')
        info = json.loads(self.run('inspect', container))[0]
        if not info['State']['Running']:
            self.run('start', container)
            info = json.loads(self.run('inspect', container))[0]
        require(info['State']['Running'],
                'Kalibr 容器启动后立即退出：' + container +
                '。请检查镜像 ENTRYPOINT 与容器日志；新建容器需要 --entrypoint /bin/sleep。')
        mounts = [m for m in info.get('Mounts', []) if m.get('Type') == 'bind' and m.get('RW') and m['Destination'] == '/data']
        require(len(mounts) == 1, 'Kalibr 容器必须有可写的宿主数据目录 → /data 挂载')
        root = Path(mounts[0]['Source']).resolve()
        require(root.is_dir() and os.access(root, os.W_OK), '当前 Linux 用户无法写入容器 /data 对应目录：' + str(root))
        shell = ROS_ENV + '''
python3 -c 'import rosbag, rospy, sensor_msgs.msg, numpy'
rosrun kalibr kalibr_calibrate_cameras --help >/dev/null
'''
        self.run('exec', container, 'bash', '-c', shell, timeout=120)
        return container, root, info

    def kill_group(self, container, inner):
        # Stop only the process group named by this run, never a whole container.
        shell = '''p="$1/.kalibr.pid"; if test -f "$p"; then read -r n < "$p"; case "$n" in (*[!0-9]*|'') exit 1;; esac; kill -TERM -- "-$n" 2>/dev/null || true; fi'''
        try:
            self.run('exec', container, 'bash', '-c', shell, '_', inner, timeout=8)
        except Exception:
            pass
