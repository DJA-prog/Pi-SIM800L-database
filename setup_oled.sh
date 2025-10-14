#!/bin/bash
# Lightweight OLED Display Setup Script for SIM800L System (Pi Zero Optimized)

echo "🖥️ Setting up Lightweight OLED Display (SSD1306) for SIM800L System"
echo "======================================================================"

# Check if running as root for I2C setup
if [ "$EUID" -ne 0 ]; then
    echo "⚠️ This script needs to be run as root for I2C configuration"
    echo "Please run: sudo $0"
    exit 1
fi

# Enable I2C interface
echo "📡 Enabling I2C interface..."
raspi-config nonint do_i2c 0

# Install minimal system packages
echo "📦 Installing minimal system packages..."
apt-get update
apt-get install -y python3-pip i2c-tools

# Install Python requirements for OLED (no PIL - lightweight)
echo "🐍 Installing lightweight Python packages for OLED..."
pip3 install luma.oled requests

echo "🔍 Scanning for I2C devices..."
i2cdetect -y 1

echo ""
echo "✅ Lightweight OLED Setup Complete!"
echo ""
echo "� Display Layout:"
echo "   Line 1: IP: 192.168.1.100"
echo "   Line 2: Bat: 85%"
echo "   Line 3: SMS: 45"
echo ""
echo "🔌 Hardware Connections:"
echo "   VCC -> 3.3V (Pin 1)"
echo "   GND -> Ground (Pin 6)"
echo "   SCL -> GPIO 3 (Pin 5)"
echo "   SDA -> GPIO 2 (Pin 3)"
echo ""
echo "🧪 Test the display:"
echo "   python3 oled_display.py"
echo ""
echo "🚀 Start system with OLED:"
echo "   python3 sim800l_hat_db_api_batt.py"
echo ""
echo "⚡ Pi Zero Optimized:"
echo "   - Updates every 10 seconds"
echo "   - Minimal resource usage"
echo "   - No PIL dependency"
echo "   - Lightweight API calls"