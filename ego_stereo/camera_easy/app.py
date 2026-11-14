#!/usr/bin/env python3
"""Unified 2UQ2 calibration: camera, IMU and joint raw capture/preflight."""
import argparse
from collections import deque
from dataclasses import asdict
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import platform
import secrets
import shutil
import signal
import subprocess
import threading
import time
import tarfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse
import webbrowser
import cv2
import numpy as np
from core import Board, FrameStore, WIDTH, HEIGHT, SAMPLE_HZ, device_id, require
from environment import Docker
from hardware import Camera, find_device
from pipeline import calculate
from imu_capture import capture as capture_imu
from imu_analysis import analyze as analyze_imu
from joint import joint_motion, validate_inputs, save_inputs, inspect_capture, pack_review
from offline import Offline, EXPORTS as OFFLINE_EXPORTS
from parameters import Parameters

ROOT = Path(__file__).resolve().parent
DOWNLOADS = {'camera-camchain.yaml', 'camera-results-cam.txt', 'camera-report-cam.pdf',
             'camera_easy_small_review.tar.gz', 'aprilgrid.yaml', 'calculation.json',
             'imu_capture.json', 'imu-analysis.json', 'imu-results.txt', 'imu-report.pdf',
             'imu_experimental_review.tar.gz', 'imu-experimental.yaml', 'imu-experimental-fit.json', 'imu-allan.csv', 'imu-candidate.yaml', 'imu_small_review.tar.gz', 'imu_error.txt',
             'joint_dependencies.json', 'joint_capture.json', 'joint_clock.json',
             'camera_imu-results.txt', 'camera_imu_small_review.tar.gz', 'joint_error.txt',
             'camera_imu-camchain-imucam.yaml', 'camera_imu-report-imucam.pdf',
             'camera_imu-results-imucam.txt', 'joint_calculation.json'}

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
        self.imu_thread = None
        self.imu_cancel = threading.Event()
        self.joint_frames_done = threading.Event()
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
                          board=asdict(Board()), device_id='2UQ2', mode='camera',
                          samples=0, packets=0, errors=0, gaps=0, duplicates=0)
        self.config = Path.home() / '.config' / 'EgoStereoIMU' / 'camera_easy.json'
        if self.config.is_file():
            try:
                config = json.loads(self.config.read_text())
                self.state['board'] = asdict(Board.parse(config['board']))
                self.state['device_id'] = device_id(config['device_id'])
            except Exception:
                pass
        self.parameters = Parameters(self.config.parent/'joint_parameters.json')
        self.offline = Offline(self)
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
            if data['stage'] in ('RECORDING','JOINT_RECORDING'):
                data['elapsed'] = round(time.monotonic() - self.started, 1)
                guide = joint_motion if data['mode']=='camera_imu' else motion
                data['message'] = guide(data['elapsed'], data['duration'])
            data['log_tail'] = list(self.logs)[-30:]
            data['files'] = sorted(n for n in DOWNLOADS if self.run and (self.run / n).is_file())
            return data

    def boot(self):
        with self.lock:
            require(not self.offline.busy(), '已有数据计算或验证尚未结束')
            if self.state['mode'] in ('imu','camera_imu') and self.state['stage'] in ('DONE', 'FAILED') and self.thread and self.thread.is_alive():
                require(not self.imu_thread or not self.imu_thread.is_alive(), 'IMU 任务正在结束，请稍候')
                require(time.monotonic_ns() - self.frame_ns < 2_000_000_000, '预览已断开，请关闭并重新启动工具')
                self.run = None
                self.store = None
                self.state.update(stage='READY', message='设备已就绪，可以选择下一项标定。', output='', result=None, samples=0)
                return
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
            self.clock_anchor = {'monotonic_ns':anchor_mono,'unix_ns':anchor_unix,
                                 'image_time_basis':'Host complete-frame read, not exposure time',
                                 'imu_time_basis':'Raw counters and host request intervals; per-sample time pending review'}
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
                    if self.state['stage'] in ('RECORDING','JOINT_RECORDING'):
                        if next_sample == 0: next_sample = now_ns
                        if now_ns >= next_sample:
                            self.store.add(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY),
                                           int(anchor_unix + now_ns - anchor_mono))
                            self.state['pairs'] = len(self.store.pairs)
                            period = int(1e9 / self.store.sample_hz)
                            next_sample += ((now_ns - next_sample) // period + 1) * period
                        elapsed = time.monotonic() - self.started
                        if elapsed >= self.state['duration'] or self.end_capture.is_set():
                            self.state.update(stage='PREPARING', elapsed=round(elapsed, 1))
                            self.store.finish()
                            if self.state['mode']=='camera_imu':
                                self.store = None
                                self.state.update(stage='JOINT_CHECKING',message='正在检查联合采集数据和计算前置条件…')
                                self.end_capture.set()
                                self.joint_frames_done.set()
                                continue
                            completed = True
                            break
            if self.stop.is_set(): raise InterruptedError('工具已停止')
        except Exception as error:
            if not (self.stop.is_set() and self.state['stage']=='DONE'):
                self.fail(error)
        finally:
            if camera:
                camera.close()
        if completed and not self.stop.is_set():
            try:
                result = calculate(self.run, self.docker, self.container, self.data_root, self.info,
                                   self.stop, self.update, self.log)
                with self.lock: self.state['result'] = result
                self.parameters.remember(self.state['device_id'],'camera',self.run/'camera-camchain.yaml')
                self.update('DONE', '相机参数已计算并生成文件。请打开 PDF 报告检查结果。')
            except Exception as error:
                self.fail(error)
            finally:
                self.store = None

    def fail(self, error):
        self.imu_cancel.set()
        with self.lock:
            if self.store and self.state['stage'] in ('RECORDING','JOINT_RECORDING'):
                (self.run / 'capture_aborted.json').write_text(json.dumps(
                    {'status': 'CAPTURE_ABORTED', 'error': str(error), 'pairs_saved': self.store.pairs}, indent=2))
            self.store = None
        self.update('FAILED', str(error))

    def start(self, value):
        mode = value.get('mode', 'camera')
        require(mode in ('camera', 'imu','camera_imu'), '未知标定模块')
        if mode == 'imu':
            return self.start_imu(value)
        if mode == 'camera_imu':
            return self.start_joint(value)
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
            self.state.update(stage='RECORDING', mode='camera', message=motion(0, seconds), pairs=0, duration=seconds,
                              elapsed=0, result=None, output=str(run), board=asdict(board), device_id=ident)
        self.persist()

    def generate_imu_experiment(self):
        from imu_experimental import generate
        with self.lock:
            require(self.state['mode']=='imu' and self.state['stage']=='DONE', '请先完成当前 IMU 分析')
            report=generate(self.run)
            self.state['message']='实验混合模型权重已生成；局部斜率结果保留，尚未通过动态残差和重复性验收。'
            self.state['result']['experimental_weights_available']=True
            self.state['result']['experimental_weights_status']=report['status']
            self.parameters.remember(self.state['device_id'],'imu',self.run/'imu-experimental.yaml')

    def start_imu(self, value):
        ident = device_id(value['device_id'])
        seconds = float(value.get('imu_seconds', 7200))
        require(math.isfinite(seconds) and 60 <= seconds <= 86400, '录制时长请输入 1 分钟至 24 小时之间的有效数值')
        with self.lock:
            require(self.state['stage'] == 'READY' and time.monotonic_ns()-self.frame_ns < 2_000_000_000,
                    '请先等待设备连接和左右预览正常')
            require(not self.imu_thread or not self.imu_thread.is_alive(), '已有 IMU 任务运行中')
            parent = self.data_root / 'imu' / ident
            parent.mkdir(parents=True, exist_ok=True)
            needed = max(3*1024**3, int(seconds*400000 + 1024**3))
            require(shutil.disk_usage(parent).free > needed, f'本次录制请至少留出约 {needed/1024**3:.1f} GiB 空间')
            self.run = parent / (datetime.now(timezone.utc).strftime('imu_%Y%m%dT%H%M%SZ_')+secrets.token_hex(4))
            self.run.mkdir()
            (self.run / 'hardware.json').write_text(json.dumps(self.hardware, ensure_ascii=False, indent=2))
            self.end_capture.clear(); self.imu_cancel.clear()
            self.state.update(stage='IMU_RECORDING', mode='imu', device_id=ident, duration=seconds,
                elapsed=0, samples=0, packets=0, errors=0, gaps=0, duplicates=0,
                message='正在检查 IMU 读取，请保持头环静止。', result=None, output=str(self.run))
            self.imu_thread = threading.Thread(target=self.imu_loop,
                args=(self.run, seconds),name='imu-capture',daemon=True)
            self.imu_thread.start()

    def imu_loop(self, run, seconds):
        try:
            def notify(stage, values):
                with self.lock:
                    self.state.update(stage=stage, **values)
                    self.state['message'] = '正在记录 IMU。保持静止，不要碰桌面、拉线或移动头环。'
                self.persist()
            capture_imu(run,self.hardware['device'],seconds,
                        self.imu_cancel,self.end_capture,notify)
            if self.imu_cancel.is_set(): raise InterruptedError('IMU 已停止，原始数据保留')
            result = analyze_imu(run,self.imu_cancel,self.update)
            if (run/'imu-candidate.yaml').is_file():
                self.parameters.remember(self.state['device_id'],'imu',run/'imu-candidate.yaml')
            with self.lock: self.state['result'] = result
            self.update('DONE', 'IMU 数据检查和曲线已生成，请查看报告。'+('60 秒仅用于检查读取，不作为噪声标定验收。' if seconds==60 else '候选参数需复核后使用。'))
        except Exception as error:
            (run / 'imu_error.txt').write_text(str(error), encoding='utf-8')
            with tarfile.open(run / 'imu_small_review.tar.gz', 'w:gz') as tar:
                for name in ('imu_capture.json', 'imu_error.txt', 'hardware.json'):
                    if (run / name).is_file():tar.add(run / name, arcname=name)
            self.update('FAILED', str(error))

    def finish_early(self):
        with self.lock:
            if self.state['mode']=='camera_imu':
                require(self.state['stage']=='JOINT_RECORDING' and self.state['pairs']>=40,
                        '至少保存 40 对图像后才能提前结束，完整运动仍需覆盖全部轴')
                self.end_capture.set()
                return
            if self.state['mode'] == 'imu':
                require(self.state['stage'] == 'IMU_RECORDING', '当前没有 IMU 采集任务')
                self.end_capture.set()
                return
            require(self.state['stage'] == 'RECORDING' and self.state['pairs'] >= 40,
                    '至少采集 40 对后才能提前结束；建议完成全部动作提示')
            self.end_capture.set()

    def start_joint(self,value):
        ident=device_id(value['device_id'])
        board=Board.parse(value['board'])
        seconds=float(value.get('joint_seconds',90))
        require(seconds in (60,90,120),'联合采集请选择 60、90 或 120 秒')
        camera_text=value.get('camera_yaml','');imu_text=value.get('imu_yaml','')
        dependencies=validate_inputs(camera_text,imu_text)
        auto_calculate=value.get('auto_calculate') is True
        if auto_calculate:
            require(not dependencies['missing'],'第三步需要 Camera 相机参数 YAML 和 IMU 噪声参数 YAML，请先拖入这两个文件')
            require(value.get('experimental_ack') is True,'当前为实验时间映射计算，请使用更新后的页面')
        with self.lock:
            require(self.state['stage']=='READY' and time.monotonic_ns()-self.frame_ns<2_000_000_000,
                    '请先等待左右实时预览正常')
            require(not self.imu_thread or not self.imu_thread.is_alive(),'当前 IMU 任务还未结束')
            parent=self.data_root/'camera_imu'/ident;parent.mkdir(parents=True,exist_ok=True)
            needed=int(seconds*10*WIDTH*HEIGHT*2+1024**3)
            require(shutil.disk_usage(parent).free>needed,f'联合采集至少需要约 {needed/1024**3:.1f} GiB 空间')
            self.run=parent/(datetime.now(timezone.utc).strftime('camera_imu_%Y%m%dT%H%M%SZ_')+secrets.token_hex(4))
            self.run.mkdir();board.write(self.run)
            save_inputs(self.run,camera_text,imu_text)
            if auto_calculate:
                self.parameters.remember(ident,'camera',self.run/'input-camera.yaml')
                self.parameters.remember(ident,'imu',self.run/'input-imu.yaml')
            (self.run/'hardware.json').write_text(json.dumps(self.hardware,ensure_ascii=False,indent=2))
            (self.run/'joint_clock.json').write_text(json.dumps(self.clock_anchor,ensure_ascii=False,indent=2))
            self.store=FrameStore(self.run,sample_hz=10,purpose='joint raw capture; timing review required')
            self.end_capture.clear();self.imu_cancel.clear();self.joint_frames_done.clear()
            self.started=time.monotonic()
            self.state.update(stage='JOINT_RECORDING',mode='camera_imu',device_id=ident,board=asdict(board),
                duration=seconds,elapsed=0,pairs=0,samples=0,packets=0,errors=0,gaps=0,duplicates=0,
                message=joint_motion(0,seconds),result=None,output=str(self.run),auto_calculate=auto_calculate)
            self.imu_thread=threading.Thread(target=self.joint_loop,args=(self.run,seconds,auto_calculate),name='joint-capture',daemon=True)
            self.imu_thread.start()
        self.persist()

    def joint_loop(self,run,seconds,auto_calculate=False):
        try:
            def notify(stage,values):
                with self.lock:
                    self.state.update({k:v for k,v in values.items() if k!='elapsed'})
                self.persist()
            capture_imu(run,self.hardware['device'],seconds+5,self.imu_cancel,self.end_capture,notify)
            require(not self.imu_cancel.is_set(),'联合采集已停止，原始数据保留')
            require(self.joint_frames_done.wait(10),'图像采集未正常结束，原始数据保留')
            result=inspect_capture(run)
            with self.lock:self.state['result']=result
            self.update('DONE','联合运动数据已保存。当前是采集检查结果；请先复核参数和时间轴，再运行联合求解。')
            if auto_calculate and not self.stop.is_set():
                from offline import identity
                self.offline.start(dict(dataset=identity(self.data_root,run),action='calibrate',experimental_ack=True,
                    camera_yaml=(run/'input-camera.yaml').read_text(),imu_yaml=(run/'input-imu.yaml').read_text()))
                with self.lock:self.state['message']='录制已保存，正在自动计算联合参数，请等待下方结果。'
                self.persist()
        except Exception as error:
            self.imu_cancel.set();self.end_capture.set()
            (run/'joint_error.txt').write_text(str(error),encoding='utf-8')
            pack_review(run)
            self.update('FAILED',str(error))

    def close(self):
        self.offline.cancel()
        self.stop.set()
        self.imu_cancel.set()
        if self.run and self.container:
            inner = '/data/' + self.run.relative_to(self.data_root).as_posix()
            self.docker.kill_group(self.container, inner)
        with self.changed: self.changed.notify_all()
        if self.thread: self.thread.join(timeout=12)
        if self.imu_thread: self.imu_thread.join(timeout=12)


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
                html = (ROOT / 'web.html').read_text().replace('<!--OFFLINE_PANEL-->', (ROOT/'offline.html').read_text()).replace('__TOKEN__', self.server.token)
                return self.send_bytes(200, html.encode(), 'text/html; charset=utf-8')
            if path == '/offline.js':
                return self.send_bytes(200,(ROOT/'offline.js').read_bytes(),'application/javascript; charset=utf-8')
            if path == '/existing.js':
                return self.send_bytes(200,(ROOT/'existing.js').read_bytes(),'application/javascript; charset=utf-8')
            if path == '/flow.js':
                return self.send_bytes(200,(ROOT/'flow.js').read_bytes(),'application/javascript; charset=utf-8')
            if path.startswith('/joint/parameters/'):
                return self.send_bytes(200,json.dumps(app.parameters.defaults(path.rsplit('/',1)[1]),ensure_ascii=False).encode())
            if path == '/state':
                return self.send_bytes(200, json.dumps(app.public(), ensure_ascii=False).encode())
            if path == '/offline/catalog':
                return self.send_bytes(200, json.dumps(app.offline.catalog(), ensure_ascii=False).encode())
            if path == '/offline/state':
                return self.send_bytes(200, json.dumps(app.offline.public(), ensure_ascii=False).encode())
            if path.startswith('/offline/parameter/'):
                return self.send_bytes(200, json.dumps(app.offline.parameter(path.rsplit('/',1)[1]), ensure_ascii=False).encode())
            if path.startswith('/offline/files/'):
                name=path.rsplit('/',1)[1]
                require(name in OFFLINE_EXPORTS and app.offline.out, '未知结果文件')
                file=app.offline.out/name
                require(file.is_file(), '文件尚未生成')
                kind='application/pdf' if name.endswith('.pdf') else 'application/octet-stream'
                return self.send_bytes(200,file.read_bytes(),kind)
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
            require(0 <= size <= 98304, '请求过大')
            value = json.loads(self.rfile.read(size) or b'{}')
            if self.path == '/start':
                with self.server.app.lock:
                    require(not self.server.app.offline.busy(), '请先等待已有数据计算或验证结束')
                    self.server.app.start(value)
            elif self.path == '/offline/start': self.server.app.offline.start(value)
            elif self.path == '/offline/stop': self.server.app.offline.cancel()
            elif self.path == '/offline/open': self.server.app.offline.open_output()
            elif self.path == '/open-output':
                require(self.server.app.run and self.server.app.run.is_dir(),'尚无结果目录')
                subprocess.Popen(['xdg-open',str(self.server.app.run)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            elif self.path == '/imu-experiment': self.server.app.generate_imu_experiment()
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
