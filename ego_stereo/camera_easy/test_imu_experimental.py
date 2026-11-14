import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from imu_experimental import fit, generate


class ExperimentalTests(unittest.TestCase):
    def test_known_mixture_and_unit_scaling(self):
        tau=np.geomspace(.2,65,80)
        n,p,k=.0012,.0004,.00015
        adev=np.sqrt(n*n/tau+p*p+k*k*tau/3)
        a,b=fit(tau,adev),fit(tau,adev*100)
        for key,truth in [('N',n),('plateau',p),('K',k)]:
            self.assertAlmostEqual(a[key]/truth,1,places=5)
            self.assertAlmostEqual(b[key]/a[key],100,places=4)

    def test_output_is_experimental_preserves_strict_analysis_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            source=json.dumps({'estimated_sample_rate_hz':809.4,'quality_accepted':False,'missing_noise_terms':['gyro_z']})
            (root/'imu-analysis.json').write_text(source)
            tau=np.geomspace(.2,65,40)
            dev=np.sqrt(.001**2/tau+.0003**2+.0001**2*tau/3)
            np.savetxt(root/'imu-allan.csv',np.column_stack([tau,*[dev]*6,np.ones(40)*1000]),delimiter=',',header='tau_s,ax,ay,az,gx,gy,gz,differences_used',comments='')
            r=generate(root)
            self.assertFalse(r['quality_accepted'])
            self.assertFalse(r['ready_for_camera_imu'])
            self.assertEqual((root/'imu-analysis.json').read_text(),source)
            self.assertIn('EXPERIMENTAL',(root/'imu-experimental.yaml').read_text())
            with self.assertRaisesRegex(ValueError,'已经存在'):generate(root)

    def test_short_curve_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'imu-analysis.json').write_text('{"estimated_sample_rate_hz":809}')
            np.savetxt(root/'imu-allan.csv',np.ones((3,8)),delimiter=',',header='tau_s,ax,ay,az,gx,gy,gz,differences_used',comments='')
            with self.assertRaisesRegex(ValueError,'不足'):generate(root)
