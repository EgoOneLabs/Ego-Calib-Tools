#!/usr/bin/env python3
"""Publisher only: export the known workstation image and build a full camera.zip."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from build_installer import build, digest


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if not shutil.which('docker'):raise SystemExit('请在已经配置好 Kalibr 的原工作站运行 --make-full。新电脑只需运行普通安装命令。')
    command=['docker']
    if subprocess.run(command+['info'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
        subprocess.run(['sudo','-v'],check=True);command=['sudo','-n','docker']
    image=None
    for container in ['kalibr','ego-camera-kalibr']:
        r=subprocess.run(command+['inspect','--format','{{.Image}}',container],capture_output=True,text=True)
        if r.returncode==0:image=r.stdout.strip();break
    if not image:
        r=subprocess.run(command+['image','inspect','--format','{{.Id}}','kalibr:noetic'],capture_output=True,text=True)
        if r.returncode==0:image=r.stdout.strip()
    if not image:raise SystemExit('原工作站没有找到 Kalibr 环境，请先核对 Docker 中的 kalibr 容器。')
    a.output.mkdir(parents=True,exist_ok=True)
    archive=a.output/'kalibr-environment.tar.gz'
    print('开始导出 Kalibr 环境并生成完整安装包，可能需要数分钟。',flush=True)
    partial=archive.with_suffix('.gz.partial')
    with partial.open('wb') as out:
        save=subprocess.Popen(command+['save',image],stdout=subprocess.PIPE)
        gzip=subprocess.Popen(['gzip','-1'],stdin=save.stdout,stdout=out)
        save.stdout.close()
        code=gzip.wait();saved=save.wait()
        if code or saved:raise SystemExit('环境导出失败，保留 .partial 文件供排查。')
    subprocess.run(['gzip','-t',str(partial)],check=True)
    partial.replace(archive)
    (a.output/'environment_manifest.json').write_text(json.dumps({'image_id':image,'archive_sha256':digest(archive),'source':'Docker image used by original workstation; no runtime container filesystem changes committed'},indent=2)+'\n')
    build(a.source,a.output,archive,source_snapshot=True)
    print('完整版已生成：'+str((a.output/'camera.zip').resolve()),flush=True)
    print('给新用户发布这个 camera.zip；包中已包含环境镜像，无需用户再选择镜像文件。',flush=True)

if __name__=='__main__':main()
