"""Run a fixed-candidate check on the already recorded independent BAG."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024**2),b''): h.update(chunk)
    return h.hexdigest()


def main():
    bundle=Path(__file__).resolve().parent
    config=json.loads((bundle/'CHECKS.json').read_text())
    for name,digest in config['bundle_sha256'].items():
        if sha(bundle/name)!=digest: raise ValueError('工具校验不符：'+name)
    source=Path(config['source'])
    candidate=Path(config['candidate'])
    for name,digest in config['source_sha256'].items():
        if sha(source/name)!=digest:raise ValueError('输入校验不符：'+name)
    if sha(candidate)!=config['candidate_sha256']:raise ValueError('候选外参校验不符')
    verification=json.loads((source/'bag_verification.json').read_text())
    if verification['counts']!={'/imu0':72394,'/cam0/image_raw':765,'/cam1/image_raw':765}:
        raise ValueError('独立记录的数据数量不符')
    for field in ['all_image_pixels_verified','all_imu_values_verified','all_header_and_bag_times_verified']:
        if verification.get(field) is not True:raise ValueError('BAG 尚未完成读回检查')
    prefix=['docker']
    if subprocess.run(prefix+['info'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
        subprocess.run(['sudo','-v'],check=True);prefix=['sudo','-n','docker']
    info=json.loads(subprocess.check_output(prefix+['inspect','kalibr'],text=True))[0]
    roots=[Path(m['Source']).resolve() for m in info['Mounts'] if m['Destination']=='/data']
    if len(roots)!=1 or roots[0] not in source.resolve().parents:
        raise ValueError('Kalibr 数据挂载不符')
    if not info['State']['Running']:subprocess.run(prefix+['start','kalibr'],check=True)
    if shutil.disk_usage(source.parent).free < 6*1024**3:raise ValueError('请保留至少 6 GiB 空间')
    out=Path(tempfile.mkdtemp(prefix='joint_fixed_check_',dir=source.parent));os.chmod(out,0o755)
    status=dict(status='STARTED',source=str(source),candidate=str(candidate),output=str(out),
                source_files_modified=False,quality_accepted=False,hardware_sync_verified=False)
    print('固定外参与时间偏移验证，结果目录：'+str(out),flush=True)
    try:
        for name in ['fixed_check.py','kalibr_hashes.json','CHECKS.json','README.zh-CN.md']:
            shutil.copy2(bundle/name,out/name)
        shutil.copy2(candidate,out/'candidate.yaml')
        for a,b in [('imu-experimental.yaml','imu.yaml'),('aprilgrid.yaml','aprilgrid.yaml'),('experimental_time_model.json','experimental_time_model.json')]:
            shutil.copy2(source/a,out/b)
        subprocess.run(['cp','--reflink=auto','--',str(source/'camera_imu_experimental.bag'),str(out/'validation.bag')],check=True)
        if sha(out/'validation.bag')!=config['source_sha256']['camera_imu_experimental.bag']:
            raise ValueError('BAG 副本校验不符')
        inner='/data/'+out.relative_to(roots[0]).as_posix()
        script='''set -eo pipefail
source /opt/ros/noetic/setup.bash
source /catkin_ws/devel/setup.bash
export HOME=/tmp/ego_camera_home ROS_HOME=/tmp/ego_camera_home/.ros
export MPLBACKEND=Agg PYTHONUNBUFFERED=1
export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0=/catkin_ws/src/kalibr
unset DISPLAY KALIBR_MANUAL_FOCAL_LENGTH_INIT
cd "$1"
time -p timeout --kill-after=10s 1800 python3 "$1/fixed_check.py" "$1/candidate.yaml" --bag "$1/validation.bag" --cams "$1/candidate.yaml" --imu "$1/imu.yaml" --target "$1/aprilgrid.yaml" --no-time-calibration --dont-show-report
'''
        (out/'container_command.sh').write_text(script)
        with (out/'fixed_check.log').open('w') as log:
            proc=subprocess.Popen(prefix+['exec','kalibr','bash','-c',script,'_',inner],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
            try:
                for line in proc.stdout:print(line,end='',flush=True);log.write(line);log.flush()
                rc=proc.wait()
            finally:proc.stdout.close()
        status['container_exit_code']=rc
        if rc:raise ValueError('容器退出码：'+str(rc)+'；保留日志供排查，不代表传感器失败')
        report=json.loads((out/'fixed_validation.json').read_text())
        if report.get('extrinsics_fixed') is not True or report.get('time_offsets_fixed') is not True:
            raise ValueError('未确认参数锁定')
        for name in ['validation-camchain-imucam.yaml','validation-results-imucam.txt','validation-report-imucam.pdf']:
            if not (out/name).is_file() or not (out/name).stat().st_size:raise ValueError('缺少输出：'+name)
        if sha(out/'candidate.yaml')!=config['candidate_sha256']:raise ValueError('输入候选文件被修改')
        status.update(status='FIXED_CANDIDATE_CHECK_COMPLETE_REVIEW_PENDING',residuals=report['residuals'])
    except BaseException as exc:
        status.update(status='FAILED_OR_INTERRUPTED',error=str(exc));raise
    finally:
        (out/'review_status.json').write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n')
        archive=out/'joint_fixed_review.tar.gz'
        with tarfile.open(archive,'w:gz') as tar:
            for p in out.iterdir():
                if p.is_file() and p.suffix in ('.json','.yaml','.txt','.log','.pdf','.py','.sh','.md'):
                    tar.add(p,arcname=p.name)
        print('\n请上传：'+str(archive),flush=True)
        subprocess.run(['xdg-open',str(out)],check=False)


if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:raise SystemExit('已停止等待；容器内任务有 30 分钟上限，请勿立即重复启动。')
    except Exception as exc:raise SystemExit('验证停止：'+str(exc))
