#!/bin/bash
# Disable AP Services Script
# Use this script to manually ensure hostapd and dnsmasq are stopped and disabled

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "This script must be run as root (use sudo)"
    exit 1
fi

echo "🔧 Disabling AP services for normal WiFi operation..."

# Stop any running services
echo "Stopping services..."
systemctl stop hostapd 2>/dev/null || true
systemctl stop dnsmasq 2>/dev/null || true

# Disable automatic startup
echo "Disabling automatic startup..."
systemctl disable hostapd 2>/dev/null || true
systemctl disable dnsmasq 2>/dev/null || true

# Kill any emergency instances
echo "Stopping emergency instances..."
pkill -f "hostapd.*emergency" 2>/dev/null || true
pkill -f "dnsmasq.*emergency" 2>/dev/null || true

# Clean up any temporary files
echo "Cleaning up temporary files..."
rm -f /tmp/hostapd_emergency.conf /tmp/dnsmasq_emergency.conf
rm -f /tmp/hostapd_emergency.pid /tmp/dnsmasq_emergency.pid /tmp/emergency_web.pid
rm -rf /tmp/emergency_web

# Check status
echo ""
echo "📊 Service Status:"
echo "hostapd: $(systemctl is-active hostapd 2>/dev/null || echo 'inactive')"
echo "dnsmasq: $(systemctl is-active dnsmasq 2>/dev/null || echo 'inactive')"
echo ""
echo "Auto-start Status:"
echo "hostapd: $(systemctl is-enabled hostapd 2>/dev/null || echo 'disabled')"
echo "dnsmasq: $(systemctl is-enabled dnsmasq 2>/dev/null || echo 'disabled')"

echo ""
echo "✅ AP services disabled - WiFi ready for normal operation"
echo "💡 These services will only be used for emergency AP mode when WiFi fails"