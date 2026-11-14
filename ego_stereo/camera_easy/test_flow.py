import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
from parameters import Parameters


class FlowTests(unittest.TestCase):
    def test_parameter_reuse_is_per_device_and_rejects_changed_content(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'camera.yaml';p.write_text('cam0: {}')
            store=Parameters(root/'settings.json');store.remember('2UQ2','camera',p)
            self.assertEqual(store.defaults('2UQ2')['camera']['text'],'cam0: {}')
            self.assertEqual(store.defaults('OTHER'),{})
            p.write_text('different')
            self.assertEqual(store.defaults('2UQ2'),{})

    def test_parameter_reuse_survives_restart_and_missing_file(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'imu.yaml';p.write_text('noise: 1')
            store=Parameters(root/'settings.json');store.remember('2UQ2','imu',p)
            self.assertIn('imu',Parameters(root/'settings.json').defaults('2UQ2'))
            p.unlink();self.assertEqual(store.defaults('2UQ2'),{})

    def test_automatic_joint_requires_both_parameters_before_recording(self):
        from app import App
        app=App.__new__(App)
        with self.assertRaisesRegex(ValueError,'第三步需要'):
            app.start_joint(dict(device_id='2UQ2',board=dict(rows=6,cols=6,tag_mm=88,gap_mm=26.4),
                                 joint_seconds=90,auto_calculate=True,experimental_ack=True))

    def test_completed_record_hands_off_its_own_data_and_inputs(self):
        from app import App
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);run=root/'camera_imu/2UQ2/record';run.mkdir(parents=True)
            (run/'input-camera.yaml').write_text('camera-selected')
            (run/'input-imu.yaml').write_text('imu-selected')
            app=App.__new__(App);app.lock=threading.RLock();app.state={};app.hardware={'device':'fixture'}
            app.imu_cancel=threading.Event();app.end_capture=threading.Event();app.stop=threading.Event()
            app.joint_frames_done=threading.Event();app.joint_frames_done.set();app.data_root=root
            app.persist=lambda:None;app.update=lambda stage,message:app.state.update(stage=stage,message=message)
            app.offline=SimpleNamespace(start=Mock())
            with patch('app.capture_imu'),patch('app.inspect_capture',return_value={'status':'captured'}):
                app.joint_loop(run,90,True)
            args=app.offline.start.call_args.args[0]
            self.assertEqual(args['action'],'calibrate')
            self.assertEqual(args['camera_yaml'],'camera-selected')
            self.assertEqual(args['imu_yaml'],'imu-selected')
            self.assertTrue(args['experimental_ack'])
            self.assertEqual(app.state['stage'],'DONE')

    def test_controls_and_guidance_are_inside_sticky_preview_card(self):
        html=Path(__file__).with_name('web.html').read_text()
        card=html.split('<section id="capture_panel">',1)[1].split('</section>',1)[0]
        for token in ['class="preview"','id="start"','id="finish"','id="message"','id="progress"']:
            self.assertIn(token,card)
        self.assertIn('#capture_panel{position:sticky',html)
        separate=Path(__file__).with_name('offline.html').read_text()
        self.assertIn('<details id="offline_panel" hidden>',separate)
        self.assertNotIn('<details id="offline_panel" open',separate)


if __name__=='__main__':unittest.main()
