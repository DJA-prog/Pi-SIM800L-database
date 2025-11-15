# OLED Display API Service

A lightweight, standalone API service for controlling SSD1306 OLED displays on Raspberry Pi Zero W. This service provides REST API endpoints to update display content, manage display modes, and monitor service status.

## Features

- 🖥️ **SSD1306 OLED Display Support** - 128x32 pixel display control
- 🌐 **REST API Interface** - Easy integration with other services
- ⚡ **Pi Zero W Optimized** - Low resource usage and efficient operation
- 🔄 **Auto-Update Mode** - Automatic display refresh with configurable intervals
- 📊 **Multiple Display Modes** - Custom data, date/time, startup message, or off
- 🔒 **Systemd Integration** - Proper service management with auto-restart
- 📝 **Comprehensive Logging** - Detailed logging with configurable levels
- 🛠️ **Easy Installation** - Automated setup script for Pi Zero W

## Hardware Requirements

- Raspberry Pi Zero W (or any Pi with GPIO)
- SSD1306 OLED Display (128x32, I2C interface)
- I2C connection:
  - VCC → 3.3V
  - GND → Ground
  - SDA → GPIO 2 (Pin 3)
  - SCL → GPIO 3 (Pin 5)

## Quick Start

### 1. Installation

```bash
# Copy the oled_service directory to your Pi Zero W
scp -r oled_service/ pi@your-pi-ip:/home/pi/

# SSH to your Pi Zero W
ssh pi@your-pi-ip

# Navigate to service directory
cd /home/pi/oled_service

# Run installation script
./install_oled_service.sh
```

### 2. Configuration

Edit the configuration file:
```bash
nano .env.oled
```

### 3. Start the Service

```bash
# Enable for auto-start
sudo systemctl enable oled-service

# Start the service
sudo systemctl start oled-service

# Check status
./oled_service.sh status
```

## API Endpoints

### Health Check
```bash
GET /api/health
```
Returns service health and uptime information.

### Service Status
```bash
GET /api/status
```
Returns detailed service status, configuration, and current display data.

### Update Display Data
```bash
POST /api/display/update
Content-Type: application/json

{
  "wifi_ip": "192.168.1.100",
  "battery_percent": 85,
  "message_count": 3
}
```

### Set Display Mode
```bash
POST /api/display/mode
Content-Type: application/json

{
  "mode": "custom"  // Options: custom, datetime, startup, off
}
```

### Clear Display
```bash
POST /api/display/clear
```

### Display Custom Text
```bash
POST /api/display/text
Content-Type: application/json

{
  "lines": ["Line 1", "Line 2", "Line 3"]
}
```

### Get Configuration
```bash
GET /api/config
```

## Service Management

Use the included management script:

```bash
# Start service
./oled_service.sh start

# Stop service
./oled_service.sh stop

# Restart service
./oled_service.sh restart

# Check status
./oled_service.sh status

# View logs
./oled_service.sh logs

# Follow logs in real-time
./oled_service.sh logs -f

# Run API tests
./oled_service.sh test

# Edit configuration
./oled_service.sh config
```

## Configuration Options

| Variable | Default | Description |
|----------|---------|-------------|
| `OLED_API_HOST` | `0.0.0.0` | API server bind address |
| `OLED_API_PORT` | `5001` | API server port |
| `OLED_API_DEBUG` | `false` | Enable Flask debug mode |
| `OLED_I2C_ADDRESS` | `0x3c` | I2C address of OLED display |
| `OLED_AUTO_UPDATE_INTERVAL` | `5` | Auto-update interval (seconds) |
| `OLED_LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |

## Display Modes

- **custom**: Shows WiFi IP, battery percentage, and message count
- **datetime**: Shows current date and time
- **startup**: Shows startup message with current time
- **off**: Clears the display

## Integration Examples

### Update from Shell Script
```bash
#!/bin/bash
WIFI_IP=$(hostname -I | awk '{print $1}')
BATTERY=$(cat /sys/class/power_supply/BAT0/capacity 2>/dev/null || echo "0")
MSG_COUNT=5

curl -X POST http://localhost:5001/api/display/update \
  -H "Content-Type: application/json" \
  -d "{\"wifi_ip\":\"$WIFI_IP\",\"battery_percent\":$BATTERY,\"message_count\":$MSG_COUNT}"
```

### Update from Python
```python
import requests

def update_oled_display(wifi_ip, battery_percent, message_count):
    data = {
        "wifi_ip": wifi_ip,
        "battery_percent": battery_percent,
        "message_count": message_count
    }
    response = requests.post("http://localhost:5001/api/display/update", json=data)
    return response.json()
```

### Cron Job for Regular Updates
```bash
# Add to crontab (crontab -e)
*/5 * * * * /home/pi/update_display.sh
```

## Troubleshooting

### Service Won't Start
```bash
# Check service status
sudo systemctl status oled-service

# Check logs
sudo journalctl -u oled-service -f

# Verify I2C is enabled
sudo raspi-config nonint get_i2c

# Test I2C devices
i2cdetect -y 1
```

### Display Not Working
```bash
# Check I2C connection
i2cdetect -y 1  # Should show device at 0x3c

# Check logs for errors
tail -f /var/log/oled-service.log

# Test with different I2C address
# Edit .env.oled and change OLED_I2C_ADDRESS to 0x3d
```

### API Not Responding
```bash
# Check if service is running
./oled_service.sh status

# Check port is not in use
sudo netstat -tulpn | grep 5001

# Test API manually
curl http://localhost:5001/api/health
```

## Performance

The service is optimized for Pi Zero W with:
- Memory limit: 128MB
- CPU quota: 25%
- Efficient update cycles
- Minimal dependencies

## Security

- Service runs as `pi` user (not root)
- Limited file system access
- No new privileges allowed
- Private temp directory

## Files Structure

```
oled_service/
├── oled_api_service.py       # Main service application
├── oled_display.py           # OLED display library
├── oled-service.service      # Systemd service file
├── install_oled_service.sh   # Installation script
├── oled_service.sh           # Service management script
├── requirements.txt          # Python dependencies
├── .env.oled.template        # Configuration template
├── .env.oled                 # Configuration file
└── README.md                 # This file
```

## License

This project is provided as-is for educational and personal use.