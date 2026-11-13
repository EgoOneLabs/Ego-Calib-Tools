#!/usr/bin/env python3
"""Publisher: reuse an archive first; otherwise export with a disk space precheck."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
from build_installer import build, digest


def candidates(output, archive_dir):
    yield output / 'kalibr-environment.tar.gz'
    if archive_dir:
        yield archive_dir / 'kalibr-environment.tar.gz'
        yield archive_dir / 'environment/kalibr-environment.tar.gz'
    # Prior workstation deliveries; no hardcoded login name.
    for downloads in (Path.home()/'Downloads', Path.home()/'下载'):
        for pattern in ('calibration-bilingual-*/headband-calibration-assistant-v1.10.4-full/environment/kalibr-environment.tar.gz',
                        'headband-repo-migration-*/headband-calibration-assistant-v1.10.4-full/environment/kalibr-environment.tar.gz'):
            yield from sorted(downloads.glob(pattern))


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--archive-dir',type=Path)
    p.add_argument('--image-archive',type=Path)
    a=p.parse_args();a.output=a.output.expanduser().resolve();a.output.mkdir(parents=True,exist_ok=True)
    archive = a.image_archive.expanduser().resolve() if a.image_archive else next((x.resolve() for x in candidates(a.output,a.archive_dir) if x.is_file()),None)
    image=None
    if archive:
        if not archive.is_file():raise SystemExit('找不到环境包：'+str(archive))
        print('复用已有环境包：'+str(archive),flush=True)
    else:
        if not shutil.which('docker'):raise SystemExit('请在已经配置好 Kalibr 的原工作站打包，或用 --image-archive 指定已有环境包。')
        command=['docker']
        if subprocess.run(command+['info'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
            subprocess.run(['sudo','-v'],check=True);command=['sudo','-n','docker']
        for container in ['kalibr','ego-camera-kalibr']:
            r=subprocess.run(command+['inspect','--format','{{.Image}}',container],capture_output=True,text=True)
            if r.returncode==0:image=r.stdout.strip();break
        if not image:
            r=subprocess.run(command+['image','inspect','--format','{{.Id}}','kalibr:noetic'],capture_output=True,text=True)
            if r.returncode==0:image=r.stdout.strip()
        if not image:raise SystemExit('没有找到 Kalibr 镜像。')
        size=int(subprocess.check_output(command+['image','inspect','--format','{{.Size}}',image],text=True).strip())
        # Compression is unknown before export; reserve for archive, payload, and final ZIP.
        needed=size*3+512*1024**2
        free=shutil.disk_usage(a.output).free
        if free<needed:raise SystemExit(f'磁盘空间不足，导出未开始：保守需要 {needed/1024**3:.1f} GiB，可用 {free/1024**3:.1f} GiB。请提供已有环境包或用 --output 选择其他磁盘。')
        archive=a.output/'kalibr-environment.tar.gz';partial=archive.with_suffix('.gz.partial')
        if partial.exists():raise SystemExit('存在上次失败文件，请先检查并清理：'+str(partial))
        print('正在导出 Kalibr 环境…',flush=True)
        try:
            with partial.open('xb') as out:
                save=subprocess.Popen(command+['save',image],stdout=subprocess.PIPE)
                gzip=subprocess.Popen(['gzip','-1'],stdin=save.stdout,stdout=out)
                save.stdout.close();code=gzip.wait();saved=save.wait()
                if code or saved:raise RuntimeError('环境导出失败；本次未完成文件已清理')
            partial.replace(archive)
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
    required=archive.stat().st_size*2+512*1024**2
    free=shutil.disk_usage(a.output).free
    if free<required:raise SystemExit(f'打包磁盘空间不足：需要约 {required/1024**3:.1f} GiB，可用 {free/1024**3:.1f} GiB。请用 --output 指定另一块磁盘。')
    subprocess.run(['gzip','-t',str(archive)],check=True)
    (a.output/'environment_manifest.json').write_text(json.dumps({'image_id':image,'archive_path':str(archive),'archive_sha256':digest(archive),'source':'existing archive' if image is None else 'Docker image export; runtime container edits not included'},indent=2)+'\n')
    build(a.source,a.output,archive,source_snapshot=True,retain_run=False)
    print('完整版已生成：'+str(a.output/'camera.zip'),flush=True)
    print('只需把这个 camera.zip 发给新电脑，包内已包含环境。',flush=True)

if __name__=='__main__':main()
