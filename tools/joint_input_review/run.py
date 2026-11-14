"""Read-only source review in an existing Kalibr container; fresh output only."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    bundle=Path(__file__).resolve().parent
    config=json.loads((bundle/'CHECKS.json').read_text())
    for name,digest in config['bundle_sha256'].items():
        if sha(bundle/name)!=digest:raise ValueError('安装包文件校验不符：'+name)
    source=Path(config['source']).resolve()
    for name,digest in config['source_sha256'].items():
        if sha(source/name)!=digest:raise ValueError('源记录与此前复核不符：'+name)
    prefix=['docker']
    if subprocess.run(prefix+['info'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
        subprocess.run(['sudo','-v'],check=True)
        prefix=['sudo','-n','docker']
    chosen=None
    for name in ['kalibr','ego-camera-kalibr']:
        result=subprocess.run(prefix+['inspect',name],capture_output=True,text=True)
        if result.returncode:continue
        info=json.loads(result.stdout)[0]
        for mount in info['Mounts']:
            if mount['Destination']=='/data':
                data=Path(mount['Source']).resolve()
                if data in source.parents:
                    chosen=(name,data,info);break
        if chosen:break
    if not chosen:raise ValueError('找不到 /data 挂载包含本次记录的 Kalibr 容器，未修改环境。')
    name,data,info=chosen
    if not info['State']['Running']:subprocess.run(prefix+['start',name],check=True)
    if shutil.disk_usage(source.parent).free<4*1024**3:raise ValueError('请先留出至少 4 GiB 空间用于新的联合 BAG。')
    out=Path(tempfile.mkdtemp(prefix='joint_experimental_input_',dir=source.parent))
    os.chmod(out,0o755)
    for filename in ['camera.yaml','imu-experimental.yaml','joint_bag.py','bag_writer.py','corner_check.json','CHECKS.json']:
        shutil.copy2(bundle/filename,out/filename)
    shutil.copy2(source/'aprilgrid.yaml',out/'aprilgrid.yaml')
    inner='/data/'+out.relative_to(data).as_posix()
    original='/data/'+source.relative_to(data).as_posix()
    status={'status':'STARTED','source':str(source),'output':str(out),
            'source_files_modified':False,'container':name,'image':info['Image'],
            'quality_accepted':False,'joint_optimization_executed':False}
    script='''set -eo pipefail
source /opt/ros/noetic/setup.bash
source /catkin_ws/devel/setup.bash
export HOME=/tmp/ego_camera_home ROS_HOME=/tmp/ego_camera_home/.ros
export MPLBACKEND=Agg PYTHONUNBUFFERED=1
export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0=/catkin_ws/src/kalibr
unset DISPLAY KALIBR_MANUAL_FOCAL_LENGTH_INIT
timeout 600 python3 "$1/joint_bag.py" "$2" "$1"
'''
    try:
        print('开始准备并读回核对实验联合 BAG，不重新录制。结果目录：'+str(out),flush=True)
        with (out/'prepare.log').open('w') as log:
            proc=subprocess.Popen(prefix+['exec',name,'bash','-c',script,'_',inner,original],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
            try:
                for line in proc.stdout:print(line,end='',flush=True);log.write(line);log.flush()
                rc=proc.wait()
            finally:
                proc.stdout.close()
        if rc:raise ValueError('容器准备退出码 '+str(rc)+'；请保留日志')
        report=json.loads((out/'bag_verification.json').read_text())
        status.update(status='EXPERIMENTAL_INPUT_READY_TIMING_REVIEW_PENDING',counts=report['counts'],bag_sha256=report['bag_sha256'])
    except BaseException as exc:
        status.update(status='FAILED_OR_INTERRUPTED',error=str(exc))
        raise
    finally:
        (out/'review_status.json').write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n')
        archive=out/'joint_input_review.tar.gz'
        with tarfile.open(archive,'w:gz') as tar:
            for p in out.iterdir():
                if p.is_file() and p.suffix in ('.json','.yaml','.log'):tar.add(p,arcname=p.name)
        print('\n请上传：'+str(archive),flush=True)
        subprocess.run(['xdg-open',str(out)],check=False)


if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:raise SystemExit('已停止等待；容器准备设有 10 分钟超时，请勿立即重复启动。已有数据保留。')
    except Exception as exc:raise SystemExit('准备停止：'+str(exc))
