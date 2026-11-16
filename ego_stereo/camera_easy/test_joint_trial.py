from pathlib import Path
import tempfile
import unittest
import yaml
from joint_trial import check_outputs, SCRIPT


class TrialTests(unittest.TestCase):
    def test_output_completeness_and_finite_time_required(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with self.assertRaisesRegex(ValueError,'缺少'):check_outputs(root)
            m=[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]
            result={k:{'T_cam_imu':m,'timeshift_cam_imu':.001} for k in ['cam0','cam1']}
            (root/'camera_imu_experimental-camchain-imucam.yaml').write_text(yaml.safe_dump(result))
            (root/'camera_imu_experimental-report-imucam.pdf').write_bytes(b'%PDF-fixture')
            (root/'camera_imu_experimental-results-imucam.txt').write_text('fixture')
            self.assertEqual(len(check_outputs(root)['output_sha256']),3)
            result['cam1']['timeshift_cam_imu']=float('nan')
            (root/'camera_imu_experimental-camchain-imucam.yaml').write_text(yaml.safe_dump(result))
            with self.assertRaisesRegex(ValueError,'时间偏移'):check_outputs(root)

    def test_legacy_solver_options_keep_chain_and_do_not_forge_review(self):
        self.assertIn('--cams',SCRIPT)
        self.assertIn('--dont-show-report',SCRIPT)
        self.assertNotIn('--recompute-camera-chain-extrinsics',SCRIPT)
        self.assertNotIn('--timeoffset',SCRIPT)
        self.assertNotIn('time_review.json',SCRIPT)
