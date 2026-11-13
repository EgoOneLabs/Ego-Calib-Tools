#!/usr/bin/env python3
"""Build camera.zip with one self-extracting camera.run; no dependency installation here."""
import argparse
import gzip
import hashlib
import io
from pathlib import Path
import subprocess
import tarfile
import tempfile
import zipfile

HEADER = r'''#!/usr/bin/env bash
set -euo pipefail
SELF="$(realpath -- "$0")"
BASE="$(dirname "$SELF")"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/ego-camera.XXXXXXXX")"
trap 'rm -rf -- "$TMP"' EXIT
LINE="$(awk '/^__EGO_PAYLOAD_BELOW__$/ {print NR+1;exit}' "$SELF")"
[[ -n "$LINE" ]] || { echo "安装包不完整，请重新下载。"; exit 1; }
tail -n +"$LINE" "$SELF" > "$TMP/payload.gz"
ACTUAL="$(sha256sum "$TMP/payload.gz")"
[[ "${ACTUAL%% *}" == "__PAYLOAD_SHA__" ]] || { echo "安装包校验失败，请重新下载。"; exit 1; }
mkdir "$TMP/content"
tar -xzf "$TMP/payload.gz" -C "$TMP/content"
(cd "$TMP/content" && sha256sum -c SHA256SUMS >/dev/null) || { echo "源码校验失败。"; exit 1; }
if [[ "${1:-}" == --check ]]; then
  echo "安装包校验通过，未安装软件、未改变系统环境。"
  exit 0
fi
[[ "$EUID" -ne 0 ]] || { echo "请使用普通用户运行 bash camera.run，按提示输入 sudo 密码。"; exit 1; }
mkdir -p "$HOME/.local/share/ego-camera/releases"
DEST="$(mktemp -d "$HOME/.local/share/ego-camera/releases/v1.1_XXXXXXXX")"
cp -a "$TMP/content/." "$DEST/"
export EGO_CAMERA_ARCHIVE_DIR="$BASE"
echo "开始安装双目相机标定工具。"
echo "系统依赖只需首次安装，按提示输入本机密码。"
bash "$DEST/source/ego_stereo/camera_easy/install.sh" "$@"
echo "安装完成，正在打开相机标定入口。以后从应用菜单打开“双目相机标定”。"
bash "$DEST/source/ego_stereo/camera_easy/start.sh"
exit 0
__EGO_PAYLOAD_BELOW__
'''

def build(repo, output):
    repo, output = Path(repo).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        source = root / 'source'; source.mkdir()
        archive = subprocess.check_output(['git', '-C', str(repo), 'archive', 'HEAD'])
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(source, filter='data')
        commit = subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
        (root/'SOURCE_COMMIT.txt').write_text(commit+'\n')
        files = sorted(p for p in root.rglob('*') if p.is_file())
        (root/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(root).as_posix()+'\n' for p in files))
        raw = io.BytesIO()
        with tarfile.open(fileobj=raw, mode='w') as tar:
            for p in sorted(root.iterdir()): tar.add(p, arcname=p.name)
        payload = gzip.compress(raw.getvalue(), compresslevel=9, mtime=0)
        script = HEADER.replace('__PAYLOAD_SHA__',hashlib.sha256(payload).hexdigest()).encode()+payload
        (output/'camera.run').write_bytes(script)
        with zipfile.ZipFile(output/'camera.zip','w',zipfile.ZIP_DEFLATED,compresslevel=9) as tar:
            tar.writestr('camera.run',script)
        (output/'camera.zip.sha256').write_text(hashlib.sha256((output/'camera.zip').read_bytes()).hexdigest()+'  camera.zip\n')
        print(output/'camera.zip')

if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[2]);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();build(a.repo,a.output)
