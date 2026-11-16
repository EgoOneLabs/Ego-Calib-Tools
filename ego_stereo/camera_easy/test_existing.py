import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
from camera_bag_check import check
from offline import Offline,inventory,identity


class ExistingTests(unittest.TestCase):
    def fixture(self,root,kind):
        source=root/('camera_easy' if kind=='camera' else 'imu')/'2UQ2/record';source.mkdir(parents=True)
        names=['camera.bag'] if kind=='camera' else ['imu_samples.csv','imu_capture.json']
        for name in names:(source/name).write_text('original-'+name)
        app=SimpleNamespace(lock=threading.RLock(),state={'stage':'FAILED'},data_root=root,container='test',
                            info={'Image':'fixture'},docker=SimpleNamespace(kill_group=Mock()),parameters=SimpleNamespace(remember=Mock()))
        return source,Offline(app)

    def test_camera_and_imu_start_without_other_module_parameters_or_experimental_ack(self):
        for kind in ['camera','imu']:
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as d:
                root=Path(d);source,job=self.fixture(root,kind)
                args=dict(action=kind,dataset=identity(root,source),device_id='2UQ2',board=dict(rows=6,cols=6,tag_mm=88,gap_mm=26.4))
                with patch('offline.threading.Thread') as thread:job.start(args)
                self.assertEqual(thread.call_args.kwargs['target'],job.worker_single)
                self.assertEqual(job.state['action'],kind)

    def test_wrong_module_and_escaped_input_are_rejected(self):
        with tempfile.TemporaryDirectory() as d,tempfile.TemporaryDirectory() as escaped:
            root=Path(d);source,job=self.fixture(root,'camera')
            with self.assertRaisesRegex(ValueError,'不一致'):
                job.start(dict(action='imu',dataset=identity(root,source),device_id='2UQ2'))
            (source/'camera.bag').unlink();(Path(escaped)/'secret').write_text('outside')
            (source/'camera.bag').symlink_to(Path(escaped)/'secret')
            self.assertEqual(inventory(root)[0],{})

    def test_camera_recalculation_uses_existing_bag_and_preserves_original(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source,job=self.fixture(root,'camera');before=(source/'camera.bag').read_bytes()
            job.out=source.parent/'fresh';job.out.mkdir();job.inner='/data/fresh'
            def calculate(*args,**kwargs):
                self.assertTrue(kwargs['existing']);self.assertEqual((args[0]/'camera.bag').read_bytes(),before)
                (job.out/'camera-camchain.yaml').write_text('cam0: {}')
                args[-1]('calibration progress fixture')
                return {'quality_accepted':False}
            with patch('offline.calculate',side_effect=calculate):
                job.worker_single(source,'camera','2UQ2',dict(target_type='aprilgrid'))
            self.assertEqual(job.state['stage'],'DONE');self.assertIn('calibration progress fixture',job.public()['logs'])
            self.assertIn('camera-camchain.yaml',job.public()['files'])
            self.assertEqual((source/'camera.bag').read_bytes(),before)
            self.assertTrue((job.out/'offline_review.tar.gz').is_file())

    def test_imu_reanalysis_does_not_request_camera_inputs(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source,job=self.fixture(root,'imu')
            job.out=source.parent/'fresh';job.out.mkdir();job.inner='/data/fresh'
            def analyze(out,**kwargs):
                self.assertFalse((out/'camera.yaml').exists());self.assertTrue((out/'imu_samples.csv').exists())
                (out/'imu-results.txt').write_text('analysis fixture');return {'status':'REVIEW_PENDING'}
            with patch('offline.analyze_imu',side_effect=analyze):job.worker_single(source,'imu','2UQ2',None)
            self.assertEqual(job.state['stage'],'DONE');self.assertIn('imu-results.txt',job.public()['files'])

    def test_existing_bag_reads_images_and_rejects_timestamp_reversal(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'camera.bag').write_bytes(b'fixture')
            reversed_clock=False
            class Stream:
                def __enter__(self):return self
                def __exit__(self,*args):pass
                def read_messages(self,topics):
                    for i in range(40):
                        for topic in topics:
                            stamp=i+1 if not reversed_clock or i<30 else 1
                            yield topic,SimpleNamespace(_type='sensor_msgs/Image',width=2,height=1,step=2,data=b'12',encoding='mono8',
                                      header=SimpleNamespace(stamp=SimpleNamespace(to_nsec=lambda n=stamp:n))),None
            result=check(root,lambda *a:Stream());self.assertEqual(result['counts']['/cam0/image_raw'],40)
            self.assertFalse(result['original_pixels_verified_against_manifest'])
            reversed_clock=True
            with self.assertRaisesRegex(ValueError,'回跳'):check(root,lambda *a:Stream())


if __name__=='__main__':unittest.main()
