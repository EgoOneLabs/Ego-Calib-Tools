import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
from types import SimpleNamespace
import numpy as np
import yaml
import core
from core import Board, FrameStore, inspect_outputs
from hardware import Camera
from bag_writer import write
from pipeline import calculate
from app import Handler, ThreadingHTTPServer

REFERENCE = Path(__file__).resolve().parents[1] / 'reference/2uq2-ds-20261102'

class CoreTests(unittest.TestCase):
    def test_board_measured_mm_and_ratio(self):
        with tempfile.TemporaryDirectory() as d:
            b = Board.parse(dict(rows=6, cols=6, tag_mm=40, gap_mm=12))
            out = b.write(d)
            self.assertEqual(out['tagSize'], .04)
            self.assertAlmostEqual(out['tagSpacing'], .3)
            for wrong in (float('nan'), float('inf'), 0, -1):
                with self.assertRaises(ValueError): Board.parse(dict(rows=6, cols=6, tag_mm=wrong, gap_mm=12))
            with self.assertRaises(ValueError): Board.parse(dict(rows=6.5, cols=6, tag_mm=40, gap_mm=12))

    def test_full_sensor_split_preserves_pixels_and_time(self):
        with tempfile.TemporaryDirectory() as d:
            store = FrameStore(d)
            frame = np.zeros((1080, 3840), np.uint8); frame[:, :1920] = 17; frame[:, 1920:] = 231
            stamp = 1793351091166671038
            store.add(frame, stamp)
            for side, expected in [('left', 17), ('right', 231)]:
                data = Path(d, store.pairs[0][side]['file']).read_bytes()
                self.assertTrue(data.startswith(b'P5\n1920 1080\n255\n'))
                self.assertEqual(data.split(b'\n', 3)[3], bytes([expected]) * (1920 * 1080))
            self.assertEqual(store.pairs[0]['timestamp_ns'], stamp)
            with self.assertRaises(ValueError): store.add(frame, stamp)
            with self.assertRaises(ValueError): store.add(np.zeros((10, 10), np.uint8), stamp + 1)
            with self.assertRaises(ValueError): store.finish()

    def test_synthetic_bag_roundtrip_and_tamper_rejection(self):
        with tempfile.TemporaryDirectory() as d, patch.multiple(core, WIDTH=32, HEIGHT=12, EYE_WIDTH=16):
            root = Path(d); store = FrameStore(root)
            for i in range(40): store.add(np.full((12, 32), i, np.uint8), 1793351091166671038 + i * 250000000)
            store.finish(); report = write(root, 'rosbags')
            self.assertTrue(report['all_pixels_verified'])
            self.assertEqual(report['counts'], {'/cam0/image_raw': 40, '/cam1/image_raw': 40})
            (root / 'camera.bag').unlink(); (root / 'bag_verification.json').unlink()
            file = root / store.pairs[0]['left']['file']; file.write_bytes(file.read_bytes() + b'x')
            with self.assertRaisesRegex(ValueError, 'checksum'): write(root, 'rosbags')

    def test_real_output_fixture_and_nan_rejection(self):
        import shutil
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for suffix in ('camchain.yaml', 'results-cam.txt', 'report-cam.pdf'):
                shutil.copy2(REFERENCE / ('camera_4hz-' + suffix), root / ('camera-' + suffix))
            report = inspect_outputs(root)
            self.assertAlmostEqual(report['stereo_baseline_mm'], 89.271331536, places=3)
            self.assertFalse(report['quality_accepted'])
            f = root / 'camera-camchain.yaml'; value = yaml.safe_load(f.read_text())
            value['cam0']['intrinsics'][2] = float('nan'); f.write_text(yaml.safe_dump(value))
            with self.assertRaisesRegex(ValueError, 'NaN'): inspect_outputs(root)
            (root / 'camera-report-cam.pdf').unlink()
            with self.assertRaisesRegex(ValueError, '缺少'): inspect_outputs(root)

class CaptureTests(unittest.TestCase):
    def camera(self, code, directory):
        actual = subprocess.Popen
        with patch('hardware.subprocess.Popen', side_effect=lambda *args, **kwargs: actual([sys.executable, '-c', code], **kwargs)):
            return Camera('/dev/not-used', Path(directory) / 'ffmpeg.log')

    def test_stalled_video_has_bounded_timeout(self):
        with tempfile.TemporaryDirectory() as d:
            camera = self.camera('import time; time.sleep(30)', d)
            before = time.monotonic()
            try:
                with self.assertRaisesRegex(ValueError, '完整图像'): camera.read(threading.Event(), timeout=.15)
                self.assertLess(time.monotonic() - before, 1)
            finally: camera.close()

    def test_disconnect_never_yields_partial_frame(self):
        with tempfile.TemporaryDirectory() as d:
            camera = self.camera('import sys;sys.stdout.buffer.write(bytes(10))', d)
            try:
                with self.assertRaisesRegex(ValueError, '视频流已结束'): camera.read(threading.Event())
            finally: camera.close()

    def test_stop_interrupts_waiting_frame(self):
        with tempfile.TemporaryDirectory() as d:
            camera = self.camera('import time;time.sleep(30)', d)
            stop = threading.Event(); stop.set()
            try:
                with self.assertRaises(InterruptedError): camera.read(stop)
            finally: camera.close()

class HttpTests(unittest.TestCase):
    def test_control_requires_token_and_downloads_are_whitelisted(self):
        from unittest.mock import Mock
        called = Mock()
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler); server.daemon_threads = True
        server.token = 'valid'
        server.app = SimpleNamespace(start=called, run=Path('/tmp'), public=lambda: {'stage': 'READY'})
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            req = urllib.request.Request(base + '/start', data=b'{}', method='POST')
            with self.assertRaises(urllib.error.HTTPError) as e: urllib.request.urlopen(req)
            self.assertEqual(e.exception.code, 400); called.assert_not_called()
            req = urllib.request.Request(base + '/start', data=b'{}', headers={'X-Ego-Token': 'valid'}, method='POST')
            with urllib.request.urlopen(req) as r: self.assertEqual(r.status, 200)
            called.assert_called_once_with({})
            with self.assertRaises(urllib.error.HTTPError): urllib.request.urlopen(base + '/files/../../etc/passwd')
        finally:
            server.shutdown(); server.server_close(); thread.join()

class PipelineTests(unittest.TestCase):
    def pipeline(self, fail=False):
        from environment import Docker
        import tarfile
        with tempfile.TemporaryDirectory() as d, patch.multiple(core, WIDTH=32, HEIGHT=12, EYE_WIDTH=16):
            data = Path(d); root = data / 'run'; root.mkdir(); Board().write(root)
            store = FrameStore(root)
            for i in range(40): store.add(np.full((12, 32), i, np.uint8), 1793351091166671038 + i * 250000000)
            store.finish()
            fake = data / 'fake_docker.py'
            fake.write_text('''import os,sys,subprocess,shutil\nfrom pathlib import Path\nroot=Path(''' + repr(str(root)) + ''')\nargs=sys.argv[1:]\nif any('bag_writer.py' in v for v in args):\n sys.exit(subprocess.call([sys.executable,str(root/'bag_writer.py'),'--root',str(root),'--backend','rosbags']))\n'''+ ('sys.exit(7)\n' if fail else '''reference=Path(''' + repr(str(REFERENCE)) + ''')\nfor suffix in ['camchain.yaml','results-cam.txt','report-cam.pdf']:\n shutil.copy2(reference/('camera_4hz-'+suffix),root/('camera-'+suffix))\nimport yaml\nf=root/'camera-camchain.yaml'\nv=yaml.safe_load(f.read_text())\nfor cam in v.values(): cam['resolution']=[16,12]\nf.write_text(yaml.safe_dump(v))\nprint('real 0.1\\nuser 0.2\\nsys 0.01')\n'''))
            docker = Docker(); docker.prefix = [sys.executable, str(fake)]
            stages = []
            if fail:
                with self.assertRaises(ValueError): calculate(root, docker, 'test', data, {'Image': 'fixture'}, threading.Event(), lambda s,m: stages.append(s), lambda _: None)
                self.assertEqual(json.loads((root / 'calculation.json').read_text())['status'], 'FAILED_OR_INTERRUPTED')
            else:
                result = calculate(root, docker, 'test', data, {'Image': 'fixture'}, threading.Event(), lambda s,m: stages.append(s), lambda _: None)
                self.assertFalse(result['quality_accepted'])
                self.assertEqual(stages, ['BAG', 'CALIBRATING'])
                self.assertEqual(result['timing_seconds']['real'], .1)
            with tarfile.open(root / 'camera_easy_small_review.tar.gz') as archive:
                self.assertFalse(any(n.endswith(('.bag', '.pgm')) for n in archive.getnames()))
                self.assertIn('calculation.json', archive.getnames())

    def test_successful_orchestration_with_real_bag_io_and_fixture_kalibr(self): self.pipeline()
    def test_failed_optimizer_cannot_report_success(self): self.pipeline(fail=True)

if __name__ == '__main__': unittest.main(verbosity=2)
