#!/bin/bash

# SIM800L pigpio Setup Script for Raspberry Pi Zero W
# This script installs and configures pigpio for SIM800L communication

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}SIM800L pigpio Setup${NC}"
echo "==================="

# Check if running on Pi
if ! grep -q "Raspberry Pi" /proc/device-tree/model 2>/dev/null; then
    echo -e "${RED}Warning: This script is designed for Raspberry Pi${NC}"
fi

# Update system
echo -e "${YELLOW}Updating system packages...${NC}"
sudo apt update

# Install pigpio
echo -e "${YELLOW}Installing pigpio...${NC}"
sudo apt install -y pigpio python3-pigpio

# Install Python pigpio library
echo -e "${YELLOW}Installing Python pigpio library...${NC}"
pip3 install pigpio

# Enable and start pigpiod service
echo -e "${YELLOW}Enabling pigpiod service...${NC}"
sudo systemctl enable pigpiod
sudo systemctl start pigpiod

# Check if pigpiod is running
if pgrep -x "pigpiod" > /dev/null; then
    echo -e "${GREEN}✓ pigpiod service is running${NC}"
else
    echo -e "${RED}✗ pigpiod service failed to start${NC}"
    exit 1
fi

# Test pigpio connection
echo -e "${YELLOW}Testing pigpio connection...${NC}"
python3 -c "
import pigpio
pi = pigpio.pi()
if pi.connected:
    print('✓ pigpio connection successful')
    pi.stop()
else:
    print('✗ pigpio connection failed')
    exit(1)
"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ pigpio setup completed successfully!${NC}"
    echo ""
    echo "Hardware connection for SIM800L:"
    echo "  SIM800L TX -> Pi GPIO 13 (Pin 33)"
    echo "  SIM800L RX -> Pi GPIO 12 (Pin 32)"
    echo "  SIM800L VCC -> Pi 5V (Pin 2 or 4)"
    echo "  SIM800L GND -> Pi GND (Pin 6, 9, 14, 20, 25, 30, 34, or 39)"
    echo ""
    echo "Ready to test SMS functionality with:"
    echo "  ./test_sms.sh"
else
    echo -e "${RED}✗ pigpio setup failed${NC}"
    exit 1
fi