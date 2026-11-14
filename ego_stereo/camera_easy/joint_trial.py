"""Experimental joint optimization; never creates a formal time-review pass."""
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import time
import yaml


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024**2),b''):h.update(chunk)
    return h.hexdigest()


def check_outputs(root):
    names=['camera_imu_experimental'+s for s in ['-camchain-imucam.yaml','-report-imucam.pdf','-results-imucam.txt']]
    for name in names:
        if not (root/name).is_file() or not (root/name).stat().st_size:
            raise ValueError('缺少求解输出：'+name)
    if not (root/names[1]).read_bytes().startswith(b'%PDF'):raise ValueError('报告不是 PDF')
    result=yaml.safe_load((root/names[0]).read_text())
    summary={}
    for camera in ['cam0','cam1']:
        matrix=result[camera]['T_cam_imu']
        if len(matrix)!=4 or any(len(row)!=4 for row in matrix):raise ValueError('联合外参格式无效')
        if not all(math.isfinite(float(x)) for row in matrix for x in row):raise ValueError('联合外参有无效数值')
        shift=float(result[camera]['timeshift_cam_imu'])
        if not math.isfinite(shift):raise ValueError('时间偏移无效')
        summary[camera]={'T_cam_imu':matrix,'timeshift_cam_imu':shift}
    return {'output_sha256':{name:sha(root/name) for name in names},'experimental_results':summary}


SCRIPT='''set -eo pipefail
source /opt/ros/noetic/setup.bash
source /catkin_ws/devel/setup.bash
export HOME=/tmp/ego_camera_home ROS_HOME=/tmp/ego_camera_home/.ros
export MPLBACKEND=Agg PYTHONUNBUFFERED=1
export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0=/catkin_ws/src/kalibr
unset DISPLAY KALIBR_MANUAL_FOCAL_LENGTH_INIT
cd "$1"
git -C /catkin_ws/src/kalibr rev-parse HEAD > kalibr_source_commit.txt
printf 'started\\n' > solver_started.txt
set +e
{ time -p rosrun kalibr kalibr_calibrate_imu_camera --bag "$1/camera_imu_experimental.bag" --cams "$1/camera.yaml" --imu "$1/imu-experimental.yaml" --target "$1/aprilgrid.yaml" --dont-show-report; } 2>&1
rc=$?
printf '%s\\n' "$rc" > solver_exit_code.txt
exit "$rc"
'''


def main():
    bundle=Path(__file__).resolve().parent
    config=json.loads((bundle/'CHECKS.json').read_text())
    if sha(Path(__file__))!=config['runner_sha256']:raise ValueError('试跑程序校验不符')
    source=Path(config['source']).resolve()
    print('正在核对完整 BAG 和输入参数……',flush=True)
    for name,digest in config['source_sha256'].items():
        if sha(source/name)!=digest:raise ValueError('输入摘要不符：'+name)
    verification=json.loads((source/'bag_verification.json').read_text())
    if verification['status']!='EXPERIMENTAL_JOINT_BAG_READBACK_VERIFIED' or verification['counts']!={'/imu0':48160,'/cam0/image_raw':490,'/cam1/image_raw':490}:
        raise ValueError('BAG 读回记录不符')
    prefix=['docker']
    if subprocess.run(prefix+['info'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
        subprocess.run(['sudo','-v'],check=True);prefix=['sudo','-n','docker']
    info=json.loads(subprocess.check_output(prefix+['inspect','kalibr'],text=True))[0]
    mounts=[Path(m['Source']).resolve() for m in info['Mounts'] if m['Destination']=='/data']
    if len(mounts)!=1 or mounts[0] not in source.parents:raise ValueError('Kalibr 数据挂载不符，停止')
    data=mounts[0]
    if not info['State']['Running']:subprocess.run(prefix+['start','kalibr'],check=True)
    if shutil.disk_usage(source.parent).free<4*1024**3:raise ValueError('请先留出至少 4 GiB 空间')
    out=Path(tempfile.mkdtemp(prefix='joint_experimental_trial_',dir=source.parent));os.chmod(out,0o755)
    status={'status':'EXPERIMENTAL_OPTIMIZATION_RUNNING','source':str(source),'output':str(out),
            'source_files_modified':False,'container':'kalibr','container_image':info['Image'],
            'quality_accepted':False,'hardware_sync_verified':False,
            'imu_intrinsics_independently_verified':False,
            'timing':'Experimental host/counter mapping; not reviewed exposure/sample timing.',
            'imu_weights':'Mixed static model experimental weights; not final noise certification.',
            'source_sha256':config['source_sha256']}
    started=time.monotonic()
    try:
        for name in ['camera.yaml','imu-experimental.yaml','aprilgrid.yaml','experimental_time_model.json','bag_verification.json','corner_check.json']:
            shutil.copy2(source/name,out/name)
        subprocess.run(['cp','--reflink=auto','--',str(source/'camera_imu_experimental.bag'),str(out/'camera_imu_experimental.bag')],check=True)
        if sha(out/'camera_imu_experimental.bag')!=verification['bag_sha256']:raise ValueError('BAG 副本校验失败')
        shutil.copy2(Path(__file__),out/'runner_source.py')
        (out/'container_command.sh').write_text(SCRIPT)
        inner='/data/'+out.relative_to(data).as_posix()
        print('开始官方 Kalibr 实验求解。结果目录：'+str(out),flush=True)
        with (out/'run.log').open('w') as log:
            process=subprocess.Popen(prefix+['exec','kalibr','timeout','--kill-after=10s','1800','bash','-c',SCRIPT,'_',inner],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
            try:
                for line in process.stdout:print(line,end='',flush=True);log.write(line);log.flush()
                rc=process.wait()
            finally:process.stdout.close()
        status['container_exit_code']=rc
        if rc:raise ValueError('联合求解退出码 '+str(rc)+'，请上传日志包')
        status.update(check_outputs(out));status['status']='EXPERIMENTAL_OUTPUTS_COMPLETE_REVIEW_PENDING'
    except BaseException as exc:
        status.update(status='FAILED_OR_INTERRUPTED',error=str(exc));raise
    finally:
        status['wall_seconds']=time.monotonic()-started
        (out/'trial_status.json').write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n')
        archive=out/'joint_trial_review.tar.gz'
        with tarfile.open(archive,'w:gz') as tar:
            for p in out.iterdir():
                if p.is_file() and p.suffix in ('.json','.yaml','.txt','.log','.pdf','.py','.sh'):tar.add(p,arcname=p.name)
        print('\n请上传：'+str(archive),flush=True)
        subprocess.run(['xdg-open',str(out)],check=False)


if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:raise SystemExit('已停止等待，容器任务可能继续运行至 30 分钟超时；请勿立即重复启动。结果保留。')
    except Exception as exc:raise SystemExit('试跑停止：'+str(exc))
