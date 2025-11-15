#!/bin/bash

# Fix permissions for OLED service
# This resolves the systemd CHDIR permission denied error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🔧 Fixing OLED Service Permissions${NC}"
echo "=================================="

CURRENT_USER="$(whoami)"
CURRENT_DIR="$(pwd)"

echo -e "${BLUE}Current user: ${YELLOW}$CURRENT_USER${NC}"
echo -e "${BLUE}Current directory: ${YELLOW}$CURRENT_DIR${NC}"

# Stop the service
echo -e "${BLUE}🛑 Stopping service...${NC}"
sudo systemctl stop oled-service 2>/dev/null || true

# Fix directory permissions
echo -e "${BLUE}🔒 Fixing directory permissions...${NC}"
chmod 755 "$CURRENT_DIR"
chmod 755 "$HOME"

# Make sure parent directories are accessible
PARENT_DIR="$(dirname "$CURRENT_DIR")"
while [ "$PARENT_DIR" != "/" ] && [ "$PARENT_DIR" != "$HOME" ]; do
    chmod 755 "$PARENT_DIR" 2>/dev/null || true
    PARENT_DIR="$(dirname "$PARENT_DIR")"
done

# Fix service file permissions and simplify
echo -e "${BLUE}⚙️  Creating simplified service file...${NC}"
sudo tee /etc/systemd/system/oled-service.service > /dev/null << EOF
[Unit]
Description=OLED Display API Service
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
Group=$CURRENT_USER
WorkingDirectory=$CURRENT_DIR
ExecStart=$CURRENT_DIR/venv/bin/python3 $CURRENT_DIR/oled_api_service.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

# I2C and GPIO access
SupplementaryGroups=i2c gpio

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd
sudo systemctl daemon-reload

# Ensure user is in correct groups
echo -e "${BLUE}👥 Adding user to required groups...${NC}"
sudo usermod -a -G i2c,gpio $CURRENT_USER

echo -e "${GREEN}✅ Permissions fixed!${NC}"
echo
echo -e "${BLUE}📋 Test the service:${NC}"
echo "sudo systemctl start oled-service"
echo "sudo systemctl status oled-service"
echo "curl http://localhost:5001/api/health"
echo
echo -e "${YELLOW}⚠️  Note: You may need to log out and back in for group changes to take effect.${NC}"
echo "If the service still fails, try running it manually first:"
echo "cd $CURRENT_DIR && source venv/bin/activate && python3 oled_api_service.py"