import io
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

import cv2
import numpy as np
from core import FrameStore, WIDTH, HEIGHT
from hardware import Camera
from extract_environment import extract


class ColorTests(unittest.TestCase):
    def test_color_pipe_framing_jpeg_and_full_size_gray_storage(self):
        # Two consecutive full sensor frames prove the three-channel stride,
        # stereo order, color encoding and mono8 calibration storage together.
        actual = subprocess.Popen
        code = ('import sys\n'
                'row=bytes([0,0,255])*1920+bytes([0,255,0])*1920\n'
                'sys.stdout.buffer.write(row*1080*2)\n')
        with tempfile.TemporaryDirectory() as d:
            with patch('hardware.subprocess.Popen', side_effect=lambda *a, **k: actual([sys.executable, '-c', code], **k)):
                camera = Camera('/dev/not-used', Path(d)/'capture.log')
            try:
                self.assertIn('bgr24', camera.command)
                for n in range(2):
                    raw = camera.read(threading.Event())
                    self.assertEqual(len(raw), WIDTH*HEIGHT*3)
                    frame = np.frombuffer(raw, np.uint8).reshape(HEIGHT, WIDTH, 3)
                    ok, jpeg = cv2.imencode('.jpg', cv2.resize(frame, (1280,360)))
                    self.assertTrue(ok)
                    preview = cv2.imdecode(jpeg, cv2.IMREAD_COLOR)
                    self.assertGreater(int(preview[180,320,2]), 240)
                    self.assertLess(int(preview[180,320,0]), 10)
                    self.assertGreater(int(preview[180,960,1]), 240)
                    store = FrameStore(Path(d)/str(n))
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    store.add(gray, 1793351091166671038+n)
                    for eye, expected in [('left',76),('right',150)]:
                        saved = cv2.imread(str(Path(d)/str(n)/store.pairs[0][eye]['file']), cv2.IMREAD_UNCHANGED)
                        self.assertEqual(saved.shape,(1080,1920))
                        self.assertTrue(np.all(saved==expected))
            finally:
                camera.close()

    def test_environment_reuse_verifies_payload_and_preserves_archive(self):
        import tarfile, hashlib
        payload=io.BytesIO()
        with tarfile.open(fileobj=payload,mode='w:gz') as tar:
            info=tarfile.TarInfo('environment/kalibr-environment.tar.gz')
            info.size=12
            tar.addfile(info,io.BytesIO(b'fixture-data'))
        data=payload.getvalue()
        header=('[[ a == "'+hashlib.sha256(data).hexdigest()+'" ]]\n__EGO_PAYLOAD_BELOW__\n').encode()
        with tempfile.TemporaryDirectory() as d:
            package=Path(d)/'full.zip'; target=Path(d)/'env/image.gz'
            with zipfile.ZipFile(package,'w') as z: z.writestr('camera.run',header+data)
            extract(package,target)
            self.assertEqual(target.read_bytes(),b'fixture-data')
            with zipfile.ZipFile(package,'w') as z: z.writestr('camera.run',header+data+b'changed')
            with self.assertRaisesRegex(ValueError,'校验失败'):extract(package,target)
            self.assertEqual(target.read_bytes(),b'fixture-data')
