"""Bounded local browser uploads. Only new import directories are ever modified."""
import csv
import json
import os
from pathlib import Path,PurePosixPath
import re
import secrets
import shutil
import threading
import yaml
from core import Board,require

CHUNK=8*1024**2


def relative_name(name):
    require(isinstance(name,str) and 0<len(name)<=500,'文件名无效')
    p=PurePosixPath(name)
    require(not p.is_absolute() and all(x not in ('','.','..') for x in name.split('/'))
            and '\\' not in name and not any(ord(c)<32 for c in name),'文件路径无效')
    require(not any(x.startswith('.') for x in p.parts),'不导入隐藏文件或控制文件')
    return p.as_posix()


class DataImport:
    def __init__(self,app):
        self.app=app;self.lock=threading.RLock();self.active=None

    def create(self,value):
        with self.app.lock,self.lock:
            require(not self.active,'已有文件正在导入，请等待或取消')
            require(self.app.data_root and self.app.container,'请先等待 Docker 数据目录就绪')
            require(self.app.state['stage'] in ('READY','DONE','FAILED') and not self.app.offline.busy(),'录制或计算期间不能导入文件')
            mode=value.get('mode');require(mode in ('camera','imu','camera_imu'),'未知数据类型')
            files=value.get('files');require(isinstance(files,list) and 1<=len(files)<=20000,'请选择文件，最多 20000 个')
            entries=[];seen=set();total=0
            for f in files:
                name=relative_name(f.get('name'));size=f.get('size')
                require(type(size) is int and 0<size<=100*1024**3,'文件为空或超过 100 GiB：'+name)
                require(name not in seen,'存在重名文件：'+name);seen.add(name)
                require(Path(name).suffix.lower() in ('.bag','.csv','.json','.yaml','.yml','.pgm','.bin','.txt','.log','.pdf','.sh','.patch','.py','.gz'), '不支持的文件类型：'+name)
                entries.append(dict(name=name,size=size,offset=0));total+=size
            require(total<=100*1024**3,'一次最多导入 100 GiB')
            # Large data is streamed to disk and never loaded as one request.
            require(shutil.disk_usage(self.app.data_root).free>total*2+3*1024**3,'空间不足：导入及后续计算副本需要约 '+str(round((total*2+3*1024**3)/1024**3,1))+' GiB')
            token=secrets.token_hex(16);parent=self.app.data_root/'imports'/mode
            require(parent.resolve().is_relative_to(self.app.data_root.resolve()),'导入目录不在本机数据目录中')
            parent.mkdir(parents=True,exist_ok=True)
            root=parent/token;root.mkdir();os.chmod(root,0o755)
            self.active=dict(id=token,root=root,mode=mode,files=entries,board=value.get('board'))
            return dict(id=token,chunk_bytes=CHUNK,total_bytes=total)

    def chunk(self,token,index,offset,stream,size):
        with self.lock:
            job=self.active;require(job and job['id']==token,'导入会话已结束，请重新选择文件')
            require(0<=index<len(job['files']),'未知文件')
            f=job['files'][index]
            require(0<size<=CHUNK and offset==f['offset'] and offset+size<=f['size'],'分段位置或大小不正确')
            path=job['root']/f['name'];path.parent.mkdir(parents=True,exist_ok=True)
            require(path.resolve().is_relative_to(job['root'].resolve()),'导入路径不安全')
            with path.open('ab') as dest:
                remaining=size
                while remaining:
                    data=stream.read(min(1024**2,remaining))
                    require(data,'文件传输中断，请取消后重新选择')
                    dest.write(data);remaining-=len(data)
            f['offset']+=size
            return dict(offset=f['offset'])

    def finish(self,token):
        with self.lock:
            job=self.active;require(job and job['id']==token,'未知导入会话')
            require(all(f['size']==f['offset'] for f in job['files']),'文件尚未传完')
            root=job['root'];mode=job['mode']
            # Folder picker adds one common top-level directory; normalize it once.
            paths=[PurePosixPath(f['name']) for f in job['files']]
            if all(len(p.parts)>1 and p.parts[0]==paths[0].parts[0] for p in paths):
                folder=root/paths[0].parts[0]
                for p in list(folder.iterdir()):shutil.move(str(p),str(root/p.name))
                folder.rmdir()
            bags=list(root.glob('*.bag'))
            if mode=='camera' or mode=='camera_imu' and bags:
                require(len(bags)==1,'请只选择一个 BAG；可另选对应 aprilgrid.yaml')
                canonical='camera.bag' if mode=='camera' else 'camera_imu_experimental.bag'
                if bags[0].name!=canonical:bags[0].rename(root/canonical)
                with (root/canonical).open('rb') as f:require(f.read(13)==b'#ROSBAG V2.0\n','不是 ROS1 BAG 文件')
                self.board(root,job['board'])
                kind='camera' if mode=='camera' else 'imported_joint'
            elif mode=='imu':
                self.metadata(root,'imu_capture.json')
                require((root/'imu_samples.csv').is_file(),'请同时选择 imu_samples.csv 和 imu_capture.json，或选择包含它们的录制文件夹')
                with (root/'imu_samples.csv').open() as f:header=next(csv.reader(f),[])
                required=['segment','tick_index','host_after_ns','ax_m_s2','ay_m_s2','az_m_s2','gx_rad_s','gy_rad_s','gz_rad_s']
                require(all(len(header)>i and header[i]==name for i,name in zip((0,1,5,12,13,14,15,16,17),required)),'IMU CSV 列名或顺序不匹配，请选择本工具保存的静止录制')
                capture=json.loads((root/'imu_capture.json').read_text())
                require(all(k in capture for k in ('status','elapsed_seconds','counter_discontinuities')),'IMU 元数据缺少时间或连续性信息')
                kind='imu'
            else:
                manifest=self.metadata(root,'camera_manifest.json')
                self.metadata(root,'imu_capture.json');self.metadata(root,'joint_clock.json')
                require((root/'imu_samples.csv').is_file(),'联合原始录制缺少 imu_samples.csv')
                pairs=manifest.get('selected_pairs');require(isinstance(pairs,list) and 40<=len(pairs)<=20000,'联合图像清单无效或数量不足')
                for pair in pairs:
                    for eye in ('left','right'):
                        name=relative_name(pair[eye]['file']);require((root/name).is_file(),'联合录制缺少图像：'+name)
                self.board(root,job['board']);kind='raw'
            (root/'.import-ready.json').write_text(json.dumps(dict(mode=mode,kind=kind,files=[f['name'] for f in job['files']],
                           source='User-selected local files; timestamp/unit provenance still requires review'),ensure_ascii=False,indent=2)+'\n')
            from offline import identity
            result=dict(id=identity(self.app.data_root,root),path=str(root),mode=mode,kind=kind)
            self.active=None
            return result

    @staticmethod
    def metadata(root,name):
        path=root/name;require(path.is_file(),'缺少 '+name+'；请拖入完整录制文件夹，或选齐所需文件')
        require(path.stat().st_size<=16*1024**2,'元数据过大：'+name)
        data=json.loads(path.read_text());require(isinstance(data,dict),'元数据格式无效：'+name);return data

    @staticmethod
    def board(root,value):
        if (root/'aprilgrid.yaml').is_file():
            require((root/'aprilgrid.yaml').stat().st_size<=32768,'标定板配置过大')
            data=yaml.safe_load((root/'aprilgrid.yaml').read_text())
            require(isinstance(data,dict) and data.get('target_type')=='aprilgrid','请提供 AprilGrid 板配置')
            Board.parse(dict(rows=data['tagRows'],cols=data['tagCols'],tag_mm=float(data['tagSize'])*1000,
                             gap_mm=float(data['tagSize'])*float(data['tagSpacing'])*1000))
        # No board file: use the current measured dimensions when calculation starts.
        # Do not freeze the form's defaults at upload time.

    def abort(self,token):
        with self.lock:
            if self.active and self.active['id']==token:
                shutil.rmtree(self.active['root']);self.active=None
