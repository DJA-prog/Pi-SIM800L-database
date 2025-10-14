# OLED Display Integration for SIM800L System

## Overview
This document describes the OLED display integration for the SIM800L SMS capture system. The display shows real-time system status including WiFi IP address, SMS count, and system message count.

## Hardware Specifications
- **Display**: SSD1306 OLED 128x32 pixels
- **Size**: 0.96 inch (24mm)
- **Interface**: I²C (SCL, SDA)
- **I²C Address**: 0x3c (default) or 0x3d
- **Voltage**: 3.3V - 5V
- **Temperature**: -30°C to 80°C

## Wiring Connections
```
SSD1306 OLED    ->    Raspberry Pi
VCC             ->    3.3V (Pin 1) or 5V (Pin 2)
GND             ->    Ground (Pin 6)
SCL             ->    GPIO 3 (Pin 5) - I2C Clock
SDA             ->    GPIO 2 (Pin 3) - I2C Data
```

## Installation

### 1. Run Setup Script
```bash
sudo ./setup_oled.sh
```

### 2. Manual Installation
```bash
# Enable I2C
sudo raspi-config nonint do_i2c 0

# Install dependencies
sudo apt-get update
sudo apt-get install -y python3-pip i2c-tools
pip3 install luma.oled pillow

# Scan for I2C devices
i2cdetect -y 1
```

## Configuration

### Environment Variables (.env.server)
```bash
# OLED Display Configuration
ENABLE_OLED=true
OLED_I2C_ADDRESS=0x3c
```

### Configuration Options
- `ENABLE_OLED`: Enable/disable OLED display (true/false)
- `OLED_I2C_ADDRESS`: I2C address of display (0x3c or 0x3d)

## Display Content

### Main Display
- **Line 1**: "SIM800L Status"
- **Line 2**: WiFi IP address (e.g., "IP: 192.168.1.100")
- **Line 3**: Message counts (e.g., "SMS:45 SYS:12")

### Startup Display
- Shows "SIM800L System Starting..." with timestamp
- Displayed for 2 seconds during initialization

### Error Display
- Shows error messages when system issues occur
- Includes timestamp for debugging

### Special Status Messages
- **Battery Warning**: Shows low battery voltage
- **Connection Status**: Shows SIM800L connection state
- **System Errors**: Shows critical system errors

## API Integration

The OLED display automatically integrates with the SIM800L API server:
- Updates every 5 seconds
- Reads message counts from database
- Shows current WiFi IP address
- Displays system status

## Files

### Core Files
- `oled_display.py`: Main OLED display module
- `setup_oled.sh`: Installation script
- `OLED_DISPLAY.md`: This documentation

### Modified Files
- `sim800l_hat_db_api_batt.py`: Added OLED integration
- `.env.server`: Added OLED configuration
- `requirements_server.txt`: Added OLED dependencies

## Testing

### Test OLED Display
```bash
python3 oled_display.py
```

### Check I2C Connection
```bash
i2cdetect -y 1
```
Look for address 60 (0x3c) or 61 (0x3d)

### Verify Integration
```bash
python3 sim800l_hat_db_api_batt.py
```
Check console output for OLED status messages.

## Troubleshooting

### Display Not Working
1. Check I2C is enabled: `ls /dev/i2c*`
2. Scan for devices: `i2cdetect -y 1`
3. Verify wiring connections
4. Try different I2C address (0x3d instead of 0x3c)

### Permission Errors
```bash
sudo usermod -a -G i2c $USER
# Logout and login again
```

### Python Import Errors
```bash
pip3 install --upgrade luma.oled pillow
```

### I2C Address Issues
Edit `.env.server`:
```bash
OLED_I2C_ADDRESS=0x3d  # Try alternate address
```

## Features

### Automatic Updates
- Message counts update every 5 seconds
- WiFi IP address refreshed regularly
- Database statistics tracked in real-time

### Thread Safety
- Display updates in separate thread
- Non-blocking integration with main system
- Graceful shutdown handling

### Error Handling
- Fallback when display unavailable
- Graceful degradation if I2C fails
- Detailed error logging

### Power Management
- Low power consumption
- Automatic display management
- Battery status integration

## Performance
- Update interval: 5 seconds
- I2C speed: Standard (100kHz)
- Memory usage: Minimal (~1MB)
- CPU impact: Very low (<1%)

## Compatibility
- Raspberry Pi Zero/3/4
- Python 3.7+
- SSD1306 OLED displays
- I2C interface required