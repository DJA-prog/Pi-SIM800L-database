# SMS GUI Battery Monitoring Features

## New Features Added

### 1. Battery Monitoring Panel
- **Battery Status Display**: Real-time voltage, status, and timestamp
- **Visual Indicators**: Color-coded status with battery icons
  - 🔋 Green: Voltage ≥ 4.0V (Good)
  - 🔋 Orange: Voltage ≥ 3.7V (Moderate)
  - 🪫 Red: Voltage ≥ 3.3V (Low)
  - ⚠️ Dark Red: Voltage < 3.3V (Critical)

### 2. Battery Actions
- **Get Battery**: Fetch current battery status
- **Debug**: Get detailed debug information including:
  - AT command testing results
  - Raw SIM800L responses
  - Alternative command outputs
  - System configuration

### 3. Auto-Refresh Feature
- **Configurable Timer**: Set refresh interval (minimum 5 seconds)
- **Start/Stop Control**: Toggle automatic battery monitoring
- **Status Updates**: Real-time battery status updates in GUI

### 4. System Control
- **Emergency Shutdown**: Remote system shutdown with double confirmation
- **Safety Warnings**: Multiple confirmation dialogs to prevent accidental shutdown

## New API Endpoints Supported

### Battery Monitoring
- `GET /api/battery` - Get current battery status
- `GET /api/battery/debug` - Get detailed debug information

### System Control
- `POST /api/system/shutdown` - Initiate system shutdown

## Keyboard Shortcuts

- **Ctrl+B**: Get battery status
- **Ctrl+Shift+B**: Get battery debug information
- **Ctrl+R**: Refresh/reconnect to API
- **F5**: Get all SMS messages
- **Ctrl+E**: Export data to CSV
- **Ctrl+S**: Save connection settings

## Battery Status Information

The battery display shows:
- **Voltage**: Current battery voltage in volts (3 decimal precision)
- **Level**: Battery charge level percentage (1-100%)
- **Timestamp**: When the reading was taken
- **Warnings**: Count of low battery warnings (if any)
- **Thresholds**: Warning and shutdown voltage levels

Note: Charging status is not displayed as the SIM800L doesn't provide reliable charging status information.

## Debug Information

The debug feature provides:
- **AT Command Tests**: Results of basic AT commands
- **AT+CBC Response**: Raw battery command output
- **Alternative Commands**: Tests AT+CPAS, AT+CSQ, AT+CREG?
- **System Configuration**: Current monitoring settings
- **Error Details**: Detailed error information for troubleshooting

## Safety Features

1. **Double Confirmation**: System shutdown requires two confirmations
2. **Warning Messages**: Clear warnings about consequences
3. **Auto-refresh Limits**: Minimum 5-second refresh interval
4. **Connection Validation**: Checks API health before operations
5. **Error Handling**: Graceful handling of connection failures

## Usage Tips

1. **Start with Debug**: If battery reading fails, use the debug feature to diagnose
2. **Monitor Trends**: Use auto-refresh to monitor battery voltage trends
3. **Save Settings**: Use Ctrl+S to save your preferred host/port settings
4. **Emergency Use**: The shutdown feature is for emergency situations only
5. **Check Connections**: Green API status indicates proper connection

## Configuration

The GUI uses the same `.env` file format:
```
SMS_GUI_HOST=localhost
SMS_GUI_PORT=5000
```

Battery monitoring respects the server-side configuration for:
- Warning thresholds
- Shutdown thresholds  
- Auto-shutdown settings
- Check intervals
