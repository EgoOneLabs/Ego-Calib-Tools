"""Local GUI jobs for existing joint recordings; never overwrite source data."""
from collections import deque
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import threading
import time
import yaml
from core import require, sha, Board, device_id
from environment import ROS_ENV
from joint import validate_inputs
from joint_fixed_check import candidate_values
from pipeline import logged_run, calculate
from imu_analysis import analyze as analyze_imu

ROOT=Path(__file__).resolve().parent
EXPORTS={'joint-camchain-imucam.yaml','joint-results-imucam.txt','joint-report-imucam.pdf',
         'fixed_validation.json','job_status.json','job.log','offline_review.tar.gz',
         'camera-camchain.yaml','camera-report-cam.pdf','camera-results-cam.txt','calculation.json',
         'imu-candidate.yaml','imu-analysis.json','imu-results.txt','imu-report.pdf','imu-allan.csv',
         'camera.yaml','imu.yaml','aprilgrid.yaml','candidate.yaml','experimental_time_model.json','bag_verification.json'}


def identity(root,path):
    path=path.resolve();require(root in path.parents,'目录不在当前数据磁盘中')
    return hashlib.sha256(str(path.relative_to(root)).encode()).hexdigest()[:24]


def inventory(root):
    """Bounded discovery under this tool's known directories, no broad disk scan."""
    root=Path(root).resolve();datasets={};parameters={}
    for p in sorted(root.glob('camera_imu/*/*'),reverse=True)[:2000]:
        if not p.is_dir():continue
        try:key=identity(root,p)
        except ValueError:continue
        raw=all((p/n).is_file() for n in ('camera_manifest.json','imu_samples.csv','imu_capture.json','joint_clock.json','aprilgrid.yaml'))
        prepared=all((p/n).is_file() for n in ('camera_imu_experimental.bag','bag_verification.json','experimental_time_model.json','aprilgrid.yaml'))
        if raw or prepared:datasets[key]=(p,'raw' if raw else 'prepared')
    # Existing captures from this App; a dataset key never contains a client-supplied path.
    for pattern,kind,needed in [
        ('camera_easy/*/*','camera',('camera.bag',)),
        ('imu/*/*','imu',('imu_samples.csv','imu_capture.json'))]:
        for p in sorted(root.glob(pattern),reverse=True)[:2000]:
            if not p.is_dir() or not all((p/n).is_file() for n in needed):continue
            try:
                key=identity(root,p)
                # Reject escaped input symlinks as well as escaped directories.
                for n in needed:identity(root,p/n)
                datasets[key]=(p,kind)
            except ValueError:continue
    for p in sorted(root.glob('imports/*/*'),reverse=True)[:2000]:
        marker=p/'.import-ready.json'
        if not marker.is_file():continue
        try:
            key=identity(root,p);identity(root,marker)
            require(marker.stat().st_size<4*1024**2,'导入记录过大')
            data=json.loads(marker.read_text());kind=data.get('kind')
            require(kind in ('camera','imu','raw','imported_joint'),'未知导入类型')
            names={'camera':['camera.bag'],'imu':['imu_samples.csv','imu_capture.json'],
                   'raw':['camera_manifest.json','imu_samples.csv','imu_capture.json','joint_clock.json'],
                   'imported_joint':['camera_imu_experimental.bag']}[kind]
            for n in names:require((p/n).is_file(),'导入文件丢失');identity(root,p/n)
            datasets[key]=(p,kind)
        except (ValueError,OSError,KeyError,TypeError):continue
    patterns=['camera_imu/*/*/*.yaml','camera_easy/*/*/*camchain*.yaml','imu/*/*/imu-experimental.yaml','imu/*/*/imu-candidate.yaml']
    for pattern in patterns:
        for p in sorted(root.glob(pattern),reverse=True)[:2000]:
            if p.name=='aprilgrid.yaml' or not p.is_file() or p.stat().st_size>32768:continue
            try:
                key=identity(root,p);data=yaml.safe_load(p.read_text())
                if not isinstance(data,dict):continue
                kind='candidate' if all(k in data.get('cam0',{}) for k in ('T_cam_imu','timeshift_cam_imu')) else 'camera' if 'cam0' in data and 'cam1' in data else 'imu' if 'gyroscope_noise_density' in data else None
                if kind:parameters[key]=(p,kind)
            except (ValueError, OSError, yaml.YAMLError, UnicodeError):continue
    return datasets,parameters


class Offline:
    def __init__(self,app):
        self.app=app;self.lock=threading.RLock();self.stop=threading.Event();self.thread=None
        self.logs=deque(maxlen=35);self.out=None;self.inner=None
        self.state=dict(stage='IDLE',message='选择已有联合数据，再导入参数。',action=None,output='',files=[],result=None)

    def busy(self):
        return bool(self.thread and self.thread.is_alive())

    def catalog(self):
        root=self.app.data_root
        if not root:return dict(ready=False,datasets=[],parameters=[],root='')
        datasets,params=inventory(root)
        return dict(ready=True,root=str(root),
                    datasets=[dict(id=k,path=str(p),kind=kind,mode=kind if kind in ('camera','imu') else 'camera_imu') for k,(p,kind) in datasets.items()],
                    parameters=[dict(id=k,path=str(p),kind=kind) for k,(p,kind) in params.items()])

    def parameter(self,key):
        require(self.app.data_root,'数据目录尚未就绪')
        _,params=inventory(self.app.data_root);require(key in params,'参数文件已移动，请刷新列表')
        p,kind=params[key];return dict(text=p.read_text(),name=p.name,path=str(p),kind=kind)

    def public(self):
        with self.lock:
            return dict(self.state,busy=self.busy(),logs=list(self.logs),files=sorted(p.name for p in self.out.iterdir() if p.name in EXPORTS and p.is_file()) if self.out else [])

    def log(self,line):
        with self.lock:self.logs.append(line[-1500:])

    def stage(self,name,message):
        with self.lock:self.state.update(stage=name,message=message)
        self.log(message)

    def start(self,value):
        with self.app.lock,self.lock:
            require(not self.busy(),'已有计算或验证正在运行')
            require(not getattr(getattr(self.app,'imports',None),'active',None),'文件正在导入，请等待或取消')
            require(self.app.state['stage'] in ('READY','FAILED','DONE'),'请先等待当前采集结束')
            require(self.app.data_root and self.app.container,'Docker 环境尚未准备好')
            if value.get('action') in ('camera','imu'):
                return self.start_single(value)
            require(value.get('experimental_ack') is True,'请确认当前使用实验时间映射，结果需要复核')
            datasets,_=inventory(self.app.data_root);key=value.get('dataset')
            require(key in datasets,'请选择已有联合数据；目录移动后请刷新列表')
            source,kind=datasets[key];action=value.get('action')
            require(action in ('calibrate','validate'),'未知计算类型')
            camera=value.get('camera_yaml','') if action=='calibrate' else value.get('candidate_yaml','')
            imu=value.get('imu_yaml','');require(isinstance(camera,str) and isinstance(imu,str),'参数格式无效')
            status=validate_inputs(camera,imu);require(not status['missing'],'请导入相机或联合外参 YAML，以及 IMU 噪声 YAML')
            if action=='validate':candidate_values(yaml.safe_load(camera))
            if (source/'aprilgrid.yaml').is_file():
                identity(self.app.data_root,source/'aprilgrid.yaml')
                require((source/'aprilgrid.yaml').stat().st_size<=32768,'标定板配置过大')
                board=yaml.safe_load((source/'aprilgrid.yaml').read_text())
                require(isinstance(board,dict) and board.get('target_type')=='aprilgrid','缺少有效 AprilGrid 配置')
            else:
                require(value.get('board'),'该录制没有板配置，请在主流程填写实测板尺寸后开始计算')
                b=Board.parse(value['board'])
                board=dict(target_type='aprilgrid',tagRows=b.rows,tagCols=b.cols,tagSize=b.tag_mm/1000,tagSpacing=b.gap_mm/b.tag_mm)
            if kind=='raw':
                for n in ('camera_manifest.json','joint_clock.json','imu_capture.json'):
                    require((source/n).stat().st_size<16*1024**2,'采集元数据过大')
                manifest=json.loads((source/'camera_manifest.json').read_text())
                size=len(manifest['selected_pairs'])*int(manifest['width'])*int(manifest['height'])*2+3*1024**3
            else:size=(source/'camera_imu_experimental.bag').stat().st_size+3*1024**3
            require(shutil.disk_usage(source.parent).free>size,'磁盘空间不足，请先释放空间')
            self.out=Path(tempfile.mkdtemp(prefix='joint_gui_'+action+'_',dir=source.parent));os.chmod(self.out,0o755)
            self.inner='/data/'+self.out.relative_to(self.app.data_root).as_posix()
            self.stop.clear();self.logs.clear()
            self.state=dict(stage='QUEUED',message='正在准备已有数据…',action=action,output=str(self.out),result=None)
            self.thread=threading.Thread(target=self.worker,args=(source,kind,action,camera,imu,board),daemon=True)
            self.thread.start()

    def start_single(self,value):
        action=value['action'];datasets,_=inventory(self.app.data_root)
        require(value.get('dataset') in datasets,'请选择本机已录制的数据')
        source,kind=datasets[value['dataset']]
        require(kind==action,'所选数据与当前 Camera / IMU 模块不一致')
        ident=device_id(value.get('device_id',''))
        board=None
        if action=='camera':
            if (source/'aprilgrid.yaml').is_file():
                identity(self.app.data_root,source/'aprilgrid.yaml')
                require((source/'aprilgrid.yaml').stat().st_size<=32768,'板配置文件过大')
                board=yaml.safe_load((source/'aprilgrid.yaml').read_text())
                require(isinstance(board,dict) and board.get('target_type')=='aprilgrid','板配置无效')
                Board.parse(dict(rows=board['tagRows'],cols=board['tagCols'],tag_mm=float(board['tagSize'])*1000,
                                 gap_mm=float(board['tagSize'])*float(board['tagSpacing'])*1000))
            else:
                b=Board.parse(value.get('board',{}))
                board=dict(target_type='aprilgrid',tagRows=b.rows,tagCols=b.cols,tagSize=b.tag_mm/1000,tagSpacing=b.gap_mm/b.tag_mm)
        names=['camera.bag'] if action=='camera' else ['imu_samples.csv','imu_capture.json']
        for n in names:identity(self.app.data_root,source/n)
        size=sum((source/n).stat().st_size for n in names)+1024**3
        require(shutil.disk_usage(source.parent).free>size,'磁盘空间不足，请先释放空间')
        self.out=Path(tempfile.mkdtemp(prefix=action+'_calculate_',dir=source.parent));os.chmod(self.out,0o755)
        self.inner='/data/'+self.out.relative_to(self.app.data_root).as_posix()
        self.stop.clear();self.logs.clear()
        self.state=dict(stage='QUEUED',message='正在准备已有数据，不需要重新录制…',action=action,output=str(self.out),result=None)
        self.thread=threading.Thread(target=self.worker_single,args=(source,action,ident,board),daemon=True)
        self.thread.start()

    def worker_single(self,source,action,ident,board):
        started=time.monotonic();details=dict(source=str(source),action=action,quality_accepted=False)
        try:
            names=['camera.bag'] if action=='camera' else ['imu_samples.csv','imu_capture.json']
            details['input_sha256']={}
            self.stage('PREPARING','正在准备独立计算目录，原始录制保留…')
            for name in names:
                require(not self.stop.is_set(),'计算已停止')
                # Reflink when available, independent copy otherwise. Never edit source data.
                original=source/name;identity(self.app.data_root,original)
                before=sha(original)
                subprocess.run(['cp','--reflink=auto','--',str(original),str(self.out/name)],check=True)
                require(sha(self.out/name)==before,'数据副本校验失败：'+name)
                details['input_sha256'][name]=before
                self.log('已核对输入：'+name)
            if action=='camera':
                (self.out/'aprilgrid.yaml').write_text(yaml.safe_dump(board,sort_keys=False))
                result=calculate(self.out,self.app.docker,self.app.container,self.app.data_root,self.app.info,
                                 self.stop,self.stage,self.log,existing=True)
                if hasattr(self.app,'parameters'):self.app.parameters.remember(ident,'camera',self.out/'camera-camchain.yaml')
            else:
                result=analyze_imu(self.out,stop=self.stop,notify=self.stage)
                if hasattr(self.app,'parameters') and (self.out/'imu-candidate.yaml').is_file():
                    self.app.parameters.remember(ident,'imu',self.out/'imu-candidate.yaml')
                for line in (self.out/'imu-results.txt').read_text().splitlines():self.log(line)
            require(not self.stop.is_set(),'计算已停止；原始数据保留')
            details['result']=result
            with self.lock:self.state['result']=result
            self.stage('DONE','计算完成。请查看下方结果文件和保存路径；文件生成不等于质量验收。')
        except BaseException as exc:
            details['error']=str(exc);self.stage('FAILED',str(exc)+'；原始录制保留。')
        finally:
            if self.stop.is_set():self.app.docker.kill_group(self.app.container,self.inner)
            details.update(stage=self.state['stage'],wall_seconds=time.monotonic()-started)
            (self.out/'job_status.json').write_text(json.dumps(details,ensure_ascii=False,indent=2)+'\n')
            with tarfile.open(self.out/'offline_review.tar.gz','w:gz') as tar:
                for p in sorted(self.out.iterdir()):
                    if p.is_file() and p.suffix in ('.json','.yaml','.txt','.pdf','.log','.sh'):tar.add(p,arcname=p.name)

    def command(self,shell,filename='job.log'):
        script=ROS_ENV+'''\nexport GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0=/catkin_ws/src/kalibr
export PYTHONUNBUFFERED=1
cd "$1"
echo "$$" > .kalibr.pid
trap 'rm -f .kalibr.pid' EXIT
'''+shell
        (self.out/'command.sh').write_text(script)
        logged_run(self.app.docker.prefix+['exec',self.app.container,'setsid','bash','-c',script,'_',self.inner],
                   self.out,filename,self.stop,self.log)

    def worker(self,source,kind,action,camera,imu,board=None):
        start=time.monotonic();details=dict(source=str(source),action=action,quality_accepted=False,hardware_sync_verified=False)
        try:
            for name,text in [('camera.yaml',camera),('imu.yaml',imu)]: (self.out/name).write_text(text)
            if action=='validate':(self.out/'candidate.yaml').write_text(camera)
            if board is None:shutil.copy2(source/'aprilgrid.yaml',self.out/'aprilgrid.yaml')
            else:(self.out/'aprilgrid.yaml').write_text(yaml.safe_dump(board,sort_keys=False))
            details['input_sha256']={n:sha(self.out/n) for n in ('camera.yaml','imu.yaml','aprilgrid.yaml')}
            if kind=='raw':
                self.stage('BAG','正在生成 BAG 并逐条读回核对；保留原始数据…')
                for name in ('joint_bag.py','bag_writer.py'):shutil.copy2(ROOT/name,self.out/name)
                # JSON argv avoids inserting a filesystem path into shell source.
                original='/data/'+source.relative_to(self.app.data_root).as_posix()
                (self.out/'prepare_args.json').write_text(json.dumps([original,self.inner]))
                script='import json,sys; from joint_bag import prepare; prepare(*json.load(open(sys.argv[1])))'
                (self.out/'prepare_job.py').write_text(script)
                self.command('timeout --kill-after=10s 1800 python3 "$1/prepare_job.py" "$1/prepare_args.json"\n',filename='prepare.log')
                verified=json.loads((self.out/'bag_verification.json').read_text())
            elif kind=='imported_joint':
                self.stage('BAG','正在逐条读取导入的联合 BAG，检查图像、IMU 与时间记录…')
                subprocess.run(['cp','--reflink=auto','--',str(source/'camera_imu_experimental.bag'),str(self.out/'camera_imu_experimental.bag')],check=True)
                shutil.copy2(ROOT/'camera_bag_check.py',self.out/'camera_bag_check.py')
                self.command('timeout --kill-after=10s 1800 python3 "$1/camera_bag_check.py" "$1" --joint\n',filename='prepare.log')
                verified=json.loads((self.out/'bag_verification.json').read_text())
                require(verified.get('status')=='JOINT_IMPORTED_BAG_CHECKED','联合 BAG 检查失败')
                details['imported_timestamp_provenance']='Used BAG header timestamps as supplied; exposure synchronization not verified'
            else:
                self.stage('BAG','正在核对已有 BAG 并准备独立副本…')
                verified=json.loads((source/'bag_verification.json').read_text())
                require(verified.get('status')=='EXPERIMENTAL_JOINT_BAG_READBACK_VERIFIED','请选择已经读回核对的联合 BAG')
                for field in ('all_image_pixels_verified','all_imu_values_verified','all_header_and_bag_times_verified'):
                    require(verified.get(field) is True,'BAG 缺少完整读回记录')
                require(sha(source/'camera_imu_experimental.bag')==verified.get('bag_sha256'),'BAG 校验不符')
                require(not self.stop.is_set(),'任务已停止')
                subprocess.run(['cp','--reflink=auto','--',str(source/'camera_imu_experimental.bag'),str(self.out/'camera_imu_experimental.bag')],check=True)
                for name in ('bag_verification.json','experimental_time_model.json'):shutil.copy2(source/name,self.out/name)
            require(sha(self.out/'camera_imu_experimental.bag')==verified['bag_sha256'],'BAG 副本校验不符')
            details['bag_sha256']=verified['bag_sha256']
            require(not self.stop.is_set(),'任务已停止')
            (self.out/'camera_imu_experimental.bag').rename(self.out/'joint.bag')
            if action=='validate':
                self.stage('VALIDATING','正在固定候选外参与时间偏移，检查独立数据的一致性…')
                shutil.copy2(ROOT/'joint_fixed_check.py',self.out/'fixed_check.py')
                shutil.copy2(ROOT/'kalibr_hashes.json',self.out/'kalibr_hashes.json')
                self.command('{ time -p timeout --kill-after=10s 1800 python3 "$1/fixed_check.py" "$1/candidate.yaml" --bag "$1/joint.bag" --cams "$1/candidate.yaml" --imu "$1/imu.yaml" --target "$1/aprilgrid.yaml" --no-time-calibration --dont-show-report; } 2>&1\n')
                result=json.loads((self.out/'fixed_validation.json').read_text())
                require(result.get('extrinsics_fixed') is True and result.get('time_offsets_fixed') is True,'未确认参数保持锁定')
                require(result.get('candidate_sha256')==details['input_sha256']['camera.yaml'],'验证使用的候选文件不一致')
            else:
                self.stage('CALIBRATING','正在使用 Kalibr 计算联合外参与时间偏移…')
                self.command('{ time -p timeout --kill-after=10s 1800 rosrun kalibr kalibr_calibrate_imu_camera --bag "$1/joint.bag" --cams "$1/camera.yaml" --imu "$1/imu.yaml" --target "$1/aprilgrid.yaml" --dont-show-report; } 2>&1\n')
                result=dict(status='JOINT_OUTPUTS_COMPLETE_REVIEW_PENDING')
            for name in ('joint-camchain-imucam.yaml','joint-results-imucam.txt','joint-report-imucam.pdf'):
                require((self.out/name).is_file() and (self.out/name).stat().st_size>0,'缺少结果文件：'+name)
            require((self.out/'joint-report-imucam.pdf').read_bytes().startswith(b'%PDF'),'PDF 报告格式无效')
            result.update(quality_accepted=False,hardware_sync_verified=False)
            with self.lock:self.state['result']=result
            details['result']=result
            self.stage('DONE','计算完成，请查看报告；文件生成不等于最终质量验收。' if action=='calibrate' else '固定参数检查完成，请查看误差报告；仍需结合噪声、时间轴和重复性复核。')
        except BaseException as exc:
            details['error']=str(exc);self.stage('FAILED',str(exc)+'；原始数据保留，可下载日志。')
        finally:
            if self.stop.is_set():self.app.docker.kill_group(self.app.container,self.inner)
            details.update(stage=self.state['stage'],wall_seconds=time.monotonic()-start)
            (self.out/'job_status.json').write_text(json.dumps(details,ensure_ascii=False,indent=2)+'\n')
            with tarfile.open(self.out/'offline_review.tar.gz','w:gz') as tar:
                for p in sorted(self.out.iterdir()):
                    if p.is_file() and p.suffix in ('.json','.yaml','.txt','.pdf','.log','.sh','.py'):tar.add(p,arcname=p.name)

    def cancel(self):
        self.stop.set()
        if self.busy() and self.inner:self.app.docker.kill_group(self.app.container,self.inner)

    def open_output(self):
        require(self.out and self.out.is_dir(),'尚无结果目录')
        subprocess.Popen(['xdg-open',str(self.out)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
