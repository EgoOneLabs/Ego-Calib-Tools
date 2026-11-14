"""Upgrade the installed desktop entry in place, preserving data and a backup."""
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    bundle=Path(__file__).resolve().parent
    checks=json.loads((bundle/'CHECKS.json').read_text())
    for name,digest in checks['payload_sha256'].items():
        if sha(bundle/'payload'/name)!=digest:raise ValueError('更新包校验不符：'+name)
    entry=Path.home()/'.local/share/applications/ego-camera-calibration.desktop'
    if not entry.is_file():raise ValueError('未找到头环标定工具的菜单入口，请先安装原工具。')
    command=next(line[5:] for line in entry.read_text().splitlines() if line.startswith('Exec='))
    args=shlex.split(command)
    scripts=[Path(arg).resolve() for arg in args if arg.endswith('/camera_easy/start.sh')]
    if len(scripts)!=1:raise ValueError('菜单启动命令与预期不符，未修改。')
    root=scripts[0].parent
    releases=(Path.home()/'.local/share/ego-camera/releases').resolve()
    if releases not in root.parents:raise ValueError('程序不在已知安装目录，未修改。')
    old_hash=sha(root/'app.py')
    if old_hash not in (checks['base_app_sha256'],checks['payload_sha256']['app.py']):
        raise ValueError('当前程序版本与本更新不匹配，未修改。请提供菜单入口检查结果。')
    running=[]
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name)==os.getpid():continue
        try:argv=(proc/'cmdline').read_bytes().split(b'\0')
        except (OSError,PermissionError):continue
        if any(arg.endswith(b'/camera_easy/app.py') for arg in argv):running.append(proc.name)
    if running:raise ValueError('头环标定工具仍在运行（PID '+','.join(running)+'）。请在它的启动终端按 Ctrl+C，等待退出后重新执行本命令；无需重录。')
    backup=Path(tempfile.mkdtemp(prefix='joint-gui-before-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-',dir=root.parent))
    names=list(checks['payload_sha256'])
    for name in names:
        if (root/name).is_file():shutil.copy2(root/name,backup/name)
    manifest=root.parent/'required_files.json'
    if manifest.is_file():shutil.copy2(manifest,backup/'required_files.json')
    try:
        # Install app.py last; an interrupted copy cannot reference missing modules.
        for name in sorted(names,key=lambda n:n=='app.py'):
            pending=root/(name+'.joint-update-pending')
            shutil.copy2(bundle/'payload'/name,pending);os.replace(pending,root/name)
        if manifest.is_file():
            content=json.loads(manifest.read_text())
            for name in names:content['files']['camera_easy/'+name]=sha(root/name)
            pending=manifest.with_suffix('.json.pending');pending.write_text(json.dumps(content,ensure_ascii=False,indent=2)+'\n');os.replace(pending,manifest)
    except BaseException:
        for name in names:
            if (backup/name).is_file():shutil.copy2(backup/name,root/name)
            elif (root/name).exists():(root/name).unlink()
        if (backup/'required_files.json').is_file():shutil.copy2(backup/'required_files.json',manifest)
        raise
    print('界面已更新：20261114-JOINT-GUI',flush=True)
    print('旧程序备份：'+str(backup),flush=True)
    print('请点击页面顶部“已有数据计算／验证”，无需重新录制。',flush=True)
    subprocess.run(['bash',str(root/'start.sh')],check=True)


if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:raise SystemExit('工具已关闭；原始数据和计算结果保留。')
    except Exception as exc:raise SystemExit('更新停止：'+str(exc))
