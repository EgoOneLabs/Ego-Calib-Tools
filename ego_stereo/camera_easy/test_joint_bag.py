import unittest
import numpy as np
from joint_bag import map_times


class JointTimeTests(unittest.TestCase):
    def test_counter_fit_preserves_missing_time_and_relative_image_clock(self):
        n=2800
        a=np.zeros(n,dtype=[('tick_index','i8'),('packet','i8'),('host_after_ns','i8')])
        ticks=np.arange(n);ticks[1400:]+=14
        a['tick_index']=ticks;a['packet']=np.arange(n)//14
        ends=np.minimum((np.arange(n)//14+1)*14-1,n-1)
        origin=1000000000000
        a['host_after_ns']=origin+ticks[ends]*1250000
        m={'selected_pairs':[{'timestamp_ns':1000000000},{'timestamp_ns':2000000000}]}
        im,imu,r=map_times(a,m,{'unix_ns':1000000000,'monotonic_ns':origin})
        self.assertEqual(list(im),[1000000000,2000000000])
        self.assertAlmostEqual(r['empirical_rate_hz'],800,places=6)
        self.assertEqual(int(imu[1400]-imu[1399]),15*1250000)
        self.assertFalse(r['sensor_values_interpolated'])
        self.assertFalse(r['hardware_sync_verified'])
        a['tick_index'][20]=a['tick_index'][19]
        with self.assertRaisesRegex(ValueError,'Non-increasing'):map_times(a,m,{'unix_ns':1000000000,'monotonic_ns':origin})
