import copy
import unittest
from pathlib import Path
import sys
import numpy as np

sys.path.insert(0,str(Path(__file__).parent))
from fixed_check import candidate_values, check_locked, residual_summary


class Variable:
    def __init__(self,active=False): self.active=active
    def isActive(self): return self.active


class Transform:
    def __init__(self,T):self.value=T
    def T(self):return self.value
    def numDesignVariables(self):return 2
    def getDesignVariable(self,k):return self.variables[k]


class TestFixedCheck(unittest.TestCase):
    def setUp(self):
        T=np.eye(4);B=np.eye(4);B[0,3]=-.09
        self.data={'cam0':dict(T_cam_imu=T.tolist(),timeshift_cam_imu=-.048),
                   'cam1':dict(T_cam_imu=B.tolist(),T_cn_cnm1=B.tolist(),timeshift_cam_imu=-.049)}
        self.values=candidate_values(self.data)

    def chain(self):
        class Object:pass
        chain=Object();chain.camList=[]
        for T,shift in self.values:
            cam=Object();cam.T_c_b_Dv=Transform(T.copy());cam.T_c_b_Dv.variables=[Variable(),Variable()]
            cam.cameraTimeToImuTimeDv=Variable();chain.camList.append(cam)
        chain.getResultTrafoImuToCam=lambda i:chain.camList[i].T_c_b_Dv
        chain.getResultTimeShift=lambda i:self.values[i][1]
        return chain

    def test_accept_consistent_rigid_candidate(self):
        check_locked(self.chain(),self.values)

    def test_reject_inconsistent_baseline(self):
        d=copy.deepcopy(self.data);d['cam1']['T_cam_imu'][1][3]=.01
        with self.assertRaises(ValueError):candidate_values(d)

    def test_reject_nonrotation(self):
        d=copy.deepcopy(self.data);d['cam0']['T_cam_imu'][0][0]=2
        with self.assertRaises(ValueError):candidate_values(d)

    def test_reject_active_extrinsic(self):
        c=self.chain();c.camList[0].T_c_b_Dv.variables[0].active=True
        with self.assertRaises(ValueError):check_locked(c,self.values)

    def test_reject_active_time(self):
        c=self.chain();c.camList[1].cameraTimeToImuTimeDv.active=True
        with self.assertRaises(ValueError):check_locked(c,self.values)

    def test_reject_moved_translation(self):
        c=self.chain();c.camList[0].T_c_b_Dv.value[2,3]+=.001
        with self.assertRaises(ValueError):check_locked(c,self.values)

    def test_reject_changed_time(self):
        c=self.chain();c.getResultTimeShift=lambda i:self.values[i][1]+.001
        with self.assertRaises(ValueError):check_locked(c,self.values)

    def test_physical_residual_norm_statistics(self):
        class Error:
            def __init__(self,x):self.x=x
            def error(self):return self.x
        class Object:pass
        cal=Object();cal.CameraChain=Object();cam=Object();cam.allReprojectionErrors=[[Error([3,4]),Error([0,0])]]
        cal.CameraChain.camList=[cam];imu=Object();imu.gyroErrors=[Error([0,.1,0])];imu.accelErrors=[Error([0,0,.2])];cal.ImuList=[imu]
        stats=residual_summary(cal)
        self.assertEqual(stats['cam0_px']['mean'],2.5)
        self.assertAlmostEqual(stats['cam0_px']['rms'],np.sqrt(12.5))
        self.assertAlmostEqual(stats['gyro_rad_s']['mean'],.1)


if __name__=='__main__':unittest.main()
