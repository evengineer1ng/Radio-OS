#!/usr/bin/env bash
# deploy_oled.sh — Push the OLED Soul Display daemon to a Pi and install it as a systemd service.
#
# Usage:
#   ./deploy_oled.sh [user@host]
#
# Defaults to airfryer@airfryer.local.

set -euo pipefail

TARGET="${1:-airfryer@airfryer.local}"
REMOTE_DIR="/home/airfryer/Radio-OS-1.03"

echo "==> Deploying OLED Soul daemon to ${TARGET}:${REMOTE_DIR}"

# ── 1. Sync daemon files ──────────────────────────────────────────────────────
echo "==> Syncing tools/ files..."
rsync -avz --progress \
    tools/oled_soul_daemon.py \
    tools/oled_event_client.py \
    tools/oled_event_send.py \
    tools/oled_broadcast.py \
    "${TARGET}:${REMOTE_DIR}/tools/"

# ── 2. Sync service file ──────────────────────────────────────────────────────
echo "==> Uploading service file..."
rsync -avz oled-soul.service "${TARGET}:/tmp/oled-soul.service"

# ── 3. Remote provisioning ────────────────────────────────────────────────────
echo "==> Running remote setup (sudo required on Pi)..."
ssh "${TARGET}" bash -s << 'REMOTE'
set -euo pipefail

REMOTE_DIR="/home/airfryer/Radio-OS-1.03"
VENV="${REMOTE_DIR}/radioenv/bin/python"
PIP="${REMOTE_DIR}/radioenv/bin/pip"

# Enable SPI if not already enabled
echo "  -> Enabling SPI..."
sudo raspi-config nonint do_spi 0 || true

# Install Python deps into the project virtualenv
echo "  -> Installing luma.oled / Pillow into venv..."
"${PIP}" install --quiet --upgrade luma.oled luma.core Pillow

# Install systemd service
echo "  -> Installing systemd service..."
sudo cp /tmp/oled-soul.service /etc/systemd/system/oled-soul.service
sudo systemctl daemon-reload
sudo systemctl enable oled-soul.service
sudo systemctl restart oled-soul.service

# Brief wait then check
sleep 2
STATUS=$(sudo systemctl is-active oled-soul.service || true)
echo "  -> oled-soul.service status: ${STATUS}"
REMOTE

# ── 4. Smoke-test: send a test event ─────────────────────────────────────────
echo "==> Sending test event..."
ssh "${TARGET}" bash -s << REMOTE2
cd /home/airfryer/Radio-OS-1.03
radioenv/bin/python tools/oled_event_send.py boot || true
REMOTE2

echo ""
echo "✅  OLED Soul daemon deployed to ${TARGET}"
echo "   Logs: ssh ${TARGET} tail -f ~/oled_daemon.log"
echo "   Status: ssh ${TARGET} sudo systemctl status oled-soul.service"
