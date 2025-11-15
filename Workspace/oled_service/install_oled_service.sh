#!/bin/bash

# OLED Display Service Installation Script for Raspberry Pi Zero W
# This script sets up the OLED display service with proper permissions and configuration

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SERVICE_NAME="oled-service"
SERVICE_USER="$(whoami)"
SERVICE_DIR="$(pwd)"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
LOG_FILE="/var/log/oled-service.log"

echo -e "${BLUE}🚀 OLED Display Service Installation${NC}"
echo "=================================="

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   echo -e "${RED}❌ This script should not be run as root${NC}"
   echo "Please run as your regular user: ./install_oled_service.sh"
   exit 1
fi

# Check if we're on a Raspberry Pi
if ! grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null; then
    echo -e "${YELLOW}⚠️  Warning: This doesn't appear to be a Raspberry Pi${NC}"
    read -p "Continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo -e "${BLUE}📋 Pre-installation checks...${NC}"

# Check for I2C
if ! lsmod | grep -q i2c_dev; then
    echo -e "${YELLOW}⚠️  I2C module not loaded. Enabling I2C...${NC}"
    sudo raspi-config nonint do_i2c 0
    echo -e "${GREEN}✅ I2C enabled. You may need to reboot after installation.${NC}"
fi

# Check for required packages
echo -e "${BLUE}📦 Checking system packages...${NC}"
REQUIRED_PACKAGES="python3 python3-pip python3-venv i2c-tools"
for package in $REQUIRED_PACKAGES; do
    if ! dpkg -l | grep -q "^ii  $package "; then
        echo -e "${YELLOW}📦 Installing $package...${NC}"
        sudo apt-get update -qq
        sudo apt-get install -y $package
    else
        echo -e "${GREEN}✅ $package already installed${NC}"
    fi
done

# Create service directory
echo -e "${BLUE}📁 Setting up service directory...${NC}"
mkdir -p "$SERVICE_DIR"
cd "$SERVICE_DIR"

# Copy service files
echo -e "${BLUE}📄 Setting up service files...${NC}"
SCRIPT_DIR="$(dirname "$0")"
CURRENT_DIR="$(pwd)"

# Check if we're already in the service directory
if [ "$SCRIPT_DIR" = "." ] || [ "$SCRIPT_DIR" = "$CURRENT_DIR" ]; then
    echo -e "${GREEN}✅ Already in service directory${NC}"
    # Just verify files exist
    if [ ! -f "oled_api_service.py" ] || [ ! -f "oled_display.py" ] || [ ! -f "requirements.txt" ]; then
        echo -e "${RED}❌ Required service files missing${NC}"
        exit 1
    fi
else
    # Copy files from source directory
    if [ -f "$SCRIPT_DIR/oled_api_service.py" ]; then
        cp "$SCRIPT_DIR/oled_api_service.py" .
        cp "$SCRIPT_DIR/oled_display.py" .
        cp "$SCRIPT_DIR/requirements.txt" .
        cp "$SCRIPT_DIR/.env.oled.template" .
        echo -e "${GREEN}✅ Service files copied${NC}"
    else
        echo -e "${RED}❌ Service files not found in source directory${NC}"
        exit 1
    fi
fi

# Create config if it doesn't exist
if [ ! -f ".env.oled" ]; then
    if [ -f ".env.oled.template" ]; then
        cp ".env.oled.template" ".env.oled"
        echo -e "${GREEN}✅ Created default configuration file${NC}"
    else
        echo -e "${RED}❌ Configuration template not found${NC}"
        exit 1
    fi
else
    echo -e "${YELLOW}⚠️  Configuration file exists, not overwriting${NC}"
fi

# Set up Python virtual environment
echo -e "${BLUE}🐍 Setting up Python virtual environment...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo -e "${GREEN}✅ Virtual environment created${NC}"
fi

# Activate virtual environment and install dependencies
echo -e "${BLUE}📦 Installing Python dependencies...${NC}"
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
deactivate

echo -e "${GREEN}✅ Python dependencies installed${NC}"

# Set up logging
echo -e "${BLUE}📝 Setting up logging...${NC}"
sudo touch "$LOG_FILE"
sudo chown $SERVICE_USER:$SERVICE_USER "$LOG_FILE"
sudo chmod 664 "$LOG_FILE"

# Add user to required groups
echo -e "${BLUE}👥 Adding user to required groups...${NC}"
sudo usermod -a -G i2c,gpio $SERVICE_USER

# Install systemd service
echo -e "${BLUE}⚙️  Installing systemd service...${NC}"
SCRIPT_DIR="$(dirname "$0")"

# Look for service template first, then regular service file
if [ -f "oled-service.service.template" ]; then
    SERVICE_TEMPLATE="./oled-service.service.template"
elif [ -f "$SCRIPT_DIR/oled-service.service.template" ]; then
    SERVICE_TEMPLATE="$SCRIPT_DIR/oled-service.service.template"
elif [ -f "oled-service.service" ]; then
    SERVICE_TEMPLATE="./oled-service.service"
elif [ -f "$SCRIPT_DIR/oled-service.service" ]; then
    SERVICE_TEMPLATE="$SCRIPT_DIR/oled-service.service"
else
    echo -e "${RED}❌ Service file not found${NC}"
    exit 1
fi

# Create service file from template
cp "$SERVICE_TEMPLATE" "/tmp/oled-service.service"
sed -i "s|__SERVICE_USER__|$SERVICE_USER|g" "/tmp/oled-service.service"
sed -i "s|__SERVICE_DIR__|$SERVICE_DIR|g" "/tmp/oled-service.service"

# Install the configured service file
sudo cp "/tmp/oled-service.service" "$SERVICE_FILE"
rm "/tmp/oled-service.service"

sudo systemctl daemon-reload
echo -e "${GREEN}✅ Service file installed${NC}"

# Set proper permissions
echo -e "${BLUE}🔒 Setting permissions...${NC}"
sudo chown -R $SERVICE_USER:$SERVICE_USER "$SERVICE_DIR"
chmod +x "$SERVICE_DIR/oled_api_service.py"

# Test I2C connectivity
echo -e "${BLUE}🔍 Testing I2C connectivity...${NC}"
if command -v i2cdetect >/dev/null 2>&1; then
    echo "Scanning I2C bus 1 for devices:"
    i2cdetect -y 1 2>/dev/null || echo -e "${YELLOW}⚠️  Could not scan I2C bus (this is normal if no devices are connected)${NC}"
else
    echo -e "${YELLOW}⚠️  i2cdetect not available${NC}"
fi

echo
echo -e "${GREEN}🎉 Installation completed successfully!${NC}"
echo
echo -e "${BLUE}📋 Next steps:${NC}"
echo "1. Connect your SSD1306 OLED display to I2C pins (SDA=GPIO2, SCL=GPIO3)"
echo "2. Configure the service:"
echo "   nano $SERVICE_DIR/.env.oled"
echo
echo "3. Enable and start the service:"
echo "   sudo systemctl enable $SERVICE_NAME"
echo "   sudo systemctl start $SERVICE_NAME"
echo
echo "4. Check service status:"
echo "   sudo systemctl status $SERVICE_NAME"
echo
echo "5. View logs:"
echo "   sudo journalctl -u $SERVICE_NAME -f"
echo "   tail -f $LOG_FILE"
echo
echo "6. Test the API:"
echo "   curl http://localhost:5001/api/health"
echo
echo -e "${YELLOW}⚠️  Important: You may need to reboot if I2C was just enabled.${NC}"
echo
echo -e "${BLUE}📚 API Documentation:${NC}"
echo "   Health Check:     GET  /api/health"
echo "   Service Status:   GET  /api/status"
echo "   Update Display:   POST /api/display/update"
echo "   Set Mode:         POST /api/display/mode"
echo "   Clear Display:    POST /api/display/clear"
echo "   Custom Text:      POST /api/display/text"
echo "   Configuration:    GET  /api/config"