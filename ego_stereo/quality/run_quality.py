#!/usr/bin/env python3
"""Validate existing DS parameters on original board BAG; never recalibrate."""
import argparse,hashlib,json,shutil,subprocess,tarfile,tempfile,time,sys
from pathlib import Path

CAM_SHA='153ab87359e8efd07be55a3d5c4734911bfbd7b7277452eb91087c4976c97aaf'
BAG_SHA='21dddddd7ee6dc05b8d4e72f3255d7dccb8b29e076f70892d06aeecf5f633580'
RESULT=Path(__file__).resolve().parents[1]/'reference/2uq2-ds-20261102'


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()


def require(ok,message):
    if not ok:raise ValueError(message)


def capture(args):
    return subprocess.run(args,check=True,text=True,stdout=subprocess.PIPE).stdout


def inner(path,info,writable=False):
    choices=[]
    for mount in info.get('Mounts',[]):
        if mount.get('Type')!='bind' or (writable and not mount.get('RW')):continue
        try:relative=path.resolve().relative_to(Path(mount['Source']).resolve())
        except ValueError:continue
        choices.append((len(Path(mount['Source']).parts),str(Path(mount['Destination'])/relative)))
    require(choices,'路径不在 kalibr 容器绑定挂载内：'+str(path))
    return max(choices)[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bag',type=Path,required=True,help='Original 230-pair BAG; explicit local input, checked against BAG_SHA')
    parser.add_argument('--result',type=Path,default=RESULT)
    parser.add_argument('--output-root',type=Path,required=True,help='New output parent under a writable container bind mount')
    parser.add_argument('--container',default='kalibr')
    a=parser.parse_args();cam=a.result/'camera_4hz-camchain.yaml'
    require(cam.is_file() and sha(cam)==CAM_SHA,'DS YAML来源不匹配；停止，不自动改用其他参数')
    candidates=[a.bag]
    require(candidates,'未找到原230对图像BAG；请提供 --bag 路径，无需重录')
    bag=None
    for candidate in candidates:
        if candidate.is_file() and sha(candidate)==BAG_SHA:bag=candidate.resolve();break
    require(bag is not None,'没有BAG与已知230对原数据摘要一致；停止，不重复标定')
    info=json.loads(capture(['docker','inspect',a.container]))[0]
    inner(a.output_root,info,True);bag_in=inner(bag,info)
    if not info['State']['Running']:subprocess.run(['docker','start',a.container],check=True)
    a.output_root.mkdir(parents=True,exist_ok=True)
    root=Path(tempfile.mkdtemp(prefix='ds_fixed_quality_',dir=a.output_root));root_in=inner(root,info,True)
    for n in ['audit_core.py','audit_in_container.py']:shutil.copyfile(Path(__file__).with_name(n),root/n)
    shutil.copyfile(cam,root/'camchain.yaml')
    (root/'aprilgrid.yaml').write_text('target_type: aprilgrid\ntagRows: 6\ntagCols: 6\ntagSize: 0.088\ntagSpacing: 0.3\n')
    run={'status':'RUNNING','source_bag':str(bag),'source_result':str(a.result),'bag_sha256':BAG_SHA,'camchain_sha256':CAM_SHA,
         'tool_sha256':{n:sha(Path(__file__).with_name(n)) for n in ['run_quality.py','audit_core.py','audit_in_container.py']},
         'container':a.container,'container_image_id':info.get('Image'),'source_data_modified':False,'calibration_rerun':False,
         'calibration_quality_accepted':False,'independent_holdout':False,'target_dimensions_source':'Matched DS TXT; physical measurement not re-verified'}
    print('输出目录：'+str(root),flush=True)
    shell='''set -eo pipefail
source /opt/ros/noetic/setup.bash
source /catkin_ws/devel/setup.bash
export MPLBACKEND=Agg PYTHONUNBUFFERED=1
unset DISPLAY
git -C /catkin_ws/src/kalibr rev-parse HEAD > "$1/kalibr_commit.txt"
git -C /catkin_ws/src/kalibr status --porcelain > "$1/kalibr_status.txt"
git -C /catkin_ws/src/kalibr diff --quiet
git -C /catkin_ws/src/kalibr diff --cached --quiet
exec python3 "$1/audit_in_container.py" --root "$1" --bag "$2"
'''
    (root/'command.sh').write_text(shell)
    (root/'run.json').write_text(json.dumps(run,ensure_ascii=False,indent=2)+'\n')
    started=time.monotonic()
    try:
        with (root/'quality.log').open('w') as log:
            p=subprocess.Popen(['docker','exec',a.container,'bash','-c',shell,'_',root_in,bag_in],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
            for line in p.stdout:print(line,end='',flush=True);log.write(line);log.flush()
            code=p.wait()
        require(code==0,'固定参数核查失败；保留输出日志，不自动重试')
        summary=json.loads((root/'quality_summary.json').read_text())
        require(summary['status']=='FIXED_PARAMETER_OBSERVATIONS_COMPLETE_REVIEW_PENDING','未得到有效共同观测')
        require(sha(cam)==CAM_SHA and sha(root/'camchain.yaml')==CAM_SHA,'参数文件发生变化')
        run['status']='FIXED_PARAMETER_AUDIT_COMPLETE_REVIEW_PENDING'
    except BaseException as e:
        run.update(status='FAILED_OR_INTERRUPTED',error=str(e));raise
    finally:
        run['wrapper_wall_seconds']=time.monotonic()-started
        (root/'run.json').write_text(json.dumps(run,ensure_ascii=False,indent=2)+'\n')
        archive=root/'camera_quality_small_review.tar.gz'
        with tarfile.open(archive,'w:gz') as tar:
            for f in sorted(root.iterdir()):
                if f.is_file() and f.suffix in ['.json','.log','.txt','.csv','.png','.jpg','.yaml','.sh','.py']:
                    tar.add(f,arcname=f.name)
        print('\n请上传：'+str(archive),flush=True)
        print('原参数和BAG未覆盖；没有运行标定优化。',flush=True)

if __name__=='__main__':
    try:main()
    except Exception as e:sys.exit(str(e))
