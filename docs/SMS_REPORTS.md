# SMS Report Feature Documentation

## Overview
The SMS Report feature automatically sends system status reports to a configured phone number at regular intervals. This allows you to monitor your SIM800L system remotely without needing to access the API or GUI.

## Configuration

### Environment Variables
Add these to your `.env.server` file:

```bash
# Enable/disable SMS reports
ENABLE_SMS_REPORTS=true

# Phone number to receive reports (include country code)
SMS_REPORT_RECIPIENT=+1234567890

# Report interval in seconds (default: 604800 = 1 week)
SMS_REPORT_INTERVAL=604800

# Last report timestamp (auto-managed)
SMS_REPORT_LAST_SENT=0
```

### Common Intervals
- 1 hour: `3600`
- 6 hours: `21600`
- 12 hours: `43200`
- 1 day: `86400`
- 1 week: `604800` (default)
- 2 weeks: `1209600`
- 1 month: `2419200`

## Report Content
Each status report includes:

- **Timestamp**: When the report was generated
- **SMS Statistics**: Total SMS count and unique senders
- **Battery Status**: Voltage and percentage
- **Disk Usage**: Used/total space and percentage
- **Signal Strength**: Quality and RSSI value
- **System Messages**: Count of system log entries

### Example Report
```
SIM800L System Report
2025-10-30 14:30:15

SMS Stats:
- Total: 147
- Senders: 8

System:
- Battery: 4.12V (87%)
- Disk: 2.1G/14G (18% used)
- Signal: Good (18)
- Sys Messages: 23

System operational.
```

## API Endpoints

### Get Configuration
```http
GET /api/sms-reports/config
```

Returns current SMS report settings including next report time.

### Update Configuration
```http
POST /api/sms-reports/config
Content-Type: application/json

{
  "enabled": true,
  "recipient": "+1234567890",
  "interval_hours": 24
}
```

Updates report settings. You can specify interval in hours or seconds.

### Send Report Now
```http
POST /api/sms-reports/send-now
Content-Type: application/json

{
  "recipient": "+1234567890"  // Optional: override default recipient
}
```

Sends a status report immediately.

### Test SMS
```http
POST /api/sms-reports/test-sms
Content-Type: application/json

{
  "recipient": "+1234567890",
  "message": "Test message"
}
```

Sends a test SMS to verify SMS functionality.

### Preview Report
```http
GET /api/sms-reports/preview
```

Generates and returns a status report without sending it.

## GUI Configuration
The SMS report feature can be configured through the web GUI:

1. Access the web interface at `http://your-pi-ip:5000`
2. Navigate to the SMS Reports section
3. Configure recipient, interval, and enable/disable reports
4. Test SMS functionality
5. Send reports manually
6. Preview report content

## Troubleshooting

### Reports Not Sending
1. Check SMS_REPORT_RECIPIENT is set correctly
2. Verify ENABLE_SMS_REPORTS=true
3. Check system logs for SMS send errors
4. Test SMS functionality with test endpoint
5. Verify SIM800L module is responding

### Wrong Interval
- Minimum interval is 15 minutes (900 seconds)
- Use `/api/sms-reports/config` to check current settings
- Update interval via API or environment file

### SMS Send Failures
- Check SIM card balance and SMS capability
- Verify phone number format (include country code)
- Check SIM800L signal strength
- Review system logs for error messages

## Security Notes
- Reports contain system information - use secure phone numbers
- Phone numbers are logged in system messages
- Consider disabling reports if not needed
- Reports count against SMS allowance/costs

## Log Messages
The system logs SMS report activities:
- Report sending attempts
- Configuration changes
- Send failures and successes
- Manual report requests

Check `/api/system/logs?filter=report` for SMS report related logs.