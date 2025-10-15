#!/bin/bash
# Test WiFi Fallback Script
# This script tests the WiFi fallback functionality without waiting for boot

set -e

SCRIPT_DIR="/home/dino/Documents/Shootecc/Coding"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "This script must be run as root (use sudo)"
    exit 1
fi

echo "🧪 Testing WiFi Fallback Script"
echo "==============================="

# Test 1: Check if script exists and is executable
echo "📄 Checking script file..."
if [ -x "$SCRIPT_DIR/wifi_to_ad_hoc.sh" ]; then
    echo "✅ Script file exists and is executable"
else
    echo "❌ Script file missing or not executable"
    exit 1
fi

# Test 2: Check required commands
echo "🔧 Checking required commands..."
MISSING_COMMANDS=""

for cmd in hostapd dnsmasq iwconfig ping ip; do
    if ! command -v $cmd >/dev/null 2>&1; then
        MISSING_COMMANDS="$MISSING_COMMANDS $cmd"
    fi
done

if [ -n "$MISSING_COMMANDS" ]; then
    echo "❌ Missing commands: $MISSING_COMMANDS"
    echo "Install with: sudo apt-get install hostapd dnsmasq wireless-tools"
    exit 1
else
    echo "✅ All required commands available"
fi

# Test 3: Check WiFi interface
echo "📡 Checking WiFi interface..."
if ip link show wlan0 >/dev/null 2>&1; then
    echo "✅ WiFi interface wlan0 found"
    
    # Show current status
    echo "   Current status:"
    if ip addr show wlan0 | grep -q "inet "; then
        IP=$(ip addr show wlan0 | grep "inet " | awk '{print $2}' | cut -d/ -f1)
        echo "   - IP Address: $IP"
    else
        echo "   - No IP address assigned"
    fi
    
    if iwconfig wlan0 2>/dev/null | grep -q "Access Point"; then
        SSID=$(iwconfig wlan0 2>/dev/null | grep "ESSID" | cut -d'"' -f2)
        echo "   - Connected to: $SSID"
    else
        echo "   - Not connected to any network"
    fi
else
    echo "❌ WiFi interface wlan0 not found"
    exit 1
fi

# Test 4: Check internet connectivity
echo "🌐 Checking current internet connectivity..."
if ping -c 1 -W 5 8.8.8.8 >/dev/null 2>&1; then
    echo "✅ Internet connectivity available"
    echo "   (Script would exit normally in this case)"
else
    echo "⚠️ No internet connectivity"
    echo "   (Script would activate AP mode in this case)"
fi

# Test 5: Dry run configuration check
echo "⚙️ Checking AP configuration..."
HOSTNAME=$(hostname | tail -c 5)
echo "   Emergency SSID would be: RPI-Emergency-$HOSTNAME"
echo "   Password would be: raspberry123"
echo "   AP IP would be: 192.168.4.1"

echo ""
echo "🎯 Test Summary:"
echo "   ✅ Script ready to run"
echo "   ✅ All dependencies available"
echo "   ✅ WiFi interface present"

echo ""
echo "🚀 To install and enable at boot:"
echo "   sudo $SCRIPT_DIR/install_wifi_fallback.sh"
echo ""
echo "🧪 To test manually (will activate AP if no WiFi):"
echo "   sudo $SCRIPT_DIR/wifi_to_ad_hoc.sh"
echo ""
echo "📊 To monitor in real-time:"
echo "   sudo tail -f /var/log/wifi-fallback.log"