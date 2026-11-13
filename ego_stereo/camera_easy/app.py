#!/usr/bin/env python3
"""Local single-entry camera calibration assistant (2UQ2, Linux, camera only)."""
import argparse
from collections import deque
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import secrets
import shutil
import signal
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse
import webbrowser
import cv2
import numpy as np
from core import Board, FrameStore, WIDTH, HEIGHT, SAMPLE_HZ, device_id, require
from environment import Docker
from hardware import Camera, find_device
from pipeline import calculate

ROOT = Path(__file__).resolve().parent
DOWNLOADS = {'camera-camchain.yaml', 'camera-results-cam.txt', 'camera-report-cam.pdf',
             'camera_easy_small_review.tar.gz', 'aprilgrid.yaml', 'calculation.json'}

def motion(elapsed, duration):
    fraction = elapsed / duration
    if fraction < .10: return '标定板放在画面中间，保持清晰；头环始终固定。'
    if fraction < .30: return '缓慢移动到左上、右上，让图案覆盖两幅画面的上方。'
    if fraction < .50: return '缓慢移动到左下、右下，补充两幅画面的下方和边缘。'
    if fraction < .70: return '让板向左、右、上、下倾斜，改变角度，避免只正对镜头。'
    if fraction < .90: return '将板缓慢靠近、远离，兼顾近景和远景；尽量让两个镜头同时看到板。'
    return '补充尚未覆盖的边缘和倾斜角度，避免模糊、反光、弯曲。结束后自动计算。'


class App:
    def __init__(self, args):
        self.args = args
        self.docker = Docker(args.sudo_docker)
        self.lock = threading.RLock()
        self.changed = threading.Condition(self.lock)
        self.stop = threading.Event()
        self.end_capture = threading.Event()
        self.thread = None
        self.store = None
        self.run = None
        self.container = None
        self.data_root = None
        self.info = None
        self.jpeg = None
        self.sequence = 0
        self.frame_ns = 0
        self.logs = deque(maxlen=100)
        self.state = dict(stage='CHECKING', message='正在检查 Linux、Docker 和 Kalibr 环境…',
                          pairs=0, elapsed=0, duration=60, result=None, output='',
                          board=asdict(Board()), device_id='2UQ2')
        self.config = Path.home() / '.config' / 'EgoStereoIMU' / 'camera_easy.json'
        if self.config.is_file():
            try:
                config = json.loads(self.config.read_text())
                self.state['board'] = asdict(Board.parse(config['board']))
                self.state['device_id'] = device_id(config['device_id'])
            except Exception:
                pass
        self.boot()

    def log(self, line):
        with self.lock: self.logs.append(str(line))
        print(line, flush=True)

    def update(self, stage, message):
        with self.lock:
            self.state.update(stage=stage, message=message)
        self.log(message)
        self.persist()

    def persist(self):
        with self.lock:
            if self.run:
                (self.run / 'run_status.json').write_text(json.dumps(self.state, ensure_ascii=False, indent=2) + '\n')

    def public(self):
        with self.lock:
            data = dict(self.state)
            if data['stage'] == 'RECORDING':
                data['elapsed'] = round(time.monotonic() - self.started, 1)
                data['message'] = motion(data['elapsed'], data['duration'])
            data['log_tail'] = list(self.logs)[-30:]
            data['files'] = sorted(n for n in DOWNLOADS if self.run and (self.run / n).is_file())
            return data

    def boot(self):
        with self.lock:
            require(not self.thread or not self.thread.is_alive(), '当前任务尚未结束，请等待')
            self.run = None
            self.state.update(stage='CHECKING', message='正在连接设备并检查标定环境…', output='', result=None, pairs=0, elapsed=0)
            self.thread = threading.Thread(target=self.camera_loop, name='camera-easy', daemon=True)
            self.thread.start()

    def camera_loop(self):
        camera = None
        completed = False
        try:
            if self.container is None:
                self.container, self.data_root, self.info = self.docker.prepare(
                    self.args.container, self.args.image, self.args.image_archive)
            device, details = find_device(self.args.device)
            logs = Path.home() / 'EgoStereoIMU' / 'camera_easy_logs'
            logs.mkdir(parents=True, exist_ok=True)
            capture_log = logs / ('preview_' + secrets.token_hex(5) + '.log')
            camera = Camera(device, capture_log)
            anchor_mono, anchor_unix = time.monotonic_ns(), time.time_ns()
            next_sample = 0
            first = True
            while not self.stop.is_set():
                raw = camera.read(self.stop)
                now_ns = time.monotonic_ns()
                frame = np.frombuffer(raw, dtype=np.uint8).reshape(HEIGHT, WIDTH, 3)
                ok, encoded = cv2.imencode('.jpg', cv2.resize(frame, (1280, 360)), [cv2.IMWRITE_JPEG_QUALITY, 80])
                require(ok, '预览编码失败')
                with self.changed:
                    self.jpeg, self.frame_ns = encoded.tobytes(), now_ns
                    self.sequence += 1
                    self.changed.notify_all()
                    if first:
                        self.state.update(stage='READY', message='左右画面已连接。固定头环，准备好标定板后点击开始。')
                        self.hardware = dict(device=device, v4l2_format=details, ffmpeg_command=camera.command,
                                             capture_log=str(capture_log), platform=platform.platform(),
                                             cv2_version=cv2.__version__, container=self.container,
                                             docker_image_id=self.info['Image'])
                        first = False
                    if self.state['stage'] == 'RECORDING':
                        if next_sample == 0: next_sample = now_ns
                        if now_ns >= next_sample:
                            self.store.add(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY),
                                           int(anchor_unix + now_ns - anchor_mono))
                            self.state['pairs'] = len(self.store.pairs)
                            period = int(1e9 / SAMPLE_HZ)
                            next_sample += ((now_ns - next_sample) // period + 1) * period
                        elapsed = time.monotonic() - self.started
                        if elapsed >= self.state['duration'] or self.end_capture.is_set():
                            self.state.update(stage='PREPARING', elapsed=round(elapsed, 1))
                            self.store.finish()
                            completed = True
                            break
            if self.stop.is_set(): raise InterruptedError('工具已停止')
        except Exception as error:
            self.fail(error)
        finally:
            if camera:
                camera.close()
        if completed and not self.stop.is_set():
            try:
                result = calculate(self.run, self.docker, self.container, self.data_root, self.info,
                                   self.stop, self.update, self.log)
                with self.lock: self.state['result'] = result
                self.update('DONE', '相机参数已计算并生成文件。请打开 PDF 报告检查结果。')
            except Exception as error:
                self.fail(error)
            finally:
                self.store = None

    def fail(self, error):
        with self.lock:
            if self.store and self.state['stage'] == 'RECORDING':
                (self.run / 'capture_aborted.json').write_text(json.dumps(
                    {'status': 'CAPTURE_ABORTED', 'error': str(error), 'pairs_saved': self.store.pairs}, indent=2))
            self.store = None
        self.update('FAILED', str(error))

    def start(self, value):
        board = Board.parse(value['board'])
        ident = device_id(value['device_id'])
        seconds = float(value.get('seconds', 60))
        require(seconds in (60, 90, 120), '采集时长请选择 60、90 或 120 秒')
        with self.lock:
            require(self.state['stage'] == 'READY' and time.monotonic_ns() - self.frame_ns < 2_000_000_000,
                    '请先等待左右画面正常显示')
            parent = self.data_root / 'camera_easy' / ident
            parent.mkdir(parents=True, exist_ok=True)
            needed = int(seconds * SAMPLE_HZ * WIDTH * HEIGHT * 2 + 1024**3)
            require(shutil.disk_usage(parent).free > needed, f'空间不足，至少需要约 {needed / 1024**3:.1f} GiB')
            run = parent / (datetime.now(timezone.utc).strftime('camera_%Y%m%dT%H%M%SZ_') + secrets.token_hex(4))
            run.mkdir()
            board.write(run)
            self.run = run
            self.store = FrameStore(run)
            (run / 'hardware.json').write_text(json.dumps(self.hardware, ensure_ascii=False, indent=2))
            self.config.parent.mkdir(parents=True, exist_ok=True)
            self.config.write_text(json.dumps(dict(board=asdict(board), device_id=ident), indent=2))
            self.end_capture.clear()
            self.started = time.monotonic()
            self.state.update(stage='RECORDING', message=motion(0, seconds), pairs=0, duration=seconds,
                              elapsed=0, result=None, output=str(run), board=asdict(board), device_id=ident)
        self.persist()

    def finish_early(self):
        with self.lock:
            require(self.state['stage'] == 'RECORDING' and self.state['pairs'] >= 40,
                    '至少采集 40 对后才能提前结束；建议完成全部动作提示')
            self.end_capture.set()

    def close(self):
        self.stop.set()
        if self.run and self.container:
            inner = '/data/' + self.run.relative_to(self.data_root).as_posix()
            self.docker.kill_group(self.container, inner)
        with self.changed: self.changed.notify_all()
        if self.thread: self.thread.join(timeout=12)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def send_bytes(self, code, data, kind='application/json; charset=utf-8'):
        self.send_response(code)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers(); self.wfile.write(data)

    def do_GET(self):
        app = self.server.app
        path = unquote(urlparse(self.path).path)
        try:
            if path == '/':
                html = (ROOT / 'web.html').read_text().replace('__TOKEN__', self.server.token)
                return self.send_bytes(200, html.encode(), 'text/html; charset=utf-8')
            if path == '/state':
                return self.send_bytes(200, json.dumps(app.public(), ensure_ascii=False).encode())
            if path == '/stream.mjpg':
                self.send_response(200)
                self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=ego_frame')
                self.send_header('Cache-Control', 'no-store'); self.end_headers()
                previous = 0
                while not app.stop.is_set():
                    with app.changed:
                        app.changed.wait_for(lambda: app.sequence != previous or app.stop.is_set(), timeout=2)
                        if app.sequence == previous: continue
                        previous, data = app.sequence, app.jpeg
                    self.wfile.write(b'--ego_frame\r\nContent-Type: image/jpeg\r\nContent-Length: ' +
                                     str(len(data)).encode() + b'\r\n\r\n' + data + b'\r\n')
                    self.wfile.flush()
                return
            if path.startswith('/files/') and path[7:] in DOWNLOADS and app.run:
                name = path[7:]; file = app.run / name
                require(file.is_file(), '文件尚未生成')
                kind = 'application/pdf' if name.endswith('.pdf') else 'application/octet-stream'
                return self.send_bytes(200, file.read_bytes(), kind)
            return self.send_bytes(404, b'{}')
        except (BrokenPipeError, ConnectionResetError): pass
        except Exception as error:
            self.send_bytes(400, json.dumps({'error': str(error)}, ensure_ascii=False).encode())

    def do_POST(self):
        try:
            require(self.headers.get('X-Ego-Token') == self.server.token, '请求校验失败，请重新打开当前页面')
            size = int(self.headers.get('Content-Length', '0'))
            require(0 <= size <= 8192, '请求过大')
            value = json.loads(self.rfile.read(size) or b'{}')
            if self.path == '/start': self.server.app.start(value)
            elif self.path == '/finish': self.server.app.finish_early()
            elif self.path == '/reconnect': self.server.app.boot()
            else: raise ValueError('未知操作')
            self.send_bytes(200, b'{"ok":true}')
        except Exception as error:
            self.send_bytes(400, json.dumps({'error': str(error)}, ensure_ascii=False).encode())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sudo-docker', action='store_true')
    parser.add_argument('--container')
    parser.add_argument('--image', default='kalibr:noetic')
    parser.add_argument('--image-archive', type=Path)
    parser.add_argument('--device')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--setup-only', action='store_true')
    args = parser.parse_args()
    os.umask(0o022)
    if args.setup_only:
        name, root, info = Docker(args.sudo_docker).prepare(args.container, args.image, args.image_archive)
        print('Kalibr 环境可用：', name, root, info['Image']); return
    app = App(args)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    server.app, server.token = app, secrets.token_hex(24)
    url = f'http://127.0.0.1:{server.server_port}/'
    print('相机标定入口：' + url, flush=True)
    if not args.no_browser: webbrowser.open(url)
    def interrupted(*_): raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    try: server.serve_forever(poll_interval=.25)
    except KeyboardInterrupt: pass
    finally: app.close(); server.server_close()

if __name__ == '__main__':
    main()
