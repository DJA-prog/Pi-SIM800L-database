#!/bin/bash
# Install WiFi Fallback Service
# Run this script as root to install the WiFi fallback service

set -e

SCRIPT_DIR="/home/dino/Documents/Shootecc/Coding"
SERVICE_NAME="wifi-fallback"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "This script must be run as root (use sudo)"
    exit 1
fi

echo "🔧 Installing WiFi Fallback Service..."

# Check required packages
echo "📦 Checking required packages..."
PACKAGES_NEEDED=""

if ! command -v hostapd >/dev/null 2>&1; then
    PACKAGES_NEEDED="$PACKAGES_NEEDED hostapd"
fi

if ! command -v dnsmasq >/dev/null 2>&1; then
    PACKAGES_NEEDED="$PACKAGES_NEEDED dnsmasq"
fi

if ! command -v iwconfig >/dev/null 2>&1; then
    PACKAGES_NEEDED="$PACKAGES_NEEDED wireless-tools"
fi

if [ -n "$PACKAGES_NEEDED" ]; then
    echo "Installing required packages: $PACKAGES_NEEDED"
    apt-get update
    apt-get install -y $PACKAGES_NEEDED
fi

# Copy service file to systemd directory
echo "📋 Installing systemd service..."
cp "$SCRIPT_DIR/wifi-fallback.service" /etc/systemd/system/

# Reload systemd and enable service
systemctl daemon-reload
systemctl enable $SERVICE_NAME.service

echo "✅ WiFi Fallback Service installed successfully!"
echo ""
echo "📝 Configuration:"
echo "   - Check timeout: 60 seconds"
echo "   - Emergency SSID: RPI-Emergency-$(hostname | tail -c 5)"
echo "   - Password: raspberry123"
echo "   - AP IP: 192.168.4.1"
echo "   - Log file: /var/log/wifi-fallback.log"
echo ""
echo "🔧 Manual commands:"
echo "   Start service:  sudo systemctl start $SERVICE_NAME"
echo "   Stop service:   sudo systemctl stop $SERVICE_NAME"
echo "   Check status:   sudo systemctl status $SERVICE_NAME"
echo "   View logs:      sudo journalctl -u $SERVICE_NAME -f"
echo "   Disable auto:   sudo systemctl disable $SERVICE_NAME"
echo ""
echo "🔄 The service will automatically start on next reboot."
echo "   To test immediately: sudo systemctl start $SERVICE_NAME"