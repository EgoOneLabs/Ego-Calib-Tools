#!/usr/bin/env bash
# Public download/install entry; no GitHub login or source checkout required.
set -euo pipefail
DEST="$HOME/Downloads/Ego-camera-v1.2"
BASE="https://github.com/EgoOneLabs/Ego-Calib-Tools/releases/download"
mkdir -p "$DEST"
cd "$DEST"
fetch() {
  curl --fail --location --retry 5 --retry-all-errors --retry-delay 3 \
    --connect-timeout 20 --speed-limit 1024 --speed-time 60 "$@"
}
fetch --output camera-color.zip "$BASE/camera-easy-v1.2/camera-color.zip"
fetch --output camera-color.zip.sha256 "$BASE/camera-easy-v1.2/camera-color.zip.sha256"
sha256sum -c camera-color.zip.sha256
unzip -oq camera-color.zip camera.run
D=(docker)
if ! docker info >/dev/null 2>&1; then sudo -v; D=(sudo -n docker); fi
# An existing installation needs only the small updated program.
if "${D[@]}" container inspect kalibr >/dev/null 2>&1 ||
   "${D[@]}" container inspect ego-camera-kalibr >/dev/null 2>&1 ||
   "${D[@]}" image inspect kalibr:noetic >/dev/null 2>&1; then
  exec bash camera.run
fi
for NUMBER in {000..008}; do
  NAME="camera.zip.part-$NUMBER"
  EXPECTED=209715200
  if [[ "$NUMBER" == 008 ]]; then EXPECTED=125244339; fi
  CURRENT=0
  if [[ -f "$NAME" ]]; then CURRENT="$(stat -c %s "$NAME")"; fi
  if [[ "$CURRENT" == "$EXPECTED" ]]; then echo "已下载，跳过：$NAME"; continue; fi
  if (( CURRENT > EXPECTED )); then echo "文件大小异常：$NAME"; exit 1; fi
  echo "正在下载环境分卷：$NAME"
  fetch --continue-at - --output "$NAME" "$BASE/camera-easy-v1/$NAME"
  test "$(stat -c %s "$NAME")" -eq "$EXPECTED"
done
fetch --output camera.zip.sha256 "$BASE/camera-easy-v1/camera.zip.sha256"
if ! sha256sum -c camera.zip.sha256 >/dev/null 2>&1; then
  cat camera.zip.part-00{0..8} > camera.zip.partial
  mv camera.zip.partial camera.zip
fi
sha256sum -c camera.zip.sha256
# Use v1 only as an environment archive; run the corrected v1.2 program.
exec bash camera.run --environment-package "$DEST/camera.zip"
