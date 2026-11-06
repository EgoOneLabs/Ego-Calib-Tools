import unittest
import numpy as np
from audit_core import cross_residuals,coverage,stats

class Pose:
    def __init__(self,m):self.m=np.asarray(m)
    def inverse(self):return Pose(np.linalg.inv(self.m))
    def __mul__(self,other):return Pose(self.m@other.m)
    def C(self):return self.m[:3,:3]
    def t(self):return self.m[:3,3]
class Camera:
    def euclideanToKeypoint(self,p):return 100*np.asarray(p)[:2]/p[2]
class Observation:
    def __init__(self,xyz,uv,ids,target_to_camera):self.xyz=xyz;self.uv=uv;self.ids=ids;self.pose=Pose(target_to_camera)
    def getCornersIdx(self):return self.ids
    def getCornersTargetFrame(self):return self.xyz
    def getCornersImageFrame(self):return self.uv
    def T_t_c(self):return self.pose.inverse()

class Tests(unittest.TestCase):
    def test_fixed_baseline_direction_and_common_id_alignment(self):
        m=np.eye(4);m[0,3]=-.1
        xyz=np.array([[0,0,1],[.1,.1,2],[.2,-.1,1]])
        g=Camera();uv0=np.array([g.euclideanToKeypoint(p) for p in xyz]);uv1=np.array([g.euclideanToKeypoint(p+m[:3,3]) for p in xyz])
        a=Observation(xyz,uv0,[7,2,9],np.eye(4));b=Observation(xyz[[2,0]],uv1[[2,0]],[9,7],m)
        forward=cross_residuals(a,b,g,Pose(m));backward=cross_residuals(b,a,g,Pose(m).inverse())
        self.assertEqual([r[0] for r in forward],[7,9])
        self.assertLess(stats([r[3] for r in forward+backward])['max_l2_px'],1e-10)
        wrong=cross_residuals(a,b,g,Pose(m).inverse())
        self.assertGreater(stats([r[3] for r in wrong])['rms_l2_px'],10)
    def test_signed_mean_is_not_rms(self):
        r=stats([[3,4],[-3,-4]])
        self.assertEqual(r['mean_xy_px'],[0,0]);self.assertEqual(r['rms_l2_px'],5)
        self.assertEqual(stats([]),{'count':0})
    def test_coverage_boundary_outside_and_invalid(self):
        grid,out=coverage([[0,0],[1919,1079],[1920,500],[-1,0]],1920,1080)
        self.assertEqual(grid.sum(),2);self.assertEqual(grid[0,0],1);self.assertEqual(grid[-1,-1],1);self.assertEqual(out,2)
        with self.assertRaises(ValueError):coverage([[np.nan,0]],1920,1080)
    def test_nonfinite_not_silently_dropped(self):
        with self.assertRaises(ValueError):stats([[np.inf,1]])

if __name__=='__main__':unittest.main()
