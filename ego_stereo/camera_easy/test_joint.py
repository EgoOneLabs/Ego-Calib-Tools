import csv
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
import yaml
from core import sha
from joint import inspect_capture, joint_motion, require_solver_inputs, save_inputs, validate_inputs

REFERENCE=Path(__file__).resolve().parents[1]/'reference/2uq2-ds-20261102/camera_4hz-camchain.yaml'
IMU={'rostopic':'/imu0','update_rate':800,'accelerometer_noise_density':.001,
     'accelerometer_random_walk':.0001,'gyroscope_noise_density':.0001,'gyroscope_random_walk':.00001}


class JointTests(unittest.TestCase):
    def test_capture_allowed_without_profiles_but_dependencies_explicit(self):
        status=validate_inputs()
        self.assertEqual(len(status['missing']),2)
        self.assertEqual(status['status'],'INPUTS_MISSING_CAPTURE_ALLOWED')
        with tempfile.TemporaryDirectory() as d:
            status=save_inputs(Path(d),REFERENCE.read_text(),yaml.safe_dump(IMU))
            self.assertFalse(status['quality_accepted'])
            self.assertEqual(status['missing'],[])
            self.assertEqual(status['input-camera.yaml_sha256'],sha(Path(d)/'input-camera.yaml'))

    def test_profile_camera_geometry_and_imu_parameters_checked(self):
        cam=yaml.safe_load(REFERENCE.read_text())
        for change in ('size','intrinsics','transform'):
            v=yaml.safe_load(yaml.safe_dump(cam))
            if change=='size':v['cam0']['resolution']=[640,480]
            elif change=='intrinsics':v['cam1']['intrinsics'][2]=float('nan')
            else:v['cam1']['T_cn_cnm1'][0][0]=2
            with self.assertRaises(ValueError):validate_inputs(yaml.safe_dump(v),'')
        for key in ('gyroscope_random_walk','update_rate'):
            imu=dict(IMU);imu[key]=0
            with self.assertRaises(ValueError):validate_inputs('',yaml.safe_dump(imu))

    def test_joint_records_raw_clock_evidence_without_sync_pass(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);base=10**12;unix=1794620000*10**9
            (root/'camera_manifest.json').write_text(json.dumps({'selected_pairs':[{'timestamp_ns':unix+i*100000000} for i in range(40)]}))
            (root/'imu_capture.json').write_text(json.dumps({'samples':3200,'errors':0,'gaps':1,'counter_discontinuities':0}))
            (root/'joint_clock.json').write_text(json.dumps({'unix_ns':unix,'monotonic_ns':base}))
            (root/'imu_samples.csv').write_text('fixture')
            (root/'imu_packets.bin').write_bytes(b'fixture')
            (root/'aprilgrid.yaml').write_text('fixture')
            save_inputs(root,'','')
            with (root/'imu_requests.csv').open('w',newline='') as f:
                w=csv.writer(f);w.writerow(['valid','unique_samples','host_before_ns','host_after_ns'])
                for i in range(300):w.writerow(['True',14,base+i*14000000,base+i*14000000+1000000])
            report=inspect_capture(root)
            self.assertFalse(report['ready_for_official_solver'])
            self.assertFalse(report['quality_accepted'])
            self.assertAlmostEqual(report['camera_mean_rate_hz'],10)
            self.assertGreater(report['host_interval_overlap_seconds'],3)
            self.assertTrue((root/'camera_imu_small_review.tar.gz').is_file())

    def test_solver_refuses_missing_or_unmatched_review_before_running(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with self.assertRaisesRegex(ValueError,'缺少'):require_solver_inputs(root)
            for name,content in [('camera_imu.bag','fixture'),('input-camera.yaml',REFERENCE.read_text()),('input-imu.yaml',yaml.safe_dump(IMU)),('aprilgrid.yaml','fixture'),('time_review.json','{}')]:
                (root/name).write_text(content)
            with self.assertRaisesRegex(ValueError,'尚未复核'):require_solver_inputs(root)
            review={'status':'JOINT_TIME_AXIS_REVIEWED','reviewer':'test-fixture','evidence':['fixture'],'imu_intrinsics_corrected':True,
              'sha256':{n:sha(root/n) for n in ('camera_imu.bag','input-camera.yaml','input-imu.yaml','aprilgrid.yaml')}}
            (root/'time_review.json').write_text(json.dumps(review))
            require_solver_inputs(root)
            (root/'camera_imu.bag').write_text('changed')
            with self.assertRaisesRegex(ValueError,'不匹配'):require_solver_inputs(root)

    def test_joint_start_sets_shared_run_and_keeps_missing_inputs_visible(self):
        from app import App
        with tempfile.TemporaryDirectory() as d:
            app=App.__new__(App);app.lock=threading.RLock();app.imu_thread=None
            app.state={'stage':'READY'};app.frame_ns=time.monotonic_ns();app.data_root=Path(d)
            app.hardware={'device':'/dev/not-used'};app.clock_anchor={'unix_ns':10**18,'monotonic_ns':10**12}
            app.end_capture=threading.Event();app.imu_cancel=threading.Event();app.joint_frames_done=threading.Event()
            app.persist=lambda:None
            with patch('app.threading.Thread') as thread, patch('app.shutil.disk_usage',return_value=SimpleNamespace(free=10**12)):
                app.start({'mode':'camera_imu','device_id':'test','joint_seconds':90,
                           'board':{'rows':6,'cols':6,'tag_mm':88,'gap_mm':26.4}})
                self.assertEqual(app.state['stage'],'JOINT_RECORDING')
                self.assertEqual(app.store.sample_hz,10)
                self.assertEqual(len(json.loads((app.run/'joint_dependencies.json').read_text())['missing']),2)
                thread.return_value.start.assert_called_once()

    def test_guidance_keeps_board_fixed_and_includes_three_axis_motion(self):
        self.assertIn('板固定',joint_motion(0,90))
        self.assertIn('侧倾',joint_motion(40,90))
        self.assertIn('移动',joint_motion(65,90))
