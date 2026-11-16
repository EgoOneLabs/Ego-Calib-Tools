#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[[ "$EUID" -ne 0 ]] || { echo "Run bash install.sh as your normal user; sudo will be requested when needed."; exit 1; }
source /etc/os-release
[[ "${ID:-}" == ubuntu && ( "${VERSION_ID:-}" == 22.04 || "${VERSION_ID:-}" == 24.04 ) ]] || {
  echo "This installer targets Ubuntu 22.04/24.04 desktop. Other distributions require manual dependency setup."; exit 1;
}
sudo apt-get update
PACKAGES=(python3 python3-opencv python3-numpy python3-yaml python3-matplotlib python3-scipy ffmpeg v4l-utils xdg-utils zenity)
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
    for BASE in "${EGO_CAMERA_ARCHIVE_DIR:-$PWD}" "$PWD" "$ROOT"; do
      for NAME in kalibr-environment.tar.gz environment/kalibr-environment.tar.gz; do
        if [[ -s "$BASE/$NAME" ]]; then ARCHIVE="$BASE/$NAME"; break 2; fi
      done
    done
  fi
  if [[ -z "$ARCHIVE" ]]; then
    echo "Select the downloaded Kalibr image: kalibr-environment.tar.gz."
    ARCHIVE="$(zenity --file-selection --title='Select Kalibr image: kalibr-environment.tar.gz')" || exit 1
  fi
  [[ -s "$ARCHIVE" ]] || { echo "Image archive not found: $ARCHIVE"; exit 1; }
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
text = '[Desktop Entry]\nType=Application\nName=Headband Calibration Tool\nName[zh_CN]=头环标定工具\nComment=Camera, IMU and Camera–IMU calibration\nComment[zh_CN]=Camera、IMU 与 Camera–IMU 标定\nExec=/usr/bin/bash "' + quoted + '"\nTerminal=true\nIcon=camera-photo\nCategories=Science;Education;\n'
apps = Path.home() / '.local/share/applications'; apps.mkdir(parents=True, exist_ok=True)
(apps / 'ego-camera-calibration.desktop').write_text(text)
print('Application menu entry added: Headband Calibration Tool. You can also run start.sh.')
PY
printf '\nEnvironment setup complete. Reconnect the headband. Log out and back in to apply Docker/video group membership.\n'
printf 'To start later: bash "%s/start.sh"\n' "$ROOT"
