# SMS GUI Application - User Guide

## Overview
The SMS Database Viewer is a PyQt5 application that provides a graphical interface to interact with your SMS database API.

## Features

### Connection Settings
- **Host Input**: Enter the IP address or hostname where your API is running
  - Default: `localhost` (loaded from .env file)
  - Examples: `localhost`, `192.168.1.100`, `myserver.local`
- **Port Input**: Enter the port number for your API
  - Default: `5000` (loaded from .env file)
  - Range: 1-65535
- **Save Settings Button**: Save current host and port to `.env` file for persistence
- **Preset Buttons**: Quick connection presets (auto-saves when used)
  - **Localhost**: Sets to `localhost:5000`
  - **192.168.1.x**: Helps set local network addresses

### Configuration Persistence
The application automatically saves and loads connection settings from a `.env` file:
- **Auto-load**: Settings are loaded on startup
- **Manual Save**: Click "Save Settings" or press Ctrl+S
- **Auto-save**: Preset buttons automatically save changes
- **File Location**: `.env` in the application directory

### Query Options
1. **Basic Queries**
   - Get All SMS: Retrieve all messages
   - Get Statistics: Database statistics

2. **Filter Queries**
   - Sender Filter: Find messages from specific phone number
   - Keyword Search: Search message content
   - Date Range: Filter by time period

3. **Custom Query**
   - Execute custom SQL queries
   - Support for parameterized queries

### Results Display
- **Table View**: Results displayed in sortable table
- **Export to CSV**: Save results to CSV file
- **Result Count**: Shows number of results

## Keyboard Shortcuts
- **Ctrl+R**: Refresh connection
- **F5**: Reload all SMS data
- **Ctrl+E**: Export current results to CSV
- **Ctrl+S**: Save current connection settings to .env file

## Connection Status
- **Green ✓**: API is connected and responsive
- **Red ✗**: API is offline or error occurred
- **Window Title**: Shows current connection status

## Usage Examples

### Connecting to Different Hosts
1. **Local Development**: `localhost:5000`
2. **Raspberry Pi on Network**: `192.168.1.100:5000`
3. **Remote Server**: `myserver.com:5000`

### Common Queries
1. **Recent Messages**: Use date range filter for last 24 hours
2. **Specific Sender**: Enter phone number in sender field
3. **Keyword Search**: Search for specific words in messages
4. **Custom Analysis**: Use custom SQL for complex queries

### Exporting Data
1. Run any query to populate results
2. Click "Export to CSV" or press Ctrl+E
3. Choose filename and location
4. File will include headers and all visible data

## Troubleshooting

### Connection Issues
- Verify API server is running
- Check host and port settings
- Ensure firewall allows connection
- Use "Update Connection" to retry

### No Data Displayed
- Check API health status
- Verify database has data
- Try "Get All SMS" first
- Check for error messages in status bar

### Performance Tips
- Use date ranges for large datasets
- Filter by sender for targeted results
- Export subsets rather than entire database
- Use custom queries for complex analysis

## Installation Requirements
```bash
pip install PyQt5 requests python-dotenv
```

## Configuration File
Create a `.env` file in the application directory to set default connection settings:
```env
SMS_GUI_HOST=localhost
SMS_GUI_PORT=5000
```

See `.env.example` for more configuration options.

## Running the Application
```bash
python3 SMS_GUI.py
```

Or use the launcher script:
```bash
./run_gui.sh
```
