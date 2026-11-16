"""Bounded FFmpeg V4L2 capture. Camera disconnect cannot block the HTTP UI."""
import os
from pathlib import Path
import re
import select
import subprocess
import time
from core import WIDTH, HEIGHT, require


def find_device(requested=None):
    candidates = [Path(requested)] if requested else sorted(Path('/dev').glob('video*'))
    good = []
    for node in candidates:
        sys = (Path('/sys/class/video4linux') / node.name / 'device').resolve()
        parents = (sys, *sys.parents)
        matched = any((p / 'idVendor').is_file() and (p / 'idProduct').is_file() and
                      (p / 'idVendor').read_text().strip().lower() == '1bcf' and
                      (p / 'idProduct').read_text().strip().lower() == '0b15' for p in parents)
        if not matched:
            continue
        result = subprocess.run(['v4l2-ctl', '-d', str(node), '--list-formats-ext'],
                                capture_output=True, text=True, timeout=8)
        if result.returncode == 0 and "'MJPG'" in result.stdout and '3840x1080' in result.stdout:
            good.append(str(node))
    require(len(good) == 1, '未找到唯一的 2UQ2 视频设备。请直接接到 Linux、允许当前用户访问 video 设备，并只连接一套头环。')
    device = good[0]
    result = subprocess.run(['v4l2-ctl', '-d', device,
                             '--set-fmt-video=width=3840,height=1080,pixelformat=MJPG', '--get-fmt-video'],
                            capture_output=True, text=True, timeout=8)
    require(result.returncode == 0 and re.search(r'Width/Height\s*:\s*3840/1080', result.stdout)
            and re.search(r"Pixel Format\s*:\s*'MJPG'", result.stdout),
            '设备没有接受 MJPEG 3840×1080，停止，未采用低分辨率替代')
    return device, result.stdout


class Camera:
    def __init__(self, device, log):
        self.log = Path(log).open('wb')
        self.command = ['ffmpeg', '-hide_banner', '-nostdin', '-loglevel', 'warning',
                        '-xerror', '-err_detect', 'explode', '-f', 'v4l2',
                        '-input_format', 'mjpeg', '-video_size', f'{WIDTH}x{HEIGHT}',
                        '-framerate', '60', '-i', device, '-an',
                        '-vf', 'fps=10', '-pix_fmt', 'bgr24', '-f', 'rawvideo', 'pipe:1']
        self.process = subprocess.Popen(self.command, stdout=subprocess.PIPE, stderr=self.log, bufsize=0)
        os.set_blocking(self.process.stdout.fileno(), False)
        self.buffer = bytearray()

    def read(self, stop, timeout=8):
        deadline = time.monotonic() + timeout
        size = WIDTH * HEIGHT * 3
        fd = self.process.stdout.fileno()
        while len(self.buffer) < size:
            if stop.is_set():
                raise InterruptedError('停止预览')
            require(time.monotonic() < deadline, '连续 8 秒没有完整图像，请检查 USB 连接')
            ready, _, _ = select.select([fd], [], [], .2)
            if not ready:
                continue
            chunk = os.read(fd, min(1024 * 1024, size - len(self.buffer)))
            require(chunk, '视频流已结束，请检查 USB 连接；原始文件保留')
            self.buffer.extend(chunk)
        data = bytes(self.buffer[:size])
        del self.buffer[:size]
        return data

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill(); self.process.wait(timeout=3)
        self.process.stdout.close()
        self.log.close()
