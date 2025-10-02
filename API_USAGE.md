# SMS Database API Usage Guide

This API provides access to the SMS database with proper error handling and threading support.

## Base URL
```
http://localhost:5000/api
```

## Endpoints

### 1. Health Check
```bash
GET /api/health
```
Returns the health status of the API and database connection.

**Response:**
```json
{
  "status": "success",
  "message": "API and database are healthy",
  "timestamp": "2025-10-01T12:00:00"
}
```

### 2. Get All SMS Messages
```bash
GET /api/sms
```
Retrieves all SMS messages ordered by timestamp (newest first).

**Response:**
```json
{
  "status": "success",
  "data": [
    [1, "+1234567890", "2025-10-01 12:00:00", "Hello World"],
    [2, "+0987654321", "2025-10-01 11:00:00", "Test message"]
  ],
  "count": 2
}
```

### 3. Get SMS by Sender
```bash
GET /api/sms/sender/{phone_number}
```
Retrieves all SMS messages from a specific sender.

**Example:**
```bash
curl http://localhost:5000/api/sms/sender/+1234567890
```

### 4. Search SMS by Keyword
```bash
GET /api/sms/search?keyword={keyword}
```
Searches for SMS messages containing the specified keyword.

**Example:**
```bash
curl "http://localhost:5000/api/sms/search?keyword=hello"
```

### 5. Get SMS by Date Range
```bash
GET /api/sms/date-range?start={start_date}&end={end_date}
```
Retrieves SMS messages within a specified date range.

**Example:**
```bash
curl "http://localhost:5000/api/sms/date-range?start=2025-10-01%2000:00:00&end=2025-10-01%2023:59:59"
```

### 6. Get Database Statistics
```bash
GET /api/stats
```
Returns statistics about the SMS database.

**Response:**
```json
{
  "status": "success",
  "data": {
    "total_sms": 150,
    "unique_senders": 25,
    "latest_sms": "2025-10-01 12:00:00",
    "oldest_sms": "2025-09-01 10:30:00"
  }
}
```

### 7. Get Battery Status
```bash
GET /api/battery
```
Returns current battery voltage and charging status from SIM800L.

**Response:**
```json
{
  "status": "success",
  "data": {
    "voltage": 4.1,
    "voltage_mv": 4100,
    "charge_level": 85,
    "charge_status": "not_charging",
    "charge_status_code": 0,
    "timestamp": "2025-10-02T12:00:00",
    "low_battery_warnings": 0,
    "warning_threshold": 3.5,
    "shutdown_threshold": 3.3,
    "auto_shutdown_enabled": true
  }
}
```

### 8. Get Battery History
```bash
GET /api/battery/history
```
Returns battery-related system events from the SMS log.

**Response:**
```json
{
  "status": "success",
  "data": [
    [1, "SYSTEM", "2025-10-02 11:30:00", "Battery warning: 3.4V"],
    [2, "SYSTEM", "2025-10-02 11:00:00", "Battery monitoring started"]
  ],
  "count": 2
}
```

### 9. Manual System Shutdown
```bash
POST /api/system/shutdown
Content-Type: application/json
```
Manually trigger system shutdown (use with caution).

**Request Body:**
```json
{
  "force": false
}
```

**Response:**
```json
{
  "status": "success",
  "message": "System shutdown initiated"
}
```

### 10. Execute Custom Query
```bash
POST /api/query
Content-Type: application/json
```
Executes a custom SQL query on the database.

**Request Body:**
```json
{
  "query": "SELECT * FROM sms WHERE sender LIKE ?",
  "params": ["+123%"]
}
```

**Response:**
```json
{
  "status": "success",
  "data": [
    [1, "+1234567890", "2025-10-01 12:00:00", "Hello World"]
  ],
  "row_count": 1
}
```

## Error Handling

All endpoints return consistent error responses:

```json
{
  "status": "error",
  "message": "Human-readable error message",
  "error": "Technical error details"
}
```

Common HTTP status codes:
- `200`: Success
- `400`: Bad Request (missing parameters, invalid input)
- `500`: Internal Server Error (database issues, unexpected errors)

## Usage Examples

### Python Example
```python
import requests

# Get all SMS
response = requests.get('http://localhost:5000/api/sms')
data = response.json()

if data['status'] == 'success':
    print(f"Found {data['count']} SMS messages")
    for sms in data['data']:
        print(f"From: {sms[1]}, Time: {sms[2]}, Text: {sms[3]}")
else:
    print(f"Error: {data['message']}")

# Check battery status
battery_response = requests.get('http://localhost:5000/api/battery')
battery_data = battery_response.json()

if battery_data['status'] == 'success':
    info = battery_data['data']
    print(f"Battery: {info['voltage']:.2f}V ({info['charge_level']}%)")
    print(f"Status: {info['charge_status']}")
    if info['voltage'] <= info['warning_threshold']:
        print("WARNING: Low battery!")
else:
    print(f"Battery Error: {battery_data['message']}")

# Execute custom query
query_data = {
    "query": "SELECT COUNT(*) FROM sms WHERE sender = ?",
    "params": ["+1234567890"]
}
response = requests.post('http://localhost:5000/api/query', json=query_data)
result = response.json()
print(f"SMS count: {result['data'][0][0]}")
```

### curl Examples
```bash
# Health check
curl http://localhost:5000/api/health

# Get all SMS
curl http://localhost:5000/api/sms

# Search for messages containing "test"
curl "http://localhost:5000/api/sms/search?keyword=test"

# Get battery status
curl http://localhost:5000/api/battery

# Get battery history
curl http://localhost:5000/api/battery/history

# Get statistics
curl http://localhost:5000/api/stats

# Custom query
curl -X POST http://localhost:5000/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "SELECT * FROM sms LIMIT 5"}'

# Manual shutdown (use with extreme caution!)
curl -X POST http://localhost:5000/api/system/shutdown \
  -H "Content-Type: application/json" \
  -d '{"force": false}'
```

## Security Notes

- The API accepts any SQL query via the `/api/query` endpoint. In production, implement proper authentication and query validation.
- Consider adding rate limiting for production use.
- The API runs on all interfaces (0.0.0.0). Restrict access as needed for your environment.
- **CRITICAL**: The `/api/system/shutdown` endpoint can shutdown your system. Use with extreme caution and consider disabling in production.

## Battery Monitoring Features

The system includes automatic battery monitoring with the following features:

### Automatic Monitoring
- **Continuous Monitoring**: Checks battery voltage every 60 seconds (configurable)
- **Warning System**: Alerts when battery drops below 3.5V
- **Critical Shutdown**: Automatically shuts down Linux system when battery reaches 3.3V
- **Event Logging**: All battery events are logged to the SMS database

### Safety Features
- **Configurable Thresholds**: Easily adjust warning and shutdown voltage levels
- **Auto-shutdown Toggle**: Can be disabled for testing/development
- **Manual Override**: API endpoint for manual shutdown when needed
- **Event History**: Track battery warnings and critical events over time

### Configuration
Edit the configuration variables in `sim800l_hat_db_api.py`:
```python
BATTERY_CHECK_INTERVAL = 60      # Check every 60 seconds
LOW_BATTERY_THRESHOLD = 3.3      # Shutdown threshold
BATTERY_WARNING_THRESHOLD = 3.5  # Warning threshold
ENABLE_AUTO_SHUTDOWN = True      # Enable/disable auto shutdown
```

### Battery Status Codes
- **0 (not_charging)**: Battery is not being charged
- **1 (charging)**: Battery is currently charging
- **2 (charging_finished)**: Battery charging is complete

### Emergency Procedures
If auto-shutdown is disabled and battery is critical:
1. Check battery status via API: `GET /api/battery`
2. Save any important data
3. Manually shutdown via API: `POST /api/system/shutdown` with `"force": true`
4. Or use system command: `sudo shutdown -h now`
