#!/bin/bash

# Quick fix for OLED service user/group issues
# Run this on the Pi to fix the service configuration

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🔧 OLED Service Quick Fix${NC}"
echo "=========================="

# Get current user and directory
CURRENT_USER="$(whoami)"
CURRENT_DIR="$(pwd)"
SERVICE_FILE="/etc/systemd/system/oled-service.service"

echo -e "${BLUE}Current user: ${YELLOW}$CURRENT_USER${NC}"
echo -e "${BLUE}Current directory: ${YELLOW}$CURRENT_DIR${NC}"

# Stop the service if running
echo -e "${BLUE}🛑 Stopping service...${NC}"
sudo systemctl stop oled-service.service 2>/dev/null || true

# Check if user is in required groups
echo -e "${BLUE}👥 Checking user groups...${NC}"
if ! groups $CURRENT_USER | grep -q "i2c"; then
    echo -e "${YELLOW}Adding user to i2c group...${NC}"
    sudo usermod -a -G i2c $CURRENT_USER
fi

if ! groups $CURRENT_USER | grep -q "gpio"; then
    echo -e "${YELLOW}Adding user to gpio group...${NC}"
    sudo usermod -a -G gpio $CURRENT_USER
fi

# Create a new service file with correct user and paths
echo -e "${BLUE}⚙️  Creating new service file...${NC}"
sudo tee "$SERVICE_FILE" > /dev/null << EOF
[Unit]
Description=OLED Display API Service
Documentation=https://github.com/your-repo/oled-service
After=network.target
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=$CURRENT_USER
Group=$CURRENT_USER
WorkingDirectory=$CURRENT_DIR
Environment=PATH=$CURRENT_DIR/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ExecStartPre=/bin/sleep 5
ExecStart=$CURRENT_DIR/venv/bin/python3 $CURRENT_DIR/oled_api_service.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=oled-service

# Resource limits for Pi Zero W
MemoryLimit=128M
CPUQuota=25%

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/log $CURRENT_DIR

# I2C access
SupplementaryGroups=i2c gpio

[Install]
WantedBy=multi-user.target
EOF

echo -e "${GREEN}✅ Service file updated${NC}"

# Set proper permissions
echo -e "${BLUE}🔒 Setting permissions...${NC}"
sudo chown -R $CURRENT_USER:$CURRENT_USER "$CURRENT_DIR"
chmod +x "$CURRENT_DIR/oled_api_service.py"

# Create log file with proper permissions
LOG_FILE="/var/log/oled-service.log"
sudo touch "$LOG_FILE"
sudo chown $CURRENT_USER:$CURRENT_USER "$LOG_FILE"
sudo chmod 664 "$LOG_FILE"

# Reload systemd
sudo systemctl daemon-reload

echo -e "${GREEN}✅ Service configuration fixed${NC}"
echo
echo -e "${BLUE}📋 Next steps:${NC}"
echo "1. Start the service:"
echo "   sudo systemctl start oled-service"
echo
echo "2. Check status:"
echo "   sudo systemctl status oled-service"
echo
echo "3. Enable auto-start:"
echo "   sudo systemctl enable oled-service"
echo
echo "4. Test API:"
echo "   curl http://localhost:5001/api/health"
echo
echo -e "${YELLOW}⚠️  Note: You may need to log out and back in for group changes to take effect.${NC}"
EOF