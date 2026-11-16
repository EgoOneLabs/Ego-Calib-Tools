"""Short polling comparison; diagnostic only, never a noise calibration."""
import json
import shutil
import subprocess
import tarfile
import tempfile
import threading
from pathlib import Path
from hardware import Camera, find_device
from imu_capture import capture


class VideoStream:
    """Keep the normal UVC stream alive; release it on every exit path."""
    def __init__(self, device, log, factory=Camera):
        self.camera = factory(device, log)
        self.stop = threading.Event()
        self.error = None
        self.thread = None
        self.frames = 0

    def __enter__(self):
        try:
            self.camera.read(self.stop)
            self.frames = 1
            self.thread = threading.Thread(target=self.drain, daemon=True)
            self.thread.start()
            return self
        except BaseException:
            self.camera.close()
            raise

    def drain(self):
        try:
            while not self.stop.is_set():
                self.camera.read(self.stop)
                self.frames += 1
        except Exception as exc:
            if not self.stop.is_set():
                self.error = str(exc)

    def check(self):
        if self.error is not None:
            raise ValueError('视频流已中断：'+self.error)

    def __exit__(self, *exc):
        self.stop.set()
        if self.thread is not None:
            self.thread.join(timeout=2)
        self.camera.close()


def summarize(stats):
    total = stats['samples'] + stats['missing_estimated']
    return {k: stats[k] for k in ('status', 'elapsed_seconds', 'samples', 'packets',
            'errors', 'duplicates', 'gaps', 'missing_estimated',
            'counter_discontinuities', 'counter_wraps_24bit', 'poll_wait_seconds')} | {
        'missing_fraction': stats['missing_estimated'] / total if total else None,
        'unique_samples_per_host_second': stats['samples'] / stats['elapsed_seconds']}


def main():
    if not shutil.which('fuser'):
        raise ValueError('缺少 fuser，不能确认设备占用情况；请先安装 psmisc。')
    nodes = []
    for node in Path('/dev').glob('video*'):
        sys = (Path('/sys/class/video4linux') / node.name / 'device').resolve()
        if any((p/'idVendor').is_file() and (p/'idProduct').is_file() and
               (p/'idVendor').read_text().strip().lower() == '1bcf' and
               (p/'idProduct').read_text().strip().lower() == '0b15'
               for p in (sys, *sys.parents)):
            nodes.append(str(node))
    if nodes:
        busy = subprocess.run(['fuser', '-s', *nodes]).returncode
        if busy == 0:
            raise ValueError('头环正在被使用。请关闭标定工具的启动终端和其他预览程序后再试；本程序不会停止其他进程。')
        if busy != 1:
            raise ValueError('无法检查设备占用情况，停止。')
    device, info = find_device()
    root = Path(tempfile.mkdtemp(prefix='imu_poll_check_', dir=Path.home()))
    (root/'device.txt').write_text(device+'\n'+info)
    report = {'status': 'DIAGNOSTIC_ONLY', 'video_stream_enabled': True,
              'browser_preview_enabled': False,
              'quality_accepted': False, 'phases': [],
              'note': 'Sequential 60s A/B/A test with the normal FFmpeg video stream continuously drained; no browser JPEG rendering. Not long-run validation.'}
    try:
        print('正在启动视频流并检查首帧……', flush=True)
        with VideoStream(device, root/'video-stream.log') as stream:
            for name, wait in [('A_10ms', .01), ('B_0ms', 0), ('A2_10ms', .01)]:
                stream.check()
                out = root/name
                out.mkdir()
                print('\n开始 '+name+'：60 秒。保持头环连接，按 Ctrl+C 可停止。', flush=True)
                last = [-1]
                def notify(state, values):
                    stream.check()
                    second = int(values['elapsed'])
                    if second//10 != last[0]:
                        last[0] = second//10
                        print(f"  {second}/60 秒；有效样本 {values['samples']}；缺口 {values['gaps']}；重复 {values['duplicates']}", flush=True)
                stats = capture(out, device, 60, threading.Event(), threading.Event(),
                                notify, poll_wait_seconds=wait)
                report['phases'].append({'name': name, **summarize(stats)})
            stream.check()
            report['video_frames_drained'] = stream.frames
            report['comparison_completed'] = True
    finally:
        (root/'poll-comparison.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
        with tarfile.open(root/'imu_poll_review.tar.gz', 'w:gz') as tar:
            for path in root.rglob('*'):
                if path.is_file() and path.suffix in ('.json', '.txt', '.log'):
                    tar.add(path, arcname=str(path.relative_to(root)))
                elif path.name == 'imu_requests.csv':
                    tar.add(path, arcname=str(path.relative_to(root)))
        print('\n数据已保留：'+str(root), flush=True)
        print('请上传：'+str(root/'imu_poll_review.tar.gz'), flush=True)
        subprocess.run(['xdg-open', str(root)], check=False)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit('测试已停止，已有数据保留。')
    except Exception as exc:
        raise SystemExit('测试停止：'+str(exc))
