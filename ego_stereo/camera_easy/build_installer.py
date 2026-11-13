#!/usr/bin/env python3
"""Build camera.zip with one self-extracting camera.run; no dependency installation here."""
import argparse
import gzip
import hashlib
import io
import shutil
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
rm -f "$TMP/payload.gz"
if [[ "${1:-}" == --make-full ]]; then
  python3 "$TMP/content/source/ego_stereo/camera_easy/make_full.py" --source "$TMP/content/source" --output "$PWD/camera-full"
  exit 0
fi
if [[ "${1:-}" == --check ]]; then
  echo "安装包校验通过，未安装软件、未改变系统环境。"
  exit 0
fi
[[ "$EUID" -ne 0 ]] || { echo "请使用普通用户运行 bash camera.run，按提示输入 sudo 密码。"; exit 1; }
mkdir -p "$HOME/.local/share/ego-camera/releases"
DEST="$(mktemp -d "$HOME/.local/share/ego-camera/releases/v1.1_XXXXXXXX")"
cp -a "$TMP/content/source" "$DEST/"
export EGO_CAMERA_ARCHIVE_DIR="$BASE"
if [[ -s "$TMP/content/environment/kalibr-environment.tar.gz" ]]; then export EGO_CAMERA_ARCHIVE_DIR="$TMP/content"; fi
echo "开始安装双目相机标定工具。"
echo "系统依赖只需首次安装，按提示输入本机密码。"
bash "$DEST/source/ego_stereo/camera_easy/install.sh" "$@"
rm -rf -- "$TMP/content/environment"
echo "安装完成，正在打开相机标定入口。以后从应用菜单打开“双目相机标定”。"
bash "$DEST/source/ego_stereo/camera_easy/start.sh"
exit 0
__EGO_PAYLOAD_BELOW__
'''

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda:stream.read(1024*1024),b''):h.update(data)
    return h.hexdigest()

def build(repo, output, environment_image=None, source_snapshot=False):
    repo, output = Path(repo).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        source = root / 'source'; source.mkdir()
        if source_snapshot:
            shutil.copytree(repo,source,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','.git'))
            commit_file=repo.parent/'SOURCE_COMMIT.txt'
            commit=commit_file.read_text().strip() if commit_file.is_file() else 'snapshot-from-verified-installer'
        else:
            archive = subprocess.check_output(['git', '-C', str(repo), 'archive', 'HEAD'])
            with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
                tar.extractall(source, filter='data')
            commit = subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
        (root/'SOURCE_COMMIT.txt').write_text(commit+'\n')
        files = sorted(p for p in root.rglob('*') if p.is_file())
        sums=''.join(digest(p)+'  '+p.relative_to(root).as_posix()+'\n' for p in files)
        if environment_image:
            environment_image=Path(environment_image).resolve()
            sums+=digest(environment_image)+'  environment/kalibr-environment.tar.gz\n'
        (root/'SHA256SUMS').write_text(sums)
        payload=root/'payload.gz'
        with tarfile.open(payload,mode='w:gz',compresslevel=1) as tar:
            for item in sorted(root.iterdir()):
                if item!=payload:tar.add(item,arcname=item.name)
            if environment_image:tar.add(environment_image,arcname='environment/kalibr-environment.tar.gz')
        with (output/'camera.run').open('wb') as stream:
            stream.write(HEADER.replace('__PAYLOAD_SHA__',digest(payload)).encode())
            with payload.open('rb') as data:shutil.copyfileobj(data,stream,1024*1024)
        with zipfile.ZipFile(output/'camera.zip','w',zipfile.ZIP_STORED,allowZip64=True) as archive:
            archive.write(output/'camera.run','camera.run')
        (output/'camera.zip.sha256').write_text(digest(output/'camera.zip')+'  camera.zip\n')
        print(output/'camera.zip')

if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[2]);p.add_argument('--output',type=Path,required=True);p.add_argument('--environment-image',type=Path)
    a=p.parse_args();build(a.repo,a.output,a.environment_image)
