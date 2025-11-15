#!/bin/bash

# SIM800L SMS Test Runner for Pi Zero W
# This script helps run SMS tests with proper configuration

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}SIM800L SMS Test Runner${NC}"
echo "=========================="

# Check if running on Pi
if ! grep -q "Raspberry Pi" /proc/device-tree/model 2>/dev/null; then
    echo -e "${RED}Warning: Not running on Raspberry Pi${NC}"
    echo "This script is designed for Raspberry Pi Zero W"
fi

# Load configuration if available
if [ -f "sms_config.env" ]; then
    echo -e "${GREEN}Loading configuration from sms_config.env...${NC}"
    set -a
    source sms_config.env
    set +a
else
    echo -e "${YELLOW}No sms_config.env found, using default values${NC}"
fi

# Check required dependencies
echo "Checking dependencies..."

# Check if pigpio daemon is running
if ! pgrep -x "pigpiod" > /dev/null; then
    echo -e "${YELLOW}Starting pigpio daemon...${NC}"
    sudo systemctl start pigpiod
    sleep 2
    
    if ! pgrep -x "pigpiod" > /dev/null; then
        echo -e "${RED}Failed to start pigpiod. Installing pigpio...${NC}"
        sudo apt update && sudo apt install -y pigpio python3-pigpio
        sudo systemctl enable pigpiod
        sudo systemctl start pigpiod
    fi
else
    echo -e "${GREEN}pigpiod is running${NC}"
fi

# Check if pigpio Python library is installed
python3 -c "import pigpio" 2>/dev/null
if [ $? -ne 0 ]; then
    echo -e "${RED}pigpio Python library not found. Installing...${NC}"
    pip3 install pigpio
fi

echo ""
echo -e "${GREEN}Running SMS test suite...${NC}"
echo "=========================="

# Run the test
python3 send_sms.py

echo ""
echo -e "${YELLOW}Test completed. Check logs at /tmp/sms_test.log${NC}"
echo ""
echo "Usage examples:"
echo "  ./test_sms.sh                                    # Run full test suite"
echo "  python3 send_sms.py                             # Run full test suite"
echo "  python3 send_sms.py '+1234567890' 'Hello!'      # Send custom SMS"
echo ""
echo "Configuration:"
echo "  Edit sms_config.env to change settings"
echo "  Current TEST_PHONE_NUMBER: ${TEST_PHONE_NUMBER:-'Not set'}"
echo "  Current SIM_PIN: ${SIM_PIN:-'Not set'}"
echo ""
echo "Hardware setup:"
echo "  SIM800L TX -> Pi GPIO ${RX_PIN:-13} (Pin 33)"
echo "  SIM800L RX -> Pi GPIO ${TX_PIN:-12} (Pin 32)"
echo "  Power: SIM800L VCC -> Pi 5V, GND -> Pi GND"