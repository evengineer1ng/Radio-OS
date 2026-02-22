#!/usr/bin/env bash
# run_on_pi.sh — start Radio OS Flutter on the Pi (with a virtual display if headless).
# Usage: ./run_on_pi.sh [pi-user@pi-host]
#
# The app is launched detached so it survives SSH session end.
# Output goes to ~/radio_os_flutter.log.

set -e

PI_TARGET="${1:-airfryer@airfryer.local}"
PI_HOME="$(ssh "${PI_TARGET}" 'echo $HOME')"
BUNDLE="${PI_HOME}/radio_os_flutter/build/linux/arm64/release/bundle"
BINARY="${BUNDLE}/radio_os_flutter"
LOG="${PI_HOME}/radio_os_flutter.log"

echo "▶  Launching Radio OS on ${PI_TARGET} ..."
ssh "${PI_TARGET}" 'pkill -f radio_os_flutter || true; sleep 0.5; export DISPLAY=:0; export LIBGL_ALWAYS_SOFTWARE=1; nohup $HOME/radio_os_flutter/build/linux/arm64/release/bundle/radio_os_flutter > $HOME/radio_os_flutter.log 2>&1 & echo "Launched PID $!"'
