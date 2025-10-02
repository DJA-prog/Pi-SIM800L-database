# SMS Database API Server Configuration

## Environment Variables

The server now uses a `.env.server` file for configuration. Copy and modify this file to customize your setup.

### GPIO Configuration
```env
# GPIO pins for SIM800L communication
RX_PIN=13                    # GPIO pin for SIM800L TX -> Pi RX
TX_PIN=12                    # GPIO pin for SIM800L RX <- Pi TX
BAUDRATE=9600               # UART communication speed
```

### SIM Card Configuration
```env
# SIM card settings
SIM_PIN=9438                # Your SIM card PIN (4 digits)
```

### Database Configuration
```env
# Database file location
DB_FILE=sms_messages.db     # SQLite database filename/path
```

### Battery Monitoring Configuration
```env
# Battery monitoring settings
BATTERY_CHECK_INTERVAL=300           # Check interval in seconds (300 = 5 minutes)
LOW_BATTERY_THRESHOLD=3.3           # Voltage threshold for shutdown (volts)
BATTERY_WARNING_THRESHOLD=3.5       # Voltage threshold for warnings (volts)
ENABLE_AUTO_SHUTDOWN=true           # Enable automatic shutdown on low battery
```

### API Server Configuration
```env
# API server settings
API_HOST=0.0.0.0            # Server bind address (0.0.0.0 = all interfaces)
API_PORT=5000               # Server port
API_DEBUG=false             # Enable Flask debug mode (true/false)
```

## Configuration Values

### GPIO Pins
- **RX_PIN**: GPIO pin number where SIM800L TX is connected
- **TX_PIN**: GPIO pin number where SIM800L RX is connected
- **BAUDRATE**: UART communication speed (typically 9600 for SIM800L)

### Battery Thresholds
- **BATTERY_CHECK_INTERVAL**: How often to check battery (30-3600 seconds)
- **LOW_BATTERY_THRESHOLD**: Voltage below which system shuts down (volts)
- **BATTERY_WARNING_THRESHOLD**: Voltage below which warnings are logged (volts)
- **ENABLE_AUTO_SHUTDOWN**: Whether to automatically shutdown on low battery

### API Server
- **API_HOST**: `0.0.0.0` for all interfaces, `127.0.0.1` for localhost only
- **API_PORT**: Port number for the API server (default: 5000)
- **API_DEBUG**: Flask debug mode (only enable for development)

## Security Considerations

### SIM PIN
- Store your actual 4-digit SIM PIN in the `SIM_PIN` variable
- The PIN is masked in logs and API responses for security
- Change the PIN regularly for better security

### API Access
- Set `API_HOST=127.0.0.1` to restrict access to localhost only
- Use a firewall to control external access
- Consider using HTTPS in production (requires additional setup)

### File Permissions
```bash
# Secure the .env.server file
chmod 600 .env.server
chown your_user:your_group .env.server
```

## Example Configuration Files

### Development (.env.server)
```env
RX_PIN=13
TX_PIN=12
BAUDRATE=9600
SIM_PIN=1234
DB_FILE=sms_messages.db
BATTERY_CHECK_INTERVAL=60
LOW_BATTERY_THRESHOLD=3.3
BATTERY_WARNING_THRESHOLD=3.5
ENABLE_AUTO_SHUTDOWN=false
API_HOST=127.0.0.1
API_PORT=5000
API_DEBUG=true
```

### Production (.env.server)
```env
RX_PIN=13
TX_PIN=12
BAUDRATE=9600
SIM_PIN=9876
DB_FILE=/var/lib/sms/sms_messages.db
BATTERY_CHECK_INTERVAL=300
LOW_BATTERY_THRESHOLD=3.3
BATTERY_WARNING_THRESHOLD=3.5
ENABLE_AUTO_SHUTDOWN=true
API_HOST=0.0.0.0
API_PORT=5000
API_DEBUG=false
```

## Configuration API

### Get Current Configuration
```http
GET /api/config
```

Returns the current system configuration (SIM PIN is masked for security).

### Update Battery Interval
```http
POST /api/battery/set_interval
Content-Type: application/json

{
  "interval": 300
}
```

## Startup Process

1. Server loads `.env.server` file
2. Configuration is validated and applied
3. System configuration is displayed in console
4. GPIO pins are initialized
5. Database is created/verified
6. API server starts
7. Battery monitoring starts
8. SIM800L initialization begins
9. SMS capture starts

## Troubleshooting

### Configuration Issues
- Ensure `.env.server` file exists in the same directory as the script
- Check file permissions (should be readable by the user running the script)
- Verify all numeric values are valid (no quotes around numbers)
- Boolean values should be `true` or `false` (lowercase)

### GPIO Issues
- Verify GPIO pin numbers match your hardware setup
- Ensure pins are not in use by other processes
- Check that pigpio daemon is running: `sudo systemctl start pigpiod`

### API Issues
- Verify port is not in use by another service
- Check firewall settings if accessing remotely
- Ensure sufficient permissions for the user running the script
