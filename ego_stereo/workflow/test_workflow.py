"""Synthetic integration tests; not a replacement for phone/container acceptance."""
import csv
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from check_session import check
from prepare_camera import prepare
from bag_writer import write
from camera_workflow import calibrate, inner_path


class WorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='camera_workflow_test_')
        cls.root = Path(cls.temp.name)
        cls.session = cls.root / 'session'
        for name in ('videos', 'timestamps'):
            (cls.session / name).mkdir(parents=True)
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=64x32:rate=30',
                        '-frames:v', '30', '-c:v', 'mjpeg', '-threads', '1', str(cls.session / 'videos/left.mkv')], check=True)
        subprocess.run(['ffmpeg', '-v', 'error', '-i', str(cls.session / 'videos/left.mkv'), '-vf', 'hflip',
                        '-c:v', 'mjpeg', '-threads', '1', str(cls.session / 'videos/right.mkv')], check=True)
        epoch = 1793703345133000000
        times = [epoch + i * 33333333 for i in range(30)]
        for side in ('left', 'right'):
            (cls.session / 'timestamps' / (side + '_timestamps.txt')).write_text(''.join(
                '%d,%d.%09d\n' % (i, n // 10**9, n % 10**9) for i, n in enumerate(times)))
        with (cls.session / 'export_video_index.csv').open('w') as f:
            w = csv.writer(f)
            w.writerow(['output_frame_index', 'source_list_position', 'source_frame_index', 'frame_receive_boottime_ns', 'uvc_sequence'])
            w.writerows((i, i, i, n - epoch + 1000000000, i + 1) for i, n in enumerate(times))
        meta = dict(task='app_export_unplug_synthetic', video_export_status='COMPLETE', synced_frames=30,
                    topics={side: dict(width=64, height=32, written_frames=30) for side in ('left', 'right')})
        (cls.session / 'meta.json').write_text(json.dumps(meta))
        out = cls.root / 'check'
        out.mkdir()
        report = {}
        check(cls.session, out, report)
        cls.report = out / 'media_check.json'
        cls.report.write_text(json.dumps(report))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def prepared(self):
        return prepare(self.session, self.report, self.root / 'runs', 'smoke', 4)

    def test_paired_bag_roundtrip(self):
        root = self.prepared()
        manifest = json.loads((root / 'camera_manifest.json').read_text())
        self.assertEqual([p['source_output_frame_index'] for p in manifest['selected_pairs']], [0, 8, 16, 24])
        self.assertNotEqual(manifest['selected_pairs'][0]['left']['sha256'], manifest['selected_pairs'][0]['right']['sha256'])
        result = write(root, 'rosbags')
        self.assertEqual(result['counts'], {'/cam0/image_raw': 4, '/cam1/image_raw': 4})
        self.assertTrue(result['all_pixels_verified'])
        self.assertTrue(result['all_header_and_bag_timestamps_verified'])
        with self.assertRaisesRegex(ValueError, 'already exists'):
            write(root, 'rosbags')

    def test_changed_source_rejected(self):
        report = json.loads(self.report.read_text())
        report['videos']['left']['sha256'] = 'wrong'
        altered = self.root / 'bad_media_report.json'
        altered.write_text(json.dumps(report))
        with self.assertRaisesRegex(ValueError, 'Video differs'):
            prepare(self.session, altered, self.root / 'runs', 'smoke', 4)

    def test_smoke_not_calibration(self):
        with self.assertRaisesRegex(ValueError, 'cannot be used for calibration'):
            prepare(self.session, self.report, self.root / 'runs', 'calibration', 4)
        root = self.prepared()
        with self.assertRaisesRegex(ValueError, 'Smoke dataset'):
            calibrate(root, 'unused', {}, 'ds-none', .088, .3, 6, 6, True)

    def test_modified_pixels_rejected(self):
        root = self.prepared()
        p = root / 'left/00000000.pgm'
        data = p.read_bytes()
        p.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
        with self.assertRaisesRegex(ValueError, 'checksum'):
            write(root, 'rosbags')
        self.assertEqual(json.loads((root / 'bag_verification.json').read_text())['status'], 'FAILED')

    def test_bind_mount_boundary(self):
        info = {'Mounts': [{'Type': 'bind', 'RW': True, 'Source': '/home/key/data', 'Destination': '/data'}]}
        self.assertEqual(inner_path(Path('/home/key/data/run'), info), '/data/run')
        with self.assertRaisesRegex(ValueError, 'bind mount'):
            inner_path(Path('/home/key/database/run'), info)


if __name__ == '__main__':
    unittest.main()
