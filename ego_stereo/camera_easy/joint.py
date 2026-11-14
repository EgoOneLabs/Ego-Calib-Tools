"""Joint capture dependency checks and guarded official Kalibr invocation."""
import csv
import json
from pathlib import Path
import re
import shutil
import tarfile
import time

import numpy as np
import yaml
from core import WIDTH, HEIGHT, require, sha
from environment import ROS_ENV
from pipeline import logged_run


def joint_motion(elapsed,duration):
    phase=elapsed/duration
    if phase<.1:return '标定板固定不动，拿稳整套头环，先保持静止。'
    if phase<.35:return '缓慢左右摇头，再上下点头；让板在左右画面中清晰可见。'
    if phase<.6:return '增加左右侧倾，改变旋转速度；不要只绕一个轴转动。'
    if phase<.9:return '轻柔组合旋转，附带少量前后、左右移动。避免抖动和运动模糊。'
    return '保持板可见，逐渐恢复静止；板和相机/IMU的固定关系不变。'


def validate_inputs(camera_text='',imu_text=''):
    status={'camera_present':bool(camera_text),'imu_present':bool(imu_text),
            'missing':[],'quality_accepted':False}
    if not camera_text:status['missing'].append('Camera 相机参数 YAML')
    else:
        require(len(camera_text.encode())<=32768,'相机 YAML 过大')
        camera=yaml.safe_load(camera_text)
        require(isinstance(camera,dict) and 'cam0' in camera and 'cam1' in camera,'相机 YAML 缺少 cam0/cam1')
        for i in range(2):
            c=camera[f'cam{i}']
            require(c.get('camera_model')=='ds' and c.get('distortion_model')=='none','请选择本工具 DS 相机标定输出')
            require(c.get('resolution')==[WIDTH//2,HEIGHT] and c.get('rostopic')==f'/cam{i}/image_raw','相机分辨率或左右话题不匹配')
            intr=np.asarray(c.get('intrinsics'),dtype=float)
            require(intr.shape==(6,) and np.isfinite(intr).all() and 0<intr[1]<1 and np.all(intr[2:4]>0),'相机内参无效')
        t=np.asarray(camera['cam1'].get('T_cn_cnm1'),dtype=float)
        require(t.shape==(4,4) and np.isfinite(t).all() and np.allclose(t[3],[0,0,0,1]),'双目外参格式错误')
        r=t[:3,:3]
        require(np.allclose(r.T@r,np.eye(3),atol=.001) and abs(np.linalg.det(r)-1)<.001,'双目旋转矩阵无效')
        require(np.linalg.norm(t[:3,3])>0,'双目基线无效')
    if not imu_text:status['missing'].append('IMU 噪声参数 YAML')
    else:
        require(len(imu_text.encode())<=32768,'IMU YAML 过大')
        imu=yaml.safe_load(imu_text)
        require(isinstance(imu,dict),'IMU YAML 格式错误')
        for k in ('accelerometer_noise_density','accelerometer_random_walk','gyroscope_noise_density','gyroscope_random_walk','update_rate'):
            value=float(imu.get(k,float('nan')))
            require(np.isfinite(value) and value>0,'IMU 参数缺失或无效：'+k)
        require(imu.get('rostopic')=='/imu0','IMU 话题应为 /imu0')
    status['status']='INPUTS_PRESENT_REVIEW_PENDING' if not status['missing'] else 'INPUTS_MISSING_CAPTURE_ALLOWED'
    status['next']='可先录制。联合计算前需要同一套头环的已复核参数、标定板配置和图像/IMU时间轴检查。'
    return status


def save_inputs(root,camera_text,imu_text):
    status=validate_inputs(camera_text,imu_text)
    for name,text in [('input-camera.yaml',camera_text),('input-imu.yaml',imu_text)]:
        if text:
            (root/name).write_text(text)
            status[name+'_sha256']=sha(root/name)
    (root/'joint_dependencies.json').write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n')
    return status


def pack_review(root):
    path=root/'camera_imu_small_review.tar.gz'
    with tarfile.open(path,'w:gz') as tar:
        for f in sorted(root.iterdir()):
            if f.is_file() and f.suffix in ('.json','.yaml','.pdf','.txt','.log','.sh') and f.name not in ('imu_samples.csv','imu_requests.csv'):
                tar.add(f,arcname=f.name)
    return path


def inspect_capture(root):
    root=Path(root)
    manifest=json.loads((root/'camera_manifest.json').read_text())
    capture=json.loads((root/'imu_capture.json').read_text())
    clock=json.loads((root/'joint_clock.json').read_text())
    pairs=manifest['selected_pairs']
    require(len(pairs)>=40 and capture['samples']>=100,'联合采集图像或 IMU 样本不足')
    frames=np.asarray([p['timestamp_ns'] for p in pairs],dtype=np.int64)
    require(np.all(np.diff(frames)>0),'图像时间不递增')
    # Retain packet-level host clocks and counters. Do not expand packet times
    # into fictitious simultaneous or interpolated physical sample times.
    packets=[]
    with (root/'imu_requests.csv').open() as f:
        for row in csv.DictReader(f):
            if row['valid']=='True' and int(row['unique_samples'])>0:
                packets.append((int(row['host_before_ns']),int(row['host_after_ns'])))
    require(len(packets)>10,'有效 IMU 请求不足')
    p=np.asarray(packets,dtype=np.int64)
    host_video=frames-clock['unix_ns']+clock['monotonic_ns']
    overlap=max(0,min(int(host_video[-1]),int(p[-1,1]))-max(int(host_video[0]),int(p[0,0])))/1e9
    require(overlap>2,'图像与 IMU 的主机时间区间重叠不足')
    dependencies=json.loads((root/'joint_dependencies.json').read_text())
    issues=list(dependencies['missing'])
    if capture['counter_discontinuities']:issues.append('IMU 计数器回跳，需要检查')
    issues.append('图像曝光与 IMU 逐样本时间轴尚待验证；主机接收时间不是硬件同步证明')
    report={'status':'JOINT_CAPTURED_TIMING_REVIEW_PENDING','camera_pairs':len(pairs),
        'camera_mean_rate_hz':float((len(frames)-1)*1e9/(int(frames[-1])-int(frames[0]))),
        'imu_samples':capture['samples'],'imu_read_errors':capture['errors'],'imu_gaps':capture['gaps'],
        'host_interval_overlap_seconds':overlap,'request_latency_p95_ms':float(np.quantile((p[:,1]-p[:,0])/1e6,.95)),
        'missing_or_pending':issues,'ready_for_official_solver':False,'quality_accepted':False,
        'raw_inputs':{name:sha(root/name) for name in ('camera_manifest.json','imu_samples.csv','imu_packets.bin','imu_requests.csv','joint_clock.json','aprilgrid.yaml')}}
    (root/'joint_capture.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    (root/'camera_imu-results.txt').write_text('Status: '+report['status']+'\nCamera pairs: '+str(len(pairs))+'\nIMU samples: '+str(capture['samples'])+'\nPending: '+'; '.join(issues)+'\n',encoding='utf-8')
    pack_review(root)
    return report


def require_solver_inputs(root):
    """Only verified data may enter the official solver; never fake a pass."""
    root=Path(root)
    for name in ('camera_imu.bag','input-camera.yaml','input-imu.yaml','aprilgrid.yaml','time_review.json'):
        require((root/name).is_file() and (root/name).stat().st_size>0,'联合计算缺少文件：'+name)
    validate_inputs((root/'input-camera.yaml').read_text(),(root/'input-imu.yaml').read_text())
    review=json.loads((root/'time_review.json').read_text())
    require(review.get('status')=='JOINT_TIME_AXIS_REVIEWED' and review.get('reviewer') and review.get('evidence'),
            '联合时间轴尚未复核，不运行正式求解')
    for name in ('camera_imu.bag','input-camera.yaml','input-imu.yaml','aprilgrid.yaml'):
        require(review.get('sha256',{}).get(name)==sha(root/name),'时间轴复核记录与输入不匹配：'+name)
    require(review.get('imu_intrinsics_corrected') is True,'需要确认 IMU 比例和轴不正交修正，或另行验证对应估计模型')
    return review


def calculate_joint(root,docker,container,data_root,stop,update,notify):
    root=Path(root)
    require_solver_inputs(root)
    inner='/data/'+root.relative_to(data_root).as_posix()
    started=time.monotonic()
    state={'status':'JOINT_CALIBRATION_RUNNING','quality_accepted':False}
    try:
        update('JOINT_CALIBRATING','正在运行官方 Camera–IMU 联合计算…')
        shell=ROS_ENV+'''
cd "$1"
echo "$$" > .kalibr.pid
git -c safe.directory=/catkin_ws/src/kalibr -C /catkin_ws/src/kalibr rev-parse HEAD > kalibr_source_commit.txt
{ time -p rosrun kalibr kalibr_calibrate_imu_camera --bag "$1/camera_imu.bag" --cam "$1/input-camera.yaml" --imu "$1/input-imu.yaml" --target "$1/aprilgrid.yaml" --imu-models calibrated --dont-show-report; } 2>&1
'''
        (root/'joint_command.sh').write_text(shell)
        logged_run(docker.prefix+['exec',container,'setsid','bash','-c',shell,'_',inner],root,'joint_calibration.log',stop,notify)
        chain=root/'camera_imu-camchain-imucam.yaml'
        for name in ('camera_imu-camchain-imucam.yaml','camera_imu-report-imucam.pdf','camera_imu-results-imucam.txt'):
            require((root/name).is_file() and (root/name).stat().st_size>0,'联合求解缺少输出：'+name)
        require((root/'camera_imu-report-imucam.pdf').read_bytes().startswith(b'%PDF'),'联合报告不是 PDF')
        result=yaml.safe_load(chain.read_text())
        for cam in ('cam0','cam1'):
            transform=np.asarray(result[cam].get('T_cam_imu'),dtype=float)
            require(transform.shape==(4,4) and np.isfinite(transform).all() and np.allclose(transform[3],[0,0,0,1]),'联合外参无效')
            r=transform[:3,:3]
            require(np.allclose(r.T@r,np.eye(3),atol=.001) and abs(np.linalg.det(r)-1)<.001,'联合旋转无效')
            require(np.isfinite(float(result[cam].get('timeshift_cam_imu',float('nan')))),'时间偏移未生成或无效')
        state.update(status='JOINT_OUTPUTS_REVIEW_PENDING',result_sha256=sha(chain))
        state['timing_seconds']={k:float(v) for k,v in re.findall(r'^(real|user|sys)\s+([0-9.]+)\s*$',(root/'joint_calibration.log').read_text(),re.M)}
        return state
    except BaseException as e:
        state.update(status='JOINT_CALIBRATION_FAILED',error=str(e));raise
    finally:
        if stop.is_set():docker.kill_group(container,inner)
        state['wall_seconds']=time.monotonic()-started
        (root/'joint_calculation.json').write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n')
        pack_review(root)
