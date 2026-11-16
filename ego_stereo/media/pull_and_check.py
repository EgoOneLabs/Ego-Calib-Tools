#!/usr/bin/env python3
"""Pull the existing short acceptance session and run read-only media validation."""
import argparse
from datetime import datetime
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-root', type=Path, required=True, help='Explicit local parent for the pulled session and reports')
    p.add_argument('--serial', required=True, help='ADB serial from adb devices -l')
    p.add_argument('--remote-session', required=True, help='Absolute path of the selected exported phone session')
    a = p.parse_args()
    for tool in ('adb', 'ffmpeg', 'ffprobe'):
        if not shutil.which(tool):
            sys.exit('缺少命令：' + tool + '。请先安装对应工具。')
    a.output_root.mkdir(parents=True, exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix='camera_media_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '_', dir=a.output_root))
    print('结果目录：' + str(run), flush=True)
    subprocess.run(['adb', '-s', a.serial, 'get-state'], check=True)
    subprocess.run(['adb', '-s', a.serial, 'pull', a.remote_session, str(run / 'session')], check=True)
    result = subprocess.run([sys.executable, str(Path(__file__).with_name('check_session.py')),
                             '--session', str(run / 'session'), '--output', str(run / 'check')])
    print('\n请上传：' + str(run / 'check' / 'media_check.json'), flush=True)
    print('保留了本地 session 副本；没有修改或删除手机数据。', flush=True)
    return result.returncode


if __name__ == '__main__':
    sys.exit(main())
