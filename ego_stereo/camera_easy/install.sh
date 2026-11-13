#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[[ "$EUID" -ne 0 ]] || { echo "请使用普通用户运行 bash install.sh，脚本会按需申请 sudo。"; exit 1; }
source /etc/os-release
[[ "${ID:-}" == ubuntu && ( "${VERSION_ID:-}" == 22.04 || "${VERSION_ID:-}" == 24.04 ) ]] || {
  echo "本安装入口面向 Ubuntu 22.04/24.04 桌面版；其他发行版请手动安装依赖。"; exit 1;
}
sudo apt-get update
PACKAGES=(python3 python3-opencv python3-numpy python3-yaml ffmpeg v4l-utils xdg-utils zenity)
command -v docker >/dev/null || PACKAGES+=(docker.io)
sudo apt-get install -y "${PACKAGES[@]}"
sudo systemctl enable --now docker
sudo groupadd -f docker
sudo usermod -aG docker,video "$(id -un)"
printf '%s\n' 'SUBSYSTEM=="video4linux", ATTRS{idVendor}=="1bcf", ATTRS{idProduct}=="0b15", GROUP="video", MODE="0660", TAG+="uaccess"' |
  sudo tee /etc/udev/rules.d/70-ego-2uq2-camera.rules >/dev/null
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=video4linux
ARGS=()
if ! docker info >/dev/null 2>&1; then ARGS+=(--sudo-docker); fi
D=(docker)
if ((${#ARGS[@]})); then D=(sudo -n docker); fi
ARCHIVE="${1:-}"
if ! "${D[@]}" container inspect kalibr >/dev/null 2>&1 &&
   ! "${D[@]}" container inspect ego-camera-kalibr >/dev/null 2>&1 &&
   ! "${D[@]}" image inspect kalibr:noetic >/dev/null 2>&1; then
  if [[ -z "$ARCHIVE" ]]; then
    echo "请选择已下载的 Kalibr 环境镜像 kalibr-environment.tar.gz。"
    ARCHIVE="$(zenity --file-selection --title='选择 Kalibr 环境镜像 kalibr-environment.tar.gz')" || exit 1
  fi
  [[ -s "$ARCHIVE" ]] || { echo "找不到镜像文件：$ARCHIVE"; exit 1; }
  ARGS+=(--image-archive "$ARCHIVE")
fi
/usr/bin/python3 "$ROOT/app.py" "${ARGS[@]}" --setup-only
/usr/bin/python3 - "$ROOT" <<'PY'
from pathlib import Path
import os
import sys
root = Path(sys.argv[1]).resolve()
# Desktop Exec quotes must follow the desktop-entry quoting syntax.
quoted = str(root / 'start.sh').replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%')
text = '[Desktop Entry]\nType=Application\nName=双目相机标定\nComment=固定头环、移动标定板，自动生成相机标定报告\nExec=/usr/bin/bash "' + quoted + '"\nTerminal=true\nIcon=camera-photo\nCategories=Science;Education;\n'
apps = Path.home() / '.local/share/applications'; apps.mkdir(parents=True, exist_ok=True)
(apps / 'ego-camera-calibration.desktop').write_text(text)
print('已添加应用菜单入口：双目相机标定。也可直接运行 start.sh。')
PY
printf '\n环境配置完成。请重新插拔头环；首次建议注销并登录，以生效 Docker/video 用户组。\n'
printf '之后运行：bash "%s/start.sh"\n' "$ROOT"
