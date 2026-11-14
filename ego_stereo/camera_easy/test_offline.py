import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import yaml
from core import sha
from offline import Offline, inventory


class OfflineTests(unittest.TestCase):
    def test_inventory_discovers_record_and_never_follows_outside_symlink(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            root=Path(directory);p=root/'camera_imu/2UQ2/record';p.mkdir(parents=True)
            for n in ('camera_manifest.json','imu_samples.csv','imu_capture.json','joint_clock.json','aprilgrid.yaml'):(p/n).write_text('{}')
            (p.parent/'escaped').symlink_to(outside,target_is_directory=True)
            datasets,_=inventory(root)
            self.assertEqual([a[0] for a in datasets.values()],[p])

    def test_parameter_catalog_separates_joint_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);p=root/'camera_imu/2UQ2/result';p.mkdir(parents=True)
            (p/'camera.yaml').write_text('cam0: {}\ncam1: {}\n')
            (p/'candidate.yaml').write_text('cam0: {T_cam_imu: [], timeshift_cam_imu: 0}\ncam1: {}\n')
            (p/'imu.yaml').write_text('gyroscope_noise_density: 0.1\n')
            (p/'large.yaml').write_text('x'*32769)
            _,params=inventory(root)
            self.assertEqual(sorted(x[1] for x in params.values()),['camera','candidate','imu'])

    def app(self,root,stage='READY'):
        return SimpleNamespace(lock=threading.RLock(),state={'stage':stage},data_root=root,
                               container='kalibr',docker=SimpleNamespace(kill_group=lambda *a:None))

    def test_recording_blocks_offline_work(self):
        with tempfile.TemporaryDirectory() as directory:
            job=Offline(self.app(Path(directory),'IMU_RECORDING'))
            with self.assertRaisesRegex(ValueError,'当前采集'):job.start({})
            self.assertIsNone(job.out)

    def test_requires_explicit_experimental_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            job=Offline(self.app(Path(directory)))
            with self.assertRaisesRegex(ValueError,'实验时间'):job.start({})
            self.assertIsNone(job.out)

    def test_unknown_dataset_cannot_inject_arbitrary_path(self):
        with tempfile.TemporaryDirectory() as directory:
            job=Offline(self.app(Path(directory)))
            with self.assertRaisesRegex(ValueError,'已有联合数据'):job.start(dict(experimental_ack=True,dataset='/etc'))

    def prepared_job(self,directory):
        root=Path(directory);source=root/'camera_imu/2UQ2/input';source.mkdir(parents=True)
        (source/'camera_imu_experimental.bag').write_bytes(b'fake-bag-for-orchestration-test')
        (source/'aprilgrid.yaml').write_text('target_type: aprilgrid\n')
        (source/'experimental_time_model.json').write_text('{}')
        verified=dict(status='EXPERIMENTAL_JOINT_BAG_READBACK_VERIFIED',bag_sha256=sha(source/'camera_imu_experimental.bag'),
                      all_image_pixels_verified=True,all_imu_values_verified=True,all_header_and_bag_times_verified=True)
        (source/'bag_verification.json').write_text(json.dumps(verified))
        job=Offline(self.app(root));job.out=source.parent/'fresh';job.out.mkdir();job.inner='/data/camera_imu/2UQ2/fresh'
        return job,source

    def test_successful_job_exports_report_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as directory:
            job,source=self.prepared_job(directory);before={p.name:p.read_bytes() for p in source.iterdir()}
            def command(shell):
                self.assertIn('kalibr_calibrate_imu_camera',shell)
                for name in ('joint-camchain-imucam.yaml','joint-results-imucam.txt'):(job.out/name).write_text('output')
                (job.out/'joint-report-imucam.pdf').write_bytes(b'%PDF-test')
            job.command=command
            job.worker(source,'prepared','calibrate','cam0: {}','gyroscope_noise_density: 1')
            self.assertEqual(job.state['stage'],'DONE')
            self.assertFalse(job.state['result']['quality_accepted'])
            self.assertTrue((job.out/'offline_review.tar.gz').is_file())
            self.assertEqual(before,{p.name:p.read_bytes() for p in source.iterdir()})

    def test_corrupt_bag_stops_before_solver_and_preserves_log_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            job,source=self.prepared_job(directory)
            (source/'camera_imu_experimental.bag').write_bytes(b'changed')
            def forbidden(*a):raise AssertionError('solver must not execute')
            job.command=forbidden
            job.worker(source,'prepared','calibrate','cam0: {}','x: 1')
            self.assertEqual(job.state['stage'],'FAILED')
            self.assertIn('BAG 校验',job.state['message'])
            self.assertTrue((job.out/'offline_review.tar.gz').exists())

    def test_fixed_validation_requires_lock_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            job,source=self.prepared_job(directory)
            def command(shell):
                self.assertIn('--no-time-calibration',shell)
                (job.out/'fixed_validation.json').write_text(json.dumps(dict(extrinsics_fixed=False,time_offsets_fixed=True)))
            job.command=command
            job.worker(source,'prepared','validate','cam0: {}','x: 1')
            self.assertEqual(job.state['stage'],'FAILED')
            self.assertIn('锁定',job.state['message'])


if __name__=='__main__':unittest.main()
