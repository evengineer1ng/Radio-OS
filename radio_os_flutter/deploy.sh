#!/usr/bin/env bash
# deploy.sh — push Radio OS Flutter source to the Pi and rebuild there.
# Usage: ./deploy.sh [pi-user@pi-host]
#
# Defaults:  PI_USER=pi   PI_HOST=raspberrypi.local
# Override:  ./deploy.sh evan@192.168.1.50

set -e

PI_TARGET="${1:-airfryer@airfryer.local}"
# Resolve the home directory on the remote side, don't hardcode /home/<user>
PI_APP_DIR="\$HOME/radio_os_flutter"
# We need the literal \$HOME in ssh commands, but a resolved path for rsync
PI_APP_DIR_RESOLVED="$(ssh "${PI_TARGET}" 'echo $HOME')/radio_os_flutter"

echo "▶  Syncing source to ${PI_TARGET}:${PI_APP_DIR_RESOLVED} ..."
rsync -avz --delete \
  --exclude='.dart_tool' \
  --exclude='build/' \
  --exclude='.git' \
  --exclude='macos/' \
  --exclude='*.iml' \
  "$(dirname "$0")/" \
  "${PI_TARGET}:${PI_APP_DIR_RESOLVED}/"

echo "▶  Building on Pi ..."
ssh "${PI_TARGET}" 'export PATH="$PATH:$HOME/flutter/bin" && cd ~/radio_os_flutter && flutter pub get --no-example && flutter build linux --release && echo "✓ Build complete"'
