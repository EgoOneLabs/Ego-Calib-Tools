"""Conditional held-out consistency check: extrinsics and time offsets stay fixed.

Trajectory, gravity direction and IMU bias splines are nuisance variables fitted
on the evaluation record. This is not open-loop prediction or hardware sync proof.
Only process-local adapters are installed; installed Kalibr files are untouched.
"""
import hashlib
import json
from pathlib import Path
import runpy
import sys

import numpy as np
import yaml


def candidate_values(data):
    values = []
    for key in ('cam0', 'cam1'):
        cam = data[key]
        T = np.asarray(cam['T_cam_imu'], dtype=float)
        shift = float(cam['timeshift_cam_imu'])
        if T.shape != (4, 4) or not np.isfinite(T).all() or not np.isfinite(shift):
            raise ValueError('Invalid candidate transform or time offset')
        if not np.allclose(T[3], [0, 0, 0, 1], atol=1e-10, rtol=0):
            raise ValueError('Invalid homogeneous transform')
        if not np.allclose(T[:3,:3].T @ T[:3,:3], np.eye(3), atol=1e-8, rtol=0) or abs(np.linalg.det(T[:3,:3])-1)>1e-8:
            raise ValueError('Invalid rotation')
        values.append((T, shift))
    baseline = np.asarray(data['cam1']['T_cn_cnm1'], dtype=float)
    if not np.allclose(baseline @ values[0][0], values[1][0], atol=1e-9, rtol=0):
        raise ValueError('Candidate transforms disagree with stereo baseline')
    return values


def check_locked(chain, values):
    for cam, (T, shift), i in zip(chain.camList, values, range(2)):
        for k in range(cam.T_c_b_Dv.numDesignVariables()):
            if cam.T_c_b_Dv.getDesignVariable(k).isActive():
                raise ValueError('Extrinsic design variable is active')
        if cam.cameraTimeToImuTimeDv.isActive():
            raise ValueError('Time-offset design variable is active')
        if not np.allclose(chain.getResultTrafoImuToCam(i).T(), T, atol=1e-10, rtol=0):
            raise ValueError('Candidate extrinsic changed')
        if abs(chain.getResultTimeShift(i)-shift)>1e-12:
            raise ValueError('Candidate time offset changed')


def residual_summary(cal):
    def stats(errors):
        norms=np.asarray([np.linalg.norm(e.error()) for e in errors], dtype=float)
        if not len(norms) or not np.isfinite(norms).all():
            raise ValueError('Missing or nonfinite evaluation residuals')
        return dict(count=len(norms), mean=float(norms.mean()), rms=float(np.sqrt(np.mean(norms**2))), p95=float(np.percentile(norms,95)))
    result={}
    for i, cam in enumerate(cal.CameraChain.camList):
        result['cam%d_px'%i]=stats([e for group in cam.allReprojectionErrors for e in group])
    result['gyro_rad_s']=stats(cal.ImuList[0].gyroErrors)
    result['accel_m_s2']=stats(cal.ImuList[0].accelErrors)
    return result


def main():
    import sm
    from kalibr_imu_camera_calibration import IccCalibrator, sens
    root=Path('/catkin_ws/src/kalibr/aslam_offline_calibration/kalibr/python')
    expected=json.loads((Path(__file__).parent/'kalibr_hashes.json').read_text())
    for name, digest in expected.items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Kalibr source version differs: '+name)
    # Also ensure Python imports the reviewed sources, rather than another install.
    if Path(sens.__file__).with_suffix('.py').read_bytes() != (root/'kalibr_imu_camera_calibration/IccSensors.py').read_bytes():
        raise ValueError('Imported sensor implementation differs')
    candidate=Path(sys.argv.pop(1)).resolve()
    data=yaml.safe_load(candidate.read_text()); values=candidate_values(data)

    def fixed_prior(chain, imu):
        if len(chain.camList)!=2:
            raise ValueError('Expected two cameras')
        chain.camList[0].T_extrinsic=sm.Transformation(values[0][0])
        for cam, (_, shift) in zip(chain.camList,values):
            cam.timeshiftCamToImuPrior=shift
        # With the candidate already applied, the pose spline is T_world_imu.
        # Estimate only the nuisance gravity direction; do not refit rotation.
        pose=chain.camList[0].initPoseSplineFromCamera(timeOffsetPadding=0.0)
        samples=[np.asarray(pose.orientation(im.stamp.toSec()) @ (-im.alpha)).reshape(3)
                 for im in imu.imuData if pose.t_min()<im.stamp.toSec()<pose.t_max()]
        gravity=np.mean(samples,axis=0)
        if not len(samples) or not np.isfinite(gravity).all() or np.linalg.norm(gravity)<1:
            raise ValueError('Cannot initialize gravity')
        chain.camList[0].gravity_w=gravity/np.linalg.norm(gravity)*9.80655

    def fixed_design(chain, problem, noTimeCalibration=True, noChainExtrinsics=True):
        if not noTimeCalibration or not noChainExtrinsics:
            raise ValueError('Fixed check requires time and chain calibration disabled')
        for cam in chain.camList:
            cam.addDesignVariables(problem, noExtrinsics=True, noTimeCalibration=True, baselinedv_group_id=1)

    original_optimize=IccCalibrator.optimize
    def guarded_optimize(cal, *args, **kwargs):
        check_locked(cal.CameraChain,values)
        original_optimize(cal,*args,**kwargs)
        check_locked(cal.CameraChain,values)
        report=dict(status='FIXED_CANDIDATE_CONDITIONAL_CHECK_COMPLETE',
                    extrinsics_fixed=True,time_offsets_fixed=True,
                    nuisance_variables_fitted=['trajectory','gravity_direction','imu_bias_splines'],
                    hardware_sync_verified=False,quality_accepted=False,
                    candidate_sha256=hashlib.sha256(candidate.read_bytes()).hexdigest(),
                    residuals=residual_summary(cal))
        Path('fixed_validation.json').write_text(json.dumps(report,indent=2)+'\n')
        print('Fixed candidate values verified unchanged before and after optimization.')

    sens.IccCameraChain.findOrientationPriorCameraChainToImu=fixed_prior
    sens.IccCameraChain.addDesignVariables=fixed_design
    IccCalibrator.optimize=guarded_optimize
    if '--no-time-calibration' not in sys.argv:
        raise ValueError('Missing --no-time-calibration')
    runpy.run_path(str(root/'kalibr_calibrate_imu_camera'),run_name='__main__')


if __name__=='__main__':
    main()
