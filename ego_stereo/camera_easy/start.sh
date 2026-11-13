#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for name in python3 ffmpeg v4l2-ctl docker; do
  command -v "$name" >/dev/null || { echo "缺少 $name，请先运行：bash $ROOT/install.sh"; exit 1; }
done
/usr/bin/python3 -c 'import cv2,numpy,yaml' || { echo "请先运行 install.sh 安装 Python 依赖。"; exit 1; }
ARGS=()
if ! docker info >/dev/null 2>&1; then
  echo "首次使用 Docker 需要权限，正在申请 sudo；后续可注销并重新登录以启用 docker 用户组。"
  sudo -v
  ARGS+=(--sudo-docker)
fi
exec /usr/bin/python3 "$ROOT/app.py" "${ARGS[@]}" "$@"
