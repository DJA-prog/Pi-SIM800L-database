# SMS System API Updates - New Features

## 🔋 Battery Monitoring Changes
- **Interval Changed**: Battery monitoring now runs every 5 minutes (300 seconds) instead of 1 minute
- **New Endpoint**: `POST /api/battery/set_interval` - Dynamically change monitoring interval (30-3600 seconds)

## 📱 SIM800 Management
- **Restart Module**: `POST /api/sim/restart` - Restart the SIM800 module via AT+CFUN=1,1 command
- **Change PIN**: `POST /api/sim/set_pin` - Set a new 4-digit SIM card PIN

## 🖥️ System Control
- **Reboot Host**: `POST /api/system/reboot` - Reboot the Linux host system
- **Enhanced Shutdown**: `POST /api/system/shutdown` - Improved with confirmation requirement

## 📊 System Messages
- **Separate Table**: System messages now stored in dedicated `system_messages` table
- **API Access**: `GET /api/system/messages` - Retrieve recent system log messages
- **Automatic Logging**: All system operations are logged automatically

## 🎛️ GUI Enhancements
- **SIM Controls**: New buttons for SIM800 restart and PIN change
- **System Controls**: Reboot and shutdown buttons with confirmations
- **System Messages**: View system logs directly in GUI
- **Better Feedback**: Enhanced status messages and confirmations

## 📡 API Endpoints Summary

### Battery Management
```http
GET /api/battery                    # Get current battery status
POST /api/battery/set_interval      # Change monitoring interval
```

### SIM800 Management
```http
POST /api/sim/restart               # Restart SIM800 module
POST /api/sim/set_pin               # Change SIM PIN
```

### System Control
```http
POST /api/system/reboot             # Reboot host system
POST /api/system/shutdown           # Shutdown host system
GET /api/system/messages            # Get system messages
```

## 🔒 Security Features
- **Confirmation Required**: All destructive operations require explicit confirmation
- **Parameter Validation**: PIN must be 4-digit numeric, intervals have safe ranges
- **Detailed Logging**: All system operations logged with timestamps and reasons

## 📋 Usage Examples

### Change Battery Monitoring to 10 minutes:
```json
POST /api/battery/set_interval
{
  "interval": 600
}
```

### Restart SIM800:
```json
POST /api/sim/restart
{
  "confirm": true
}
```

### Change SIM PIN:
```json
POST /api/sim/set_pin
{
  "pin": "9876"
}
```

### Reboot System:
```json
POST /api/system/reboot
{
  "confirm": true,
  "reason": "Scheduled maintenance reboot"
}
```

## ⚠️ Important Notes
- All system control operations require `confirm: true` in request body
- SIM PIN must be exactly 4 digits
- Battery interval must be between 30-3600 seconds
- System messages are automatically logged for all operations
- GUI provides confirmation dialogs for all destructive operations

## 🔄 Migration Notes
- Existing SMS data remains unchanged
- New `system_messages` table is created automatically
- Battery monitoring continues with new 5-minute interval
- All existing API endpoints remain functional
