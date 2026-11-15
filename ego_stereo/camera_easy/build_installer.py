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
[[ -n "$LINE" ]] || { echo "Incomplete installer. Download it again."; exit 1; }
tail -n +"$LINE" "$SELF" > "$TMP/payload.gz"
ACTUAL="$(sha256sum "$TMP/payload.gz")"
[[ "${ACTUAL%% *}" == "__PAYLOAD_SHA__" ]] || { echo "Installer checksum failed. Download it again."; exit 1; }
mkdir "$TMP/content"
tar -xzf "$TMP/payload.gz" -C "$TMP/content"
(cd "$TMP/content" && sha256sum -c SHA256SUMS >/dev/null) || { echo "Source checksum failed."; exit 1; }
rm -f "$TMP/payload.gz"
if [[ "${1:-}" == --make-full ]]; then
  python3 "$TMP/content/source/ego_stereo/camera_easy/make_full.py" --source "$TMP/content/source" --output "$PWD/camera-full" --archive-dir "$BASE" "${@:2}"
  exit 0
fi
if [[ "${1:-}" == --check ]]; then
  echo "Installer checks passed. No software was installed and no system settings were changed."
  exit 0
fi
if [[ "${1:-}" == --environment-package ]]; then
  [[ -f "${2:-}" ]] || { echo "Downloaded complete environment package not found."; exit 1; }
  python3 "$TMP/content/source/ego_stereo/camera_easy/extract_environment.py" "$2" "$TMP/content/environment/kalibr-environment.tar.gz"
  shift 2
fi
[[ "$EUID" -ne 0 ]] || { echo "Run bash camera.run as your normal user and enter the sudo password when requested."; exit 1; }
mkdir -p "$HOME/.local/share/ego-camera/releases"
DEST="$(mktemp -d "$HOME/.local/share/ego-camera/releases/v1.9-bilingual_XXXXXXXX")"
cp -a "$TMP/content/source" "$DEST/"
export EGO_CAMERA_ARCHIVE_DIR="$BASE"
if [[ -s "$TMP/content/environment/kalibr-environment.tar.gz" ]]; then export EGO_CAMERA_ARCHIVE_DIR="$TMP/content"; fi
echo "Installing Headband Calibration Tool."
echo "System dependency setup may request your local sudo password."
bash "$DEST/source/ego_stereo/camera_easy/install.sh" "$@"
rm -rf -- "$TMP/content/environment"
echo "Installation complete. Opening Headband Calibration Tool. Use the application menu to start it later."
bash "$DEST/source/ego_stereo/camera_easy/start.sh"
exit 0
__EGO_PAYLOAD_BELOW__
'''

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda:stream.read(1024*1024),b''):h.update(data)
    return h.hexdigest()

def build(repo, output, environment_image=None, source_snapshot=False, retain_run=True):
    repo, output = Path(repo).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if environment_image:
        needed=Path(environment_image).stat().st_size*2+512*1024**2
        free=shutil.disk_usage(output).free
        if free<needed:raise RuntimeError(f'打包磁盘空间不足：需要约 {needed/1024**3:.1f} GiB，可用 {free/1024**3:.1f} GiB。请用 --output 指定另一块磁盘。')
    with tempfile.TemporaryDirectory(prefix='.camera-build-',dir=output) as folder:
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
        header=HEADER.replace('__PAYLOAD_SHA__',digest(payload)).encode()
        pending=root/'camera.zip.partial'
        with zipfile.ZipFile(pending,'w',zipfile.ZIP_STORED,allowZip64=True) as archive:
            with archive.open('camera.run','w',force_zip64=True) as stream:
                stream.write(header)
                with payload.open('rb') as data:shutil.copyfileobj(data,stream,1024*1024)
        pending.replace(output/'camera.zip')
        if retain_run:
            with (output/'camera.run').open('wb') as stream:
                stream.write(header)
                with payload.open('rb') as data:shutil.copyfileobj(data,stream,1024*1024)
        (output/'camera.zip.sha256').write_text(digest(output/'camera.zip')+'  camera.zip\n')
        print(output/'camera.zip')

if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[2]);p.add_argument('--output',type=Path,required=True);p.add_argument('--environment-image',type=Path)
    a=p.parse_args();build(a.repo,a.output,a.environment_image)
