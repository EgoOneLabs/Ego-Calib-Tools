from pathlib import Path
import tempfile
import unittest
import numpy as np
from diagnose import motion_metrics,skew,review_record


class DiagnosticTests(unittest.TestCase):
    def data(self,n=1000):
        d=np.zeros(n,dtype=[('tick_index','i8'),('segment','i8'),('gx_rad_s','f8'),('gy_rad_s','f8'),('gz_rad_s','f8')])
        d['tick_index']=np.arange(n);return d

    def test_skew_matches_cross_product(self):
        a=np.array([1.,2,3]);b=np.array([4.,5,6]);np.testing.assert_allclose(skew(a)@b,np.cross(a,b))

    def test_static_motion_has_zero_lever_arm_sensitivity(self):
        out=motion_metrics(self.data(),100,np.array([.01,.02,.03]),.1)
        self.assertEqual(out['delta_r_only_acceleration_change_m_s2']['rms'],0)
        self.assertIsNone(out['sensitivity_ratio_min_over_max'])

    def test_constant_single_axis_rotation_has_expected_centripetal_response(self):
        d=self.data();d['gz_rad_s']=2
        out=motion_metrics(d,100,np.array([.01,0,0]),.1)
        self.assertAlmostEqual(out['delta_r_only_acceleration_change_m_s2']['rms'],.04)
        self.assertEqual(out['sensitivity_ratio_min_over_max'],0)

    def test_no_derivative_is_taken_across_a_sample_gap(self):
        d=self.data(400);d['gz_rad_s'][200:]=100;d['tick_index'][200:]+=500;d['segment'][200:]=1
        out=motion_metrics(d,100,np.array([0,0,.01]),.1)
        self.assertEqual(out['delta_r_only_acceleration_change_m_s2']['rms'],0)
        self.assertEqual(out['usable_centers'],36)

    def test_short_segments_do_not_become_interpolated_motion(self):
        d=self.data(20);d['segment']=np.arange(20)//2
        out=motion_metrics(d,100,np.array([.01,0,0]),.1)
        self.assertEqual(out['status'],'INSUFFICIENT_CONTIGUOUS_DATA')


if __name__=='__main__':unittest.main()
