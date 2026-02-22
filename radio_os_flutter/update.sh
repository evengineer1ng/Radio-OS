#!/usr/bin/env bash
# update.sh — one-command: sync + build + restart on the Pi.
# Usage: ./update.sh [pi-user@pi-host]
#
# This is the normal development update loop:
#   edit code on Mac → ./update.sh → see it on the Pi

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PI_TARGET="${1:-airfryer@airfryer.local}"

echo "═══════════════════════════════════════════"
echo " Radio OS Flutter — deploy + restart"
echo " Target: ${PI_TARGET}"
echo "═══════════════════════════════════════════"

"${SCRIPT_DIR}/deploy.sh"  "${PI_TARGET}"
"${SCRIPT_DIR}/run_on_pi.sh" "${PI_TARGET}"

echo "✓ Done — Radio OS updated and restarted on ${PI_TARGET}"
