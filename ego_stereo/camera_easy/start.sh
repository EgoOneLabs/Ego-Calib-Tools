#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for name in python3 ffmpeg v4l2-ctl docker; do
  command -v "$name" >/dev/null || { echo "Missing $name. First run: bash $ROOT/install.sh"; exit 1; }
done
/usr/bin/python3 -c 'import cv2,numpy,yaml' || { echo "First run install.sh to install Python dependencies."; exit 1; }
ARGS=()
if ! docker info >/dev/null 2>&1; then
  echo "Docker access requires permission. Requesting sudo; log out and back in later to apply docker group membership."
  sudo -v
  ARGS+=(--sudo-docker)
fi
exec /usr/bin/python3 "$ROOT/app.py" "${ARGS[@]}" "$@"
