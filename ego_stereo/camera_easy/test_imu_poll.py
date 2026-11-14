import threading
import unittest
from imu_poll_check import VideoStream


class StreamTests(unittest.TestCase):
    def test_first_frame_then_drain_and_release_on_capture_error(self):
        class Camera:
            def __init__(self, *args):
                self.closed = False
                self.calls = 0
            def read(self, stop):
                self.calls += 1
                if self.calls > 1:
                    stop.wait(1)
                    raise InterruptedError()
                return b'frame'
            def close(self):
                self.closed = True
        stream = VideoStream('fake', 'fake', Camera)
        with self.assertRaisesRegex(ValueError, 'capture error'):
            with stream:
                self.assertGreaterEqual(stream.frames, 1)
                raise ValueError('capture error')
        self.assertTrue(stream.camera.closed)
        self.assertFalse(stream.thread.is_alive())
        self.assertIsNone(stream.error)

    def test_first_frame_failure_closes_camera(self):
        class Broken:
            def __init__(self, *args): self.closed = False
            def read(self, stop): raise ValueError('no first frame')
            def close(self): self.closed = True
        stream = VideoStream('fake', 'fake', Broken)
        with self.assertRaisesRegex(ValueError, 'no first frame'):
            with stream: self.fail('capture must not start')
        self.assertTrue(stream.camera.closed)

    def test_stream_failure_is_reported(self):
        stream = VideoStream.__new__(VideoStream)
        stream.error = 'disconnected'
        with self.assertRaisesRegex(ValueError, 'disconnected'):
            stream.check()
