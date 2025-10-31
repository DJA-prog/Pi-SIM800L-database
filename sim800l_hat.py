#!/usr/bin/env python3
import time
import re
import sqlite3
import datetime
import pigpio
import threading
import queue
import subprocess
import os
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# Import OLED display module
try:
    from oled_display import OLEDDisplay
    OLED_AVAILABLE = True
except ImportError:
    print("⚠️ OLED display module not available - install requirements: pip install luma.oled")
    OLED_AVAILABLE = False

# Load environment variables from .env.server file
load_dotenv('.env.server')

# ---------------- CONFIG ----------------
RX_PIN = int(os.getenv('RX_PIN', 13))   # GPIO for SIM800L TX -> Pi RX
TX_PIN = int(os.getenv('TX_PIN', 12))   # GPIO for SIM800L RX <- Pi TX
BAUDRATE = int(os.getenv('BAUDRATE', 9600))
SIM_PIN = os.getenv('SIM_PIN', '9438')
DB_FILE = os.getenv('DB_FILE', 'sms_messages.db')

# Battery monitoring config
BATTERY_CHECK_INTERVAL = int(os.getenv('BATTERY_CHECK_INTERVAL', 300))  # Check battery every 5 minutes
LOW_BATTERY_THRESHOLD = float(os.getenv('LOW_BATTERY_THRESHOLD', 3.3))  # Shutdown threshold in volts
BATTERY_WARNING_THRESHOLD = float(os.getenv('BATTERY_WARNING_THRESHOLD', 3.5))  # Warning threshold in volts
ENABLE_AUTO_SHUTDOWN = os.getenv('ENABLE_AUTO_SHUTDOWN', 'true').lower() == 'true'  # Auto shutdown setting

# API Server config
API_HOST = os.getenv('API_HOST', '0.0.0.0')
API_PORT = int(os.getenv('API_PORT', 5000))
API_DEBUG = os.getenv('API_DEBUG', 'false').lower() == 'true'

# OLED Display config
ENABLE_OLED = os.getenv('ENABLE_OLED', 'true').lower() == 'true'
OLED_I2C_ADDRESS = int(os.getenv('OLED_I2C_ADDRESS', '0x3c'), 16)  # Default I2C address

# SMS Report config
ENABLE_SMS_REPORTS = os.getenv('ENABLE_SMS_REPORTS', 'true').lower() == 'true'
SMS_REPORT_RECIPIENT = os.getenv('SMS_REPORT_RECIPIENT', '')  # Phone number for reports
SMS_REPORT_INTERVAL = int(os.getenv('SMS_REPORT_INTERVAL', 604800))  # Weekly reports (7 days)
SMS_REPORT_LAST_SENT = float(os.getenv('SMS_REPORT_LAST_SENT', 0))  # Last report timestamp
# -----------------------------------------

# Global variables for battery monitoring
last_battery_voltage = 0.0
battery_status = "unknown"
low_battery_warnings = 0
battery_voltage_history = []  # Track voltage changes for charging detection

# OLED Display instance
oled_display = None

# UART access lock for thread safety
uart_lock = threading.Lock()

# Queue for database queries
db_queue = queue.Queue()
db_result_queue = queue.Queue()

class DBWorker(threading.Thread):
    def __init__(self, db_file, db_queue, db_result_queue) -> None:
        super().__init__(daemon=True)
        self.db_file = db_file
        self.db_queue = db_queue
        self.db_result_queue = db_result_queue
        self.conn = sqlite3.connect(self.db_file, check_same_thread=False)
        self.cur = self.conn.cursor()

    def run(self) -> None:
        while True:
            item = self.db_queue.get()
            if item is None:
                break
            query, params, result_id = item
            try:
                self.cur.execute(query, params)
                self.conn.commit()
                result = self.cur.fetchall()
                self.db_result_queue.put((result_id, result, None))
            except Exception as e:
                self.db_result_queue.put((result_id, None, e))
            self.db_queue.task_done()

    def close(self) -> None:
        self.conn.close()

def db_execute(query, params=()):
    result_id = threading.get_ident()
    db_queue.put((query, params, result_id))
    while True:
        rid, result, error = db_result_queue.get()
        if rid == result_id:
            if error:
                raise error
            return result

def log_system_message(message):
    """Log a system message to the dedicated system_messages table only.

    Previously system messages were also written into the `sms` table
    (as sender = 'SYSTEM') for backward compatibility. That behaviour
    caused system logs to appear in SMS endpoints. To keep system
    messages separate from user SMS, we now only insert into
    `system_messages`.
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        # Insert only into the dedicated system_messages table
        db_execute(
            "INSERT INTO system_messages (timestamp, message) VALUES (?, ?)",
            (timestamp, message)
        )
    except Exception as e:
        print(f"[System] Failed to log message: {e}")

# --- Flask API Setup ---
app = Flask(__name__)

@app.route('/api/query', methods=['POST'])
def execute_query():
    """Execute a custom SQL query"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'status': 'error', 'message': 'No JSON data provided'}), 400
        
        query = data.get('query')
        params = data.get('params', [])
        
        if not query:
            return jsonify({'status': 'error', 'message': 'Query parameter is required'}), 400
        
        # Execute query using DB worker
        result = db_execute(query, params)
        
        return jsonify({
            'status': 'success', 
            'data': result,
            'row_count': len(result) if result else 0
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'error', 
            'message': 'Database query failed', 
            'error': str(e)
        }), 500

@app.route('/api/sms', methods=['GET'])
def get_all_sms():
    """Get all SMS messages"""
    try:
        result = db_execute("SELECT * FROM sms ORDER BY timestamp DESC")
        return jsonify({
            'status': 'success', 
            'data': result,
            'count': len(result)
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error', 
            'message': 'Could not retrieve SMS messages', 
            'error': str(e)
        }), 500

@app.route('/api/sms/sender/<sender>', methods=['GET'])
def get_sms_by_sender(sender):
    """Get SMS messages by sender"""
    try:
        result = db_execute("SELECT * FROM sms WHERE sender = ? ORDER BY timestamp DESC", (sender,))
        return jsonify({
            'status': 'success', 
            'data': result,
            'count': len(result)
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error', 
            'message': f'Could not retrieve SMS for sender {sender}', 
            'error': str(e)
        }), 500

@app.route('/api/sms/search', methods=['GET'])
def search_sms():
    """Search SMS messages by keyword"""
    try:
        keyword = request.args.get('keyword')
        if not keyword:
            return jsonify({'status': 'error', 'message': 'Keyword parameter is required'}), 400
        
        result = db_execute("SELECT * FROM sms WHERE text LIKE ? ORDER BY timestamp DESC", (f'%{keyword}%',))
        return jsonify({
            'status': 'success', 
            'data': result,
            'count': len(result),
            'keyword': keyword
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error', 
            'message': 'Could not search SMS messages', 
            'error': str(e)
        }), 500

@app.route('/api/sms/date-range', methods=['GET'])
def get_sms_by_date_range():
    """Get SMS messages within a date range"""
    try:
        start_date = request.args.get('start')
        end_date = request.args.get('end')
        
        if not start_date or not end_date:
            return jsonify({
                'status': 'error', 
                'message': 'Both start and end date parameters are required'
            }), 400
        
        result = db_execute(
            "SELECT * FROM sms WHERE timestamp BETWEEN ? AND ? ORDER BY timestamp DESC", 
            (start_date, end_date)
        )
        return jsonify({
            'status': 'success', 
            'data': result,
            'count': len(result),
            'date_range': {'start': start_date, 'end': end_date}
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error', 
            'message': 'Could not retrieve SMS by date range', 
            'error': str(e)
        }), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get database statistics"""
    try:
        total_sms = db_execute("SELECT COUNT(*) FROM sms")[0][0]
        unique_senders = db_execute("SELECT COUNT(DISTINCT sender) FROM sms")[0][0]
        latest_sms = db_execute("SELECT timestamp FROM sms ORDER BY timestamp DESC LIMIT 1")
        oldest_sms = db_execute("SELECT timestamp FROM sms ORDER BY timestamp ASC LIMIT 1")
        
        stats = {
            'total_sms': total_sms,
            'unique_senders': unique_senders,
            'latest_sms': latest_sms[0][0] if latest_sms else None,
            'oldest_sms': oldest_sms[0][0] if oldest_sms else None
        }
        
        return jsonify({
            'status': 'success', 
            'data': stats
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error', 
            'message': 'Could not retrieve statistics', 
            'error': str(e)
        }), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        # Test database connection
        db_execute("SELECT 1")
        return jsonify({
            'status': 'success', 
            'message': 'API and database are healthy',
            'timestamp': datetime.datetime.now().isoformat()
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error', 
            'message': 'Health check failed', 
            'error': str(e)
        }), 500

@app.route('/api/config', methods=['GET'])
def get_config():
    """Get current system configuration"""
    try:
        config = {
            'gpio': {
                'rx_pin': RX_PIN,
                'tx_pin': TX_PIN,
                'baudrate': BAUDRATE
            },
            'database': {
                'file': DB_FILE
            },
            'battery': {
                'check_interval': BATTERY_CHECK_INTERVAL,
                'warning_threshold': BATTERY_WARNING_THRESHOLD,
                'shutdown_threshold': LOW_BATTERY_THRESHOLD,
                'auto_shutdown_enabled': ENABLE_AUTO_SHUTDOWN,
                'current_voltage': last_battery_voltage,
                'status': battery_status,
                'warnings': low_battery_warnings
            },
            'api': {
                'host': API_HOST,
                'port': API_PORT,
                'debug': API_DEBUG
            },
            'sim': {
                'pin_configured': bool(SIM_PIN)  # Don't expose actual PIN
            },
            'sms_reports': {
                'enabled': ENABLE_SMS_REPORTS,
                'recipient': SMS_REPORT_RECIPIENT,
                'interval': SMS_REPORT_INTERVAL,
                'interval_hours': SMS_REPORT_INTERVAL / 3600,
                'last_sent': SMS_REPORT_LAST_SENT,
                'last_sent_formatted': datetime.datetime.fromtimestamp(SMS_REPORT_LAST_SENT).strftime("%Y-%m-%d %H:%M:%S") if SMS_REPORT_LAST_SENT > 0 else "Never"
            }
        }
        
        return jsonify({
            'status': 'success',
            'data': config
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': 'Could not retrieve configuration',
            'error': str(e)
        }), 500

@app.route('/api/battery', methods=['GET'])
def get_battery_status():
    """Get current battery status"""
    try:
        battery_info = get_battery_voltage()
        if battery_info:
            # Add additional status information
            battery_info['low_battery_warnings'] = low_battery_warnings
            battery_info['warning_threshold'] = BATTERY_WARNING_THRESHOLD
            battery_info['shutdown_threshold'] = LOW_BATTERY_THRESHOLD
            battery_info['auto_shutdown_enabled'] = ENABLE_AUTO_SHUTDOWN
            
            return jsonify({
                'status': 'success',
                'data': battery_info
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'message': 'Failed to read battery voltage',
                'debug_info': {
                    'last_voltage': last_battery_voltage,
                    'battery_status': battery_status,
                    'warning_count': low_battery_warnings
                }
            }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': 'Could not retrieve battery status',
            'error': str(e)
        }), 500

@app.route('/api/battery/debug', methods=['GET'])
def get_battery_debug():
    """Get battery debug information and test AT commands"""
    try:
        debug_info = {
            'timestamp': datetime.datetime.now().isoformat(),
            'last_voltage': last_battery_voltage,
            'battery_status': battery_status,
            'warning_count': low_battery_warnings,
            'config': {
                'check_interval': BATTERY_CHECK_INTERVAL,
                'warning_threshold': BATTERY_WARNING_THRESHOLD,
                'shutdown_threshold': LOW_BATTERY_THRESHOLD,
                'auto_shutdown': ENABLE_AUTO_SHUTDOWN
            }
        }
        
        # Test basic AT command
        try:
            at_resp = send_at("AT", delay=1)
            debug_info['at_test'] = {
                'command': 'AT',
                'response': at_resp.strip(),
                'success': 'OK' in at_resp
            }
        except Exception as e:
            debug_info['at_test'] = {
                'command': 'AT',
                'error': str(e),
                'success': False
            }
        
        # Test AT+CBC command with raw output
        try:
            cbc_resp = send_at("AT+CBC", delay=2)
            debug_info['at_cbc'] = {
                'command': 'AT+CBC',
                'response': cbc_resp.strip(),
                'length': len(cbc_resp),
                'contains_cbc': '+CBC' in cbc_resp or 'CBC' in cbc_resp
            }
        except Exception as e:
            debug_info['at_cbc'] = {
                'command': 'AT+CBC',
                'error': str(e),
                'success': False
            }
        
        # Test alternative commands
        alt_commands = ['AT+CPAS', 'AT+CSQ', 'AT+CREG?']
        debug_info['alternative_commands'] = {}
        
        for cmd in alt_commands:
            try:
                resp = send_at(cmd, delay=1)
                debug_info['alternative_commands'][cmd] = {
                    'response': resp.strip(),
                    'success': 'OK' in resp or 'ERROR' not in resp
                }
            except Exception as e:
                debug_info['alternative_commands'][cmd] = {
                    'error': str(e),
                    'success': False
                }
        
        return jsonify({
            'status': 'success',
            'data': debug_info
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': 'Debug information failed',
            'error': str(e)
        }), 500

@app.route('/api/battery/history', methods=['GET'])
def get_battery_history():
    """Get battery-related entries from the system_messages table"""
    try:
        # Search the dedicated system_messages table for battery-related text
        result = db_execute(
            "SELECT * FROM system_messages WHERE message LIKE ? OR message LIKE ? ORDER BY timestamp DESC LIMIT 50",
            ("%battery%", "%Battery%")
        )
        return jsonify({
            'status': 'success',
            'data': result,
            'count': len(result)
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': 'Could not retrieve battery history',
            'error': str(e)
        }), 500

@app.route('/api/system/shutdown', methods=['POST'])
def manual_shutdown():
    """Manually trigger system shutdown"""
    try:
        data = request.get_json()
        confirm = data.get('confirm', False) if data else False
        reason = data.get('reason', 'Manual shutdown requested via API') if data else 'Manual shutdown requested'
        
        if not confirm:
            return jsonify({
                'status': 'error',
                'message': 'Shutdown requires confirmation. Set confirm=true in request body.'
            }), 400
        
        # Log shutdown request
        log_system_message(f"Shutdown initiated: {reason}")
        
        if ENABLE_AUTO_SHUTDOWN:
            # Start shutdown in background thread to allow response
            def delayed_shutdown():
                time.sleep(2)  # Give time for response
                try:
                    subprocess.run(["sudo", "shutdown", "-h", "now"], check=True)
                except:
                    os.system("sudo shutdown -h now")
            
            threading.Thread(target=delayed_shutdown, daemon=True).start()
            
            return jsonify({
                'status': 'success',
                'message': 'System shutdown initiated'
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'message': 'Auto-shutdown disabled in configuration'
            }), 400
            
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': 'Could not initiate shutdown',
            'error': str(e)
        }), 500

@app.route('/api/system/reboot', methods=['POST'])
def reboot_host():
    """Reboot the Linux host system"""
    try:
        data = request.get_json()
        confirm = data.get('confirm', False) if data else False
        reason = data.get('reason', 'Manual reboot requested via API') if data else 'Manual reboot requested'
        
        if not confirm:
            return jsonify({
                'status': 'error',
                'message': 'Reboot requires confirmation. Set confirm=true in request body.'
            }), 400
        
        # Log reboot request
        log_system_message(f"System reboot initiated: {reason}")
        
        def delayed_reboot():
            time.sleep(2)  # Give time for response
            try:
                subprocess.run(["sudo", "reboot"], check=True)
            except:
                os.system("sudo reboot")
        
        threading.Thread(target=delayed_reboot, daemon=True).start()
        
        return jsonify({
            'status': 'success',
            'message': 'System reboot initiated'
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': 'Could not initiate reboot',
            'error': str(e)
        }), 500

@app.route('/api/system/messages', methods=['GET'])
def get_system_messages():
    """Get recent system messages"""
    try:
        limit = request.args.get('limit', 100)
        try:
            limit = int(limit)
            if limit > 1000:
                limit = 1000  # Cap at 1000 messages
        except:
            limit = 100
            
        result = db_execute(
            "SELECT * FROM system_messages ORDER BY timestamp DESC LIMIT ?", 
            (limit,)
        )
        return jsonify({
            'status': 'success',
            'data': result,
            'count': len(result)
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': 'Could not retrieve system messages',
            'error': str(e)
        }), 500

@app.route('/api/system/logs', methods=['GET'])
def get_system_logs():
    """Get system logs with filtering options"""
    try:
        limit = request.args.get('limit', 100)
        filter_text = request.args.get('filter', '')
        
        try:
            limit = int(limit)
            if limit > 1000:
                limit = 1000
        except:
            limit = 100
        
        # Build query with optional text filtering
        if filter_text:
            query = "SELECT * FROM system_messages WHERE message LIKE ? ORDER BY timestamp DESC LIMIT ?"
            params = (f'%{filter_text}%', limit)
        else:
            query = "SELECT * FROM system_messages ORDER BY timestamp DESC LIMIT ?"
            params = (limit,)
        
        result = db_execute(query, params)
        
        return jsonify({
            'status': 'success',
            'data': result,
            'count': len(result),
            'filter_applied': filter_text if filter_text else None
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': 'Could not retrieve system logs',
            'error': str(e)
        }), 500

@app.route('/api/system/oled-status', methods=['GET'])
def get_oled_status():
    """Get OLED display status and current data"""
    try:
        oled_status = {
            'enabled': ENABLE_OLED,
            'available': OLED_AVAILABLE,
            'running': oled_display is not None and oled_display.is_available() if oled_display else False,
            'i2c_address': f"0x{OLED_I2C_ADDRESS:02x}",
            'current_data': {}
        }
        
        # If OLED is running, get current display data
        if oled_status['running']:
            oled_status['current_data'] = {
                'wifi_ip': oled_display.wifi_ip,
                'battery_percent': oled_display.battery_percent,
                'message_count': oled_display.message_count
            }
        
        return jsonify({
            'status': 'success',
            'data': oled_status
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': 'Could not retrieve OLED status',
            'error': str(e)
        }), 500

@app.route('/api/sms/unique-senders', methods=['GET'])
def get_unique_senders():
    """Get all unique SMS senders with message counts"""
    try:
        result = db_execute("""
            SELECT sender, COUNT(*) as message_count, 
                   MIN(timestamp) as first_message,
                   MAX(timestamp) as last_message
            FROM sms 
            WHERE sender != 'SYSTEM'
            GROUP BY sender 
            ORDER BY message_count DESC
        """)
        
        return jsonify({
            'status': 'success',
            'data': result,
            'count': len(result)
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': 'Could not retrieve unique senders',
            'error': str(e)
        }), 500

@app.route('/api/sms/date-range-info', methods=['GET'])
def get_sms_date_range_info():
    """Get the datetime difference between first and last SMS"""
    try:
        # Get first and last SMS timestamps
        first_sms = db_execute("SELECT timestamp FROM sms ORDER BY timestamp ASC LIMIT 1")
        last_sms = db_execute("SELECT timestamp FROM sms ORDER BY timestamp DESC LIMIT 1")
        
        if not first_sms or not last_sms:
            return jsonify({
                'status': 'success',
                'data': {
                    'first_sms': None,
                    'last_sms': None,
                    'time_difference': None,
                    'days_difference': 0,
                    'total_messages': 0
                }
            }), 200
        
        first_timestamp = first_sms[0][0]
        last_timestamp = last_sms[0][0]
        
        # Calculate time difference
        try:
            from datetime import datetime
            first_dt = datetime.strptime(first_timestamp, "%Y-%m-%d %H:%M:%S")
            last_dt = datetime.strptime(last_timestamp, "%Y-%m-%d %H:%M:%S")
            time_diff = last_dt - first_dt
            days_diff = time_diff.days
            
            # Get total message count
            total_count = db_execute("SELECT COUNT(*) FROM sms")[0][0]
            
            return jsonify({
                'status': 'success',
                'data': {
                    'first_sms': first_timestamp,
                    'last_sms': last_timestamp,
                    'time_difference': str(time_diff),
                    'days_difference': days_diff,
                    'hours_difference': round(time_diff.total_seconds() / 3600, 2),
                    'total_messages': total_count
                }
            }), 200
        except ValueError as e:
            return jsonify({
                'status': 'error',
                'message': 'Could not parse timestamps',
                'error': str(e),
                'first_timestamp': first_timestamp,
                'last_timestamp': last_timestamp
            }), 500
            
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': 'Could not calculate SMS date range',
            'error': str(e)
        }), 500

@app.route('/api/sim/restart', methods=['POST'])
def restart_sim800():
    """Restart the SIM800 module via AT command"""
    try:
        data = request.get_json()
        confirm = data.get('confirm', False) if data else False
        
        if not confirm:
            return jsonify({
                'status': 'error',
                'message': 'SIM800 restart requires confirmation. Set confirm=true in request body.'
            }), 400
        
        log_system_message("SIM800 restart command sent")
        
        # Send restart command to SIM800
        resp = send_at("AT+CFUN=1,1", delay=3)
        
        # Give time for module to reboot
        time.sleep(5)
        
        # Try to reconnect
        try:
            test_resp = send_at("AT", delay=2)
            if "OK" in test_resp:
                log_system_message("SIM800 restart completed successfully")
                return jsonify({
                    'status': 'success',
                    'message': 'SIM800 restart completed',
                    'response': resp.strip(),
                    'test_response': test_resp.strip()
                }), 200
            else:
                log_system_message("SIM800 restart may have failed - no response")
                return jsonify({
                    'status': 'warning',
                    'message': 'SIM800 restart command sent but module not responding',
                    'response': resp.strip()
                }), 200
        except Exception as e:
            log_system_message(f"SIM800 restart test failed: {str(e)}")
            return jsonify({
                'status': 'warning',
                'message': 'SIM800 restart command sent but cannot verify status',
                'response': resp.strip(),
                'error': str(e)
            }), 200
            
    except Exception as e:
        log_system_message(f"SIM800 restart failed: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to restart SIM800',
            'error': str(e)
        }), 500

@app.route('/api/sim/set_pin', methods=['POST'])
def set_sim_pin():
    """Set a new SIM PIN"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'status': 'error',
                'message': 'No JSON data provided'
            }), 400
            
        new_pin = data.get('pin')
        if not new_pin:
            return jsonify({
                'status': 'error',
                'message': 'PIN parameter is required'
            }), 400
            
        if not str(new_pin).isdigit() or len(str(new_pin)) != 4:
            return jsonify({
                'status': 'error',
                'message': 'PIN must be a 4-digit numeric string'
            }), 400
        
        log_system_message(f"SIM PIN change requested to: {new_pin}")
        
        # Send new PIN to SIM800
        resp = send_at(f"AT+CPIN={new_pin}", delay=2)
        
        if "OK" in resp:
            log_system_message(f"SIM PIN successfully changed to: {new_pin}")
            
            # Update global SIM_PIN variable
            global SIM_PIN
            SIM_PIN = str(new_pin)
            
            return jsonify({
                'status': 'success',
                'message': f'SIM PIN successfully set to {new_pin}',
                'response': resp.strip()
            }), 200
        else:
            log_system_message(f"SIM PIN change failed: {resp}")
            return jsonify({
                'status': 'error',
                'message': 'Failed to set SIM PIN',
                'response': resp.strip()
            }), 400
            
    except Exception as e:
        log_system_message(f"SIM PIN change error: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Could not set SIM PIN',
            'error': str(e)
        }), 500

@app.route('/api/battery/set_interval', methods=['POST'])
def set_battery_interval():
    """Set battery monitoring interval (in seconds)"""
    global BATTERY_CHECK_INTERVAL
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'status': 'error',
                'message': 'No JSON data provided'
            }), 400
            
        interval = data.get('interval')
        if interval is None:
            return jsonify({
                'status': 'error',
                'message': 'interval parameter is required'
            }), 400
            
        try:
            interval = int(interval)
        except:
            return jsonify({
                'status': 'error',
                'message': 'interval must be a number'
            }), 400
            
        if interval < 30 or interval > 3600:
            return jsonify({
                'status': 'error',
                'message': 'Interval must be between 30 and 3600 seconds (30 sec - 1 hour)'
            }), 400
        
        old_interval = BATTERY_CHECK_INTERVAL
        BATTERY_CHECK_INTERVAL = interval
        
        log_system_message(f"Battery monitoring interval changed from {old_interval}s to {interval}s")
        
        return jsonify({
            'status': 'success',
            'message': f'Battery check interval set to {interval} seconds',
            'old_interval': old_interval,
            'new_interval': interval
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': 'Failed to set battery interval',
            'error': str(e)
        }), 500

@app.route('/api/sim/status', methods=['GET'])
def get_sim_status():
    """Get comprehensive SIM status including signal, operator, and battery info"""
    try:
        # Get signal strength
        signal_info = get_signal_strength()
        
        # Get network operator
        operator_info = get_network_operator()
        
        # Get battery status
        battery_info = get_battery_voltage()
        
        # Compile comprehensive status
        sim_status = {
            'timestamp': datetime.datetime.now().isoformat(),
            'signal': signal_info,
            'operator': operator_info,
            'battery': battery_info,
            'battery_history_points': len(battery_voltage_history),
            'modem_responsive': True  # If we got this far, modem is responding
        }
        
        # Add status summary
        status_summary = []
        if signal_info:
            status_summary.append(f"Signal: {signal_info['signal_quality']}")
        if operator_info:
            status_summary.append(f"Operator: {operator_info['operator']}")
        if battery_info:
            status_summary.append(f"Battery: {battery_info['voltage']:.2f}V ({battery_info.get('charging_status', 'unknown')})")
        
        sim_status['status_summary'] = " | ".join(status_summary)
        
        return jsonify({
            'status': 'success',
            'data': sim_status
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': 'Could not retrieve SIM status',
            'error': str(e)
        }), 500

@app.route('/api/sim/signal', methods=['GET'])
def get_sim_signal():
    """Get SIM signal strength information"""
    try:
        signal_info = get_signal_strength()
        if signal_info:
            return jsonify({
                'status': 'success',
                'data': signal_info
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'message': 'Failed to get signal strength'
            }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': 'Could not retrieve signal strength',
            'error': str(e)
        }), 500

@app.route('/api/sim/operator', methods=['GET'])
def get_sim_operator():
    """Get SIM network operator information"""
    try:
        operator_info = get_network_operator()
        if operator_info:
            return jsonify({
                'status': 'success',
                'data': operator_info
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'message': 'Failed to get network operator'
            }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': 'Could not retrieve network operator',
            'error': str(e)
        }), 500

@app.route('/api/battery/voltage-history', methods=['GET'])
def get_battery_voltage_history():
    """Get battery voltage history for trend analysis"""
    try:
        limit = request.args.get('limit', 10)
        try:
            limit = int(limit)
            if limit > 50:
                limit = 50  # Cap at 50 readings
        except:
            limit = 10
        
        # Return recent voltage history
        recent_history = battery_voltage_history[-limit:] if battery_voltage_history else []
        
        # Calculate some trend statistics if we have enough data
        trend_info = {}
        if len(recent_history) >= 2:
            voltages = [reading['voltage'] for reading in recent_history]
            trend_info = {
                'min_voltage': min(voltages),
                'max_voltage': max(voltages),
                'avg_voltage': sum(voltages) / len(voltages),
                'voltage_range': max(voltages) - min(voltages),
                'charging_status': determine_battery_charging_status()
            }
        
        return jsonify({
            'status': 'success',
            'data': {
                'readings': recent_history,
                'count': len(recent_history),
                'trend_analysis': trend_info
            }
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': 'Could not retrieve battery history',
            'error': str(e)
        }), 500

@app.route('/api/data/delete-all', methods=['POST'])
def delete_all_data():
    """Delete all data from both SMS and system_messages tables"""
    try:
        data = request.get_json()
        confirm = data.get('confirm', False) if data else False
        
        if not confirm:
            return jsonify({
                'status': 'error',
                'message': 'Delete operation requires confirmation. Set confirm=true in request body.'
            }), 400
        
        # Get counts before deletion
        sms_count = db_execute("SELECT COUNT(*) FROM sms")[0][0]
        system_count = db_execute("SELECT COUNT(*) FROM system_messages")[0][0]
        
        # Delete all data
        db_execute("DELETE FROM sms")
        db_execute("DELETE FROM system_messages")
        
        # Reset auto-increment counters
        db_execute("DELETE FROM sqlite_sequence WHERE name IN ('sms', 'system_messages')")
        
        log_system_message(f"All data deleted: {sms_count} SMS messages, {system_count} system messages")
        
        return jsonify({
            'status': 'success',
            'message': f'All data deleted successfully',
            'deleted': {
                'sms_messages': sms_count,
                'system_messages': system_count,
                'total': sms_count + system_count
            }
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': 'Failed to delete all data',
            'error': str(e)
        }), 500

@app.route('/api/data/delete-sms', methods=['POST'])
def delete_sms_only():
    """Delete only SMS messages, keep system messages"""
    try:
        data = request.get_json()
        confirm = data.get('confirm', False) if data else False
        
        if not confirm:
            return jsonify({
                'status': 'error',
                'message': 'Delete operation requires confirmation. Set confirm=true in request body.'
            }), 400
        
        # Get count before deletion
        sms_count = db_execute("SELECT COUNT(*) FROM sms WHERE sender != 'SYSTEM'")[0][0]
        
        # Delete only non-system SMS messages
        db_execute("DELETE FROM sms WHERE sender != 'SYSTEM'")
        
        log_system_message(f"SMS messages deleted: {sms_count} messages")
        
        return jsonify({
            'status': 'success',
            'message': f'SMS messages deleted successfully',
            'deleted': {
                'sms_messages': sms_count
            }
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': 'Failed to delete SMS messages',
            'error': str(e)
        }), 500

@app.route('/api/data/clear-system-logs', methods=['POST'])
def clear_system_logs():
    """Clear only system log messages"""
    try:
        data = request.get_json()
        confirm = data.get('confirm', False) if data else False
        
        if not confirm:
            return jsonify({
                'status': 'error',
                'message': 'Clear operation requires confirmation. Set confirm=true in request body.'
            }), 400
        
        # Get count before deletion
        system_count = db_execute("SELECT COUNT(*) FROM system_messages")[0][0]
        system_sms_count = db_execute("SELECT COUNT(*) FROM sms WHERE sender = 'SYSTEM'")[0][0]
        
        # Clear system messages
        db_execute("DELETE FROM system_messages")
        db_execute("DELETE FROM sms WHERE sender = 'SYSTEM'")
        
        log_system_message(f"System logs cleared: {system_count} system messages, {system_sms_count} system SMS entries")
        
        return jsonify({
            'status': 'success',
            'message': f'System logs cleared successfully',
            'deleted': {
                'system_messages': system_count,
                'system_sms': system_sms_count,
                'total': system_count + system_sms_count
            }
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': 'Failed to clear system logs',
            'error': str(e)
        }), 500

@app.route('/api/data/delete-by-sender', methods=['POST'])
def delete_by_sender():
    """Delete messages from a specific sender"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'status': 'error',
                'message': 'No JSON data provided'
            }), 400
            
        sender = data.get('sender')
        confirm = data.get('confirm', False)
        
        if not sender:
            return jsonify({
                'status': 'error',
                'message': 'Sender parameter is required'
            }), 400
            
        if not confirm:
            return jsonify({
                'status': 'error',
                'message': 'Delete operation requires confirmation. Set confirm=true in request body.'
            }), 400
        
        # Get count before deletion
        count = db_execute("SELECT COUNT(*) FROM sms WHERE sender = ?", (sender,))[0][0]
        
        if count == 0:
            return jsonify({
                'status': 'success',
                'message': f'No messages found from sender: {sender}',
                'deleted': 0
            }), 200
        
        # Delete messages from sender
        db_execute("DELETE FROM sms WHERE sender = ?", (sender,))
        
        log_system_message(f"Messages deleted from sender '{sender}': {count} messages")
        
        return jsonify({
            'status': 'success',
            'message': f'Deleted {count} messages from sender: {sender}',
            'deleted': count,
            'sender': sender
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': 'Failed to delete messages by sender',
            'error': str(e)
        }), 500

@app.route('/api/data/delete-by-keyword', methods=['POST'])
def delete_by_keyword():
    """Delete messages containing a specific keyword"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'status': 'error',
                'message': 'No JSON data provided'
            }), 400
            
        keyword = data.get('keyword')
        confirm = data.get('confirm', False)
        
        if not keyword:
            return jsonify({
                'status': 'error',
                'message': 'Keyword parameter is required'
            }), 400
            
        if not confirm:
            return jsonify({
                'status': 'error',
                'message': 'Delete operation requires confirmation. Set confirm=true in request body.'
            }), 400
        
        # Get count before deletion
        count = db_execute("SELECT COUNT(*) FROM sms WHERE text LIKE ?", (f'%{keyword}%',))[0][0]
        
        if count == 0:
            return jsonify({
                'status': 'success',
                'message': f'No messages found containing keyword: {keyword}',
                'deleted': 0
            }), 200
        
        # Delete messages containing keyword
        db_execute("DELETE FROM sms WHERE text LIKE ?", (f'%{keyword}%',))
        
        log_system_message(f"Messages deleted containing keyword '{keyword}': {count} messages")
        
        return jsonify({
            'status': 'success',
            'message': f'Deleted {count} messages containing keyword: {keyword}',
            'deleted': count,
            'keyword': keyword
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': 'Failed to delete messages by keyword',
            'error': str(e)
        }), 500

@app.route('/api/data/backup', methods=['GET'])
def create_backup():
    """Create and return a database backup"""
    try:
        import shutil
        import tempfile
        from flask import send_file
        
        # Create a timestamp for the backup filename
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"sms_backup_{timestamp}.db"
        
        # Create a temporary copy of the database
        temp_backup_path = os.path.join(tempfile.gettempdir(), backup_filename)
        shutil.copy2(DB_FILE, temp_backup_path)
        
        log_system_message(f"Database backup created: {backup_filename}")
        
        # Return the file as a download
        return send_file(
            temp_backup_path,
            as_attachment=True,
            download_name=backup_filename,
            mimetype='application/x-sqlite3'
        )
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': 'Failed to create backup',
            'error': str(e)
        }), 500

@app.route('/api/data/stats', methods=['GET'])
def get_data_stats():
    """Get detailed data statistics for delete operations"""
    try:
        # Get detailed counts
        total_sms = db_execute("SELECT COUNT(*) FROM sms")[0][0]
        user_sms = db_execute("SELECT COUNT(*) FROM sms WHERE sender != 'SYSTEM'")[0][0]
        system_sms = db_execute("SELECT COUNT(*) FROM sms WHERE sender = 'SYSTEM'")[0][0]
        system_messages = db_execute("SELECT COUNT(*) FROM system_messages")[0][0]
        
        # Get unique senders count
        unique_senders = db_execute("SELECT COUNT(DISTINCT sender) FROM sms WHERE sender != 'SYSTEM'")[0][0]
        
        # Get date range
        first_sms = db_execute("SELECT MIN(timestamp) FROM sms")
        last_sms = db_execute("SELECT MAX(timestamp) FROM sms")
        
        stats = {
            'total_messages': total_sms,
            'user_sms': user_sms,
            'system_sms': system_sms,
            'system_messages': system_messages,
            'unique_senders': unique_senders,
            'date_range': {
                'first': first_sms[0][0] if first_sms and first_sms[0][0] else None,
                'last': last_sms[0][0] if last_sms and last_sms[0][0] else None
            },
            'database_file': DB_FILE,
            'timestamp': datetime.datetime.now().isoformat()
        }
        
        return jsonify({
            'status': 'success',
            'data': stats
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': 'Failed to get data statistics',
            'error': str(e)
        }), 500

@app.route('/api/sms-reports/config', methods=['GET'])
def get_sms_report_config():
    """Get SMS report configuration"""
    try:
        # Calculate time until next report
        next_report_time = None
        time_until_next = None
        
        if ENABLE_SMS_REPORTS and SMS_REPORT_RECIPIENT:
            next_report_timestamp = SMS_REPORT_LAST_SENT + SMS_REPORT_INTERVAL
            next_report_time = datetime.datetime.fromtimestamp(next_report_timestamp).strftime("%Y-%m-%d %H:%M:%S")
            time_until_next = max(0, next_report_timestamp - time.time())
        
        config = {
            'enabled': ENABLE_SMS_REPORTS,
            'recipient': SMS_REPORT_RECIPIENT,
            'interval': SMS_REPORT_INTERVAL,
            'interval_hours': SMS_REPORT_INTERVAL / 3600,
            'interval_days': SMS_REPORT_INTERVAL / 86400,
            'last_sent': SMS_REPORT_LAST_SENT,
            'last_sent_formatted': datetime.datetime.fromtimestamp(SMS_REPORT_LAST_SENT).strftime("%Y-%m-%d %H:%M:%S") if SMS_REPORT_LAST_SENT > 0 else "Never",
            'next_report_time': next_report_time,
            'seconds_until_next': time_until_next
        }
        
        return jsonify({
            'status': 'success',
            'data': config
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': 'Failed to get SMS report configuration',
            'error': str(e)
        }), 500

@app.route('/api/sms-reports/config', methods=['POST'])
def update_sms_report_config():
    """Update SMS report configuration"""
    global ENABLE_SMS_REPORTS, SMS_REPORT_RECIPIENT, SMS_REPORT_INTERVAL
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'status': 'error',
                'message': 'No JSON data provided'
            }), 400
        
        updated_fields = []
        
        # Update enabled status
        if 'enabled' in data:
            enabled = bool(data['enabled'])
            if enabled != ENABLE_SMS_REPORTS:
                ENABLE_SMS_REPORTS = enabled
                update_env_file('ENABLE_SMS_REPORTS', 'true' if enabled else 'false')
                updated_fields.append(f"enabled: {enabled}")
        
        # Update recipient
        if 'recipient' in data:
            recipient = str(data['recipient']).strip()
            if recipient != SMS_REPORT_RECIPIENT:
                SMS_REPORT_RECIPIENT = recipient
                update_env_file('SMS_REPORT_RECIPIENT', recipient)
                updated_fields.append(f"recipient: {recipient}")
        
        # Update interval (accept hours or seconds)
        if 'interval_hours' in data:
            hours = float(data['interval_hours'])
            if hours < 0.25:  # Minimum 15 minutes
                return jsonify({
                    'status': 'error',
                    'message': 'Interval must be at least 0.25 hours (15 minutes)'
                }), 400
            interval = int(hours * 3600)
            if interval != SMS_REPORT_INTERVAL:
                SMS_REPORT_INTERVAL = interval
                update_env_file('SMS_REPORT_INTERVAL', str(interval))
                updated_fields.append(f"interval: {hours}h")
        elif 'interval' in data:
            interval = int(data['interval'])
            if interval < 900:  # Minimum 15 minutes
                return jsonify({
                    'status': 'error',
                    'message': 'Interval must be at least 900 seconds (15 minutes)'
                }), 400
            if interval != SMS_REPORT_INTERVAL:
                SMS_REPORT_INTERVAL = interval
                update_env_file('SMS_REPORT_INTERVAL', str(interval))
                updated_fields.append(f"interval: {interval}s")
        
        if updated_fields:
            log_system_message(f"SMS report config updated: {', '.join(updated_fields)}")
        
        return jsonify({
            'status': 'success',
            'message': f'Configuration updated: {", ".join(updated_fields)}' if updated_fields else 'No changes made',
            'updated_fields': updated_fields
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': 'Failed to update SMS report configuration',
            'error': str(e)
        }), 500

@app.route('/api/sms-reports/send-now', methods=['POST'])
def send_report_now():
    """Send a status report immediately"""
    try:
        data = request.get_json()
        custom_recipient = None
        
        if data and 'recipient' in data:
            custom_recipient = str(data['recipient']).strip()
        
        recipient = custom_recipient or SMS_REPORT_RECIPIENT
        
        if not recipient:
            return jsonify({
                'status': 'error',
                'message': 'No recipient specified. Set recipient in request body or configure default recipient.'
            }), 400
        
        # Generate and send report
        report = generate_status_report()
        
        if send_sms(recipient, report):
            # Update last sent time if using default recipient
            if not custom_recipient:
                global SMS_REPORT_LAST_SENT
                SMS_REPORT_LAST_SENT = time.time()
                update_env_file('SMS_REPORT_LAST_SENT', str(int(SMS_REPORT_LAST_SENT)))
            
            log_system_message(f"Manual status report sent to {recipient}")
            
            return jsonify({
                'status': 'success',
                'message': f'Status report sent to {recipient}',
                'recipient': recipient,
                'report_preview': report[:100] + "..." if len(report) > 100 else report
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'message': f'Failed to send report to {recipient}'
            }), 500
            
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': 'Failed to send status report',
            'error': str(e)
        }), 500

@app.route('/api/sms-reports/test-sms', methods=['POST'])
def test_sms_send():
    """Send a test SMS message"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'status': 'error',
                'message': 'No JSON data provided'
            }), 400
        
        recipient = data.get('recipient')
        message = data.get('message', 'Test message from SIM800L system')
        
        if not recipient:
            return jsonify({
                'status': 'error',
                'message': 'Recipient phone number is required'
            }), 400
        
        if send_sms(recipient, message):
            log_system_message(f"Test SMS sent to {recipient}")
            return jsonify({
                'status': 'success',
                'message': f'Test SMS sent to {recipient}',
                'recipient': recipient,
                'sent_message': message
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'message': f'Failed to send test SMS to {recipient}'
            }), 500
            
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': 'Failed to send test SMS',
            'error': str(e)
        }), 500

@app.route('/api/sms-reports/preview', methods=['GET'])
def preview_status_report():
    """Preview the status report without sending"""
    try:
        report = generate_status_report()
        
        return jsonify({
            'status': 'success',
            'data': {
                'report': report,
                'length': len(report),
                'estimated_sms_count': (len(report) + 159) // 160  # SMS are 160 chars max
            }
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': 'Failed to generate report preview',
            'error': str(e)
        }), 500

def start_api_server():
    """Start the Flask API server in a separate thread"""
    print(f"Starting API server on {API_HOST}:{API_PORT}")
    app.run(host=API_HOST, port=API_PORT, debug=API_DEBUG, threaded=True)

# --- pigpio setup ---
pi = pigpio.pi()
if not pi.connected:
    raise RuntimeError("pigpio daemon not running. Run: sudo systemctl start pigpiod")

# ensure pins are configured
pi.set_mode(RX_PIN, pigpio.INPUT)
pi.set_mode(TX_PIN, pigpio.OUTPUT)
pi.bb_serial_read_open(RX_PIN, BAUDRATE, 8)

def wait_for_modem(timeout=30):
    """Keep sending AT until modem replies or timeout expires"""
    print("[Init] Waiting for modem...")
    deadline = time.time() + timeout
    while time.time() < deadline:
        with uart_lock:
            flush_uart()
            uart_send("AT")
            time.sleep(1)
            resp = uart_read()
            if "OK" in resp:
                print("[Init] Modem ready")
                return True
        time.sleep(1)
    raise RuntimeError("SIM800L not responding")

def flush_uart():
    """Clear out any old data in RX buffer."""
    while True:
        count, data = pi.bb_serial_read(RX_PIN)
        if count == 0:
            break

def uart_send(cmd):
    """Send AT command or raw string over TX_PIN."""
    pi.wave_clear()
    pi.wave_add_serial(TX_PIN, BAUDRATE, (cmd + "\r\n").encode())
    wid = pi.wave_create()
    pi.wave_send_once(wid)
    while pi.wave_tx_busy():
        time.sleep(0.01)
    pi.wave_delete(wid)

def uart_read():
    """Read whatever is in RX buffer."""
    count, data = pi.bb_serial_read(RX_PIN)
    if count:
        return data.decode(errors="ignore")
    return ""

def send_at(cmd, delay=0.5):
    """Send AT command and wait for response with thread-safe UART access."""
    with uart_lock:
        # Clear any existing data first
        flush_uart()
        
        # Send command
        uart_send(cmd)
        time.sleep(delay)
        
        # Read response with timeout
        response = ""
        timeout = time.time() + delay + 2  # Extra time for response
        
        while time.time() < timeout:
            data = uart_read()
            if data:
                response += data
                # Check if we have a complete response (OK or ERROR)
                if "OK" in response or "ERROR" in response:
                    break
            time.sleep(0.05)
        
        print(f">>> {cmd.strip()} \n{response}")
        return response

def get_signal_strength():
    """Get signal strength and quality from SIM800L using AT+CSQ"""
    try:
        resp = send_at("AT+CSQ", delay=2)
        print(f"[Signal] Raw AT+CSQ response: '{resp}'")
        
        # Parse response: +CSQ: <rssi>,<ber>
        # rssi: 0-31 (99=not known or not detectable)
        # ber: bit error rate 0-7 (99=not known or not detectable)
        
        match = re.search(r'\+CSQ:\s*(\d+),(\d+)', resp)
        if match:
            rssi = int(match.group(1))
            ber = int(match.group(2))
            
            # Convert RSSI to dBm: dBm = -113 + 2*rssi (for rssi 0-30)
            if rssi == 99:
                signal_dbm = None
                signal_quality = "Unknown"
            elif rssi == 0:
                signal_dbm = None
                signal_quality = "No Signal"
            else:
                signal_dbm = -113 + (2 * rssi)
                # Determine signal quality
                if rssi >= 20:
                    signal_quality = "Excellent"
                elif rssi >= 15:
                    signal_quality = "Good"
                elif rssi >= 10:
                    signal_quality = "Fair"
                elif rssi >= 5:
                    signal_quality = "Poor"
                else:
                    signal_quality = "Very Poor"
            
            return {
                'rssi': rssi,
                'ber': ber,
                'signal_dbm': signal_dbm,
                'signal_quality': signal_quality,
                'raw_response': resp.strip()
            }
        else:
            print(f"[Signal] Failed to parse CSQ response: '{resp}'")
            return None
            
    except Exception as e:
        print(f"[Signal] Error getting signal strength: {e}")
        return None

def get_network_operator():
    """Get current network operator using AT+COPS"""
    try:
        resp = send_at("AT+COPS?", delay=2)
        print(f"[Operator] Raw AT+COPS response: '{resp}'")
        
        # Parse response: +COPS: <mode>,<format>,<oper>,<act>
        # mode: 0=automatic, 1=manual, 2=deregister, 3=set format only, 4=manual/automatic
        # format: 0=long alphanumeric, 1=short alphanumeric, 2=numeric
        # oper: operator name/code
        # act: access technology (0=GSM, 2=UTRAN, 7=E-UTRAN)
        
        # Try to match different response formats
        patterns = [
            r'\+COPS:\s*(\d+),(\d+),"([^"]+)",(\d+)',  # Full response with quotes
            r'\+COPS:\s*(\d+),(\d+),([^,]+),(\d+)',    # Without quotes
            r'\+COPS:\s*(\d+),(\d+),"([^"]+)"',        # Without access technology
            r'\+COPS:\s*(\d+),(\d+),([^,\r\n]+)'       # Minimal format
        ]
        
        for pattern in patterns:
            match = re.search(pattern, resp)
            if match:
                groups = match.groups()
                mode = int(groups[0])
                format_type = int(groups[1])
                operator = groups[2].strip()
                act = int(groups[3]) if len(groups) > 3 else None
                
                # Decode access technology
                access_tech = {
                    0: "GSM",
                    1: "GSM Compact",
                    2: "UTRAN",
                    3: "GSM w/EGPRS",
                    4: "UTRAN w/HSDPA",
                    5: "UTRAN w/HSUPA",
                    6: "UTRAN w/HSDPA and HSUPA",
                    7: "E-UTRAN"
                }.get(act, f"Unknown ({act})" if act is not None else "Unknown")
                
                return {
                    'operator': operator,
                    'mode': mode,
                    'format': format_type,
                    'access_technology': access_tech,
                    'raw_response': resp.strip()
                }
        
        print(f"[Operator] Failed to parse COPS response: '{resp}'")
        return None
        
    except Exception as e:
        print(f"[Operator] Error getting network operator: {e}")
        return None

def determine_battery_charging_status():
    """Determine if battery is charging or discharging based on voltage history"""
    global battery_voltage_history
    
    if len(battery_voltage_history) < 2:
        return "insufficient_data"
    
    # Look at recent voltage changes (last 5 readings)
    recent_history = battery_voltage_history[-5:]
    
    if len(recent_history) < 2:
        return "insufficient_data"
    
    # Calculate voltage trend
    voltage_changes = []
    for i in range(1, len(recent_history)):
        change = recent_history[i]['voltage'] - recent_history[i-1]['voltage']
        voltage_changes.append(change)
    
    # Average voltage change
    avg_change = sum(voltage_changes) / len(voltage_changes)
    
    # Determine charging status based on voltage trend
    # Threshold for detecting charging (mV change)
    charging_threshold = 0.01  # 10mV increase suggests charging
    discharging_threshold = -0.005  # 5mV decrease suggests discharging
    
    if avg_change > charging_threshold:
        return "charging"
    elif avg_change < discharging_threshold:
        return "discharging"
    else:
        return "stable"

def get_battery_voltage():
    """Get battery voltage from SIM800L using AT+CBC command"""
    global last_battery_voltage, battery_status, battery_voltage_history
    try:
        # Send AT+CBC command to get battery charge
        resp = send_at("AT+CBC", delay=3)  # Longer delay for battery command
        
        # Debug: Print raw response
        print(f"[Battery] Raw AT+CBC response: '{resp}'")
        
        # Parse response: +CBC: <bcs>,<bcl>,<voltage>
        # bcs: Battery Charge Status (not reliable on SIM800L)
        # bcl: Battery Charge Level (1-100%)
        # voltage: Battery voltage in mV
        
        # Try multiple regex patterns for different response formats
        patterns = [
            r'\+CBC:\s*(\d+),(\d+),(\d+)',           # Standard: +CBC: 0,100,4150
            r'CBC:\s*(\d+),(\d+),(\d+)',             # Without +: CBC: 0,100,4150  
            r'\+CBC:\s*(\d+),(\d+)',                 # Two values: +CBC: 0,100
            r'CBC:\s*(\d+),(\d+)',                   # Two values without +: CBC: 0,100
            r'(\d+),(\d+),(\d+)',                    # Just numbers: 0,100,4150
            r'(\d+),(\d+)'                           # Just two numbers: 0,100
        ]
        
        match = None
        for pattern in patterns:
            match = re.search(pattern, resp)
            if match:
                print(f"[Battery] Matched pattern: {pattern}")
                break
        
        if match:
            groups = match.groups()
            if len(groups) >= 3:
                bcs = int(groups[0])  # Not used - unreliable
                bcl = int(groups[1])
                voltage_mv = int(groups[2])
                voltage_v = voltage_mv / 1000.0
                
                print(f"[Battery] Parsed: Level={bcl}%, Voltage={voltage_v:.3f}V")
                
                # Update global variables
                last_battery_voltage = voltage_v
                battery_status = "measured"  # Simple status indicating measurement was successful
                
                # Add to voltage history for charging detection
                current_time = datetime.datetime.now()
                battery_voltage_history.append({
                    'timestamp': current_time.isoformat(),
                    'voltage': voltage_v,
                    'charge_level': bcl
                })
                
                # Keep only last 20 readings for trend analysis
                if len(battery_voltage_history) > 20:
                    battery_voltage_history = battery_voltage_history[-20:]
                
                # Determine charging status
                charging_status = determine_battery_charging_status()
                
                return {
                    'voltage': voltage_v,
                    'voltage_mv': voltage_mv,
                    'charge_level': bcl,
                    'status': 'measured',
                    'charging_status': charging_status,
                    'timestamp': current_time.isoformat(),
                    'raw_response': resp.strip()  # Include raw response for debugging
                }
            elif len(groups) >= 2:
                # Only status and level, no voltage
                bcs = int(groups[0])
                bcl = int(groups[1])
                print(f"[Battery] Partial data: Status={bcs}, Level={bcl}% (no voltage)")
                return None
        else:
            print(f"[Battery] Failed to parse response: '{resp}'")
            
            # Try alternative battery command AT+CPAS (Phone Activity Status)
            try:
                alt_resp = send_at("AT+CPAS", delay=2)
                print(f"[Battery] Alternative AT+CPAS response: '{alt_resp}'")
            except Exception as e:
                print(f"[Battery] AT+CPAS error: {e}")
            
            # Try AT command test
            try:
                test_resp = send_at("AT", delay=1)
                print(f"[Battery] AT test response: '{test_resp}'")
                if "OK" not in test_resp:
                    print("[Battery] Modem not responding properly")
            except Exception as e:
                print(f"[Battery] AT test error: {e}")
            
            return None
            
    except Exception as e:
        print(f"[Battery] Error getting battery voltage: {e}")
        import traceback
        traceback.print_exc()
        return None

def check_battery_and_shutdown():
    """Check battery voltage and initiate shutdown if too low"""
    global low_battery_warnings
    
    battery_info = get_battery_voltage()
    if not battery_info:
        return
    
    voltage = battery_info['voltage']
    charge_level = battery_info['charge_level']
    print(f"[Battery] Voltage: {voltage:.3f}V, Level: {charge_level}%")
    
    # Update OLED display with fresh battery data (if available)
    if oled_display and oled_display.is_available():
        try:
            # Update the OLED's cached battery percentage directly
            oled_display.battery_percent = charge_level
            # Optionally force a display update for immediate visual feedback
            # (Comment out the next line if you want to keep the 10-second update cycle)
            oled_display.force_update()
        except Exception as e:
            print(f"[Battery] OLED update error: {e}")
    
    # Check for low battery warning
    if voltage <= BATTERY_WARNING_THRESHOLD and voltage > LOW_BATTERY_THRESHOLD:
        low_battery_warnings += 1
        print(f"[Battery] WARNING: Low battery {voltage:.3f}V (threshold: {BATTERY_WARNING_THRESHOLD:.1f}V)")
        
        # Log warning using new system message function
        log_system_message(f"Battery warning: {voltage:.3f}V ({charge_level}%)")
    
    # Check for critical battery level
    if voltage <= LOW_BATTERY_THRESHOLD:
        print(f"[Battery] CRITICAL: Battery voltage {voltage:.3f}V <= {LOW_BATTERY_THRESHOLD:.1f}V")
        
        # Log critical battery using new system message function
        log_system_message(f"CRITICAL: Battery {voltage:.3f}V ({charge_level}%) - Initiating shutdown")
        
        if ENABLE_AUTO_SHUTDOWN:
            print("[Battery] Initiating system shutdown...")
            try:
                # Gracefully shutdown the system
                subprocess.run(["sudo", "shutdown", "-h", "now"], check=True)
            except subprocess.CalledProcessError as e:
                print(f"[Battery] Failed to shutdown: {e}")
                # Try alternative shutdown method
                try:
                    os.system("sudo shutdown -h now")
                except:
                    print("[Battery] All shutdown methods failed!")
        else:
            print("[Battery] Auto-shutdown disabled - manual intervention required!")

def battery_monitor_thread():
    """Background thread to monitor battery voltage"""
    print(f"[Battery] Starting battery monitor (interval: {BATTERY_CHECK_INTERVAL}s)")
    
    while True:
        try:
            check_battery_and_shutdown()
            time.sleep(BATTERY_CHECK_INTERVAL)
        except Exception as e:
            print(f"[Battery] Monitor error: {e}")
            time.sleep(10)  # Shorter retry interval on error

def send_sms(phone_number, message):
    """Send SMS message using SIM800L"""
    if not phone_number or not message:
        return False
    
    try:
        with uart_lock:
            print(f"[SMS] Sending message to {phone_number}")
            
            # Set text mode
            resp = send_at("AT+CMGF=1", delay=1)
            if "OK" not in resp:
                print(f"[SMS] Failed to set text mode: {resp}")
                return False
            
            # Prepare to send SMS
            resp = send_at(f'AT+CMGS="{phone_number}"', delay=2)
            if ">" not in resp:
                print(f"[SMS] Failed to initiate SMS: {resp}")
                return False
            
            # Send message content and Ctrl+Z to terminate
            uart_send(message + "\x1A")  # \x1A is Ctrl+Z
            time.sleep(5)  # Wait for send completion
            
            # Read response
            response = ""
            timeout = time.time() + 10
            while time.time() < timeout:
                data = uart_read()
                if data:
                    response += data
                    if "OK" in response or "ERROR" in response:
                        break
                time.sleep(0.1)
            
            print(f"[SMS] Send response: {response}")
            
            if "OK" in response:
                log_system_message(f"SMS sent to {phone_number}: {message[:50]}...")
                return True
            else:
                log_system_message(f"SMS send failed to {phone_number}: {response}")
                return False
                
    except Exception as e:
        print(f"[SMS] Send error: {e}")
        log_system_message(f"SMS send error to {phone_number}: {str(e)}")
        return False

def get_disk_usage():
    """Get disk usage information"""
    try:
        result = subprocess.run(['df', '-h', '/'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            if len(lines) >= 2:
                parts = lines[1].split()
                if len(parts) >= 5:
                    return {
                        'total': parts[1],
                        'used': parts[2],
                        'available': parts[3],
                        'usage_percent': parts[4]
                    }
        return None
    except Exception as e:
        print(f"[Disk] Error getting disk usage: {e}")
        return None

def generate_status_report():
    """Generate comprehensive status report"""
    try:
        # Get current timestamp
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Get SMS statistics
        total_sms = db_execute("SELECT COUNT(*) FROM sms WHERE sender != 'SYSTEM'")[0][0]
        unique_senders = db_execute("SELECT COUNT(DISTINCT sender) FROM sms WHERE sender != 'SYSTEM'")[0][0]
        
        # Get system message count
        system_messages = db_execute("SELECT COUNT(*) FROM system_messages")[0][0]
        
        # Get battery info
        battery_info = get_battery_voltage()
        battery_text = "Unknown"
        if battery_info:
            battery_text = f"{battery_info['voltage']:.2f}V ({battery_info['charge_level']}%)"
        
        # Get disk usage
        disk_info = get_disk_usage()
        disk_text = "Unknown"
        if disk_info:
            disk_text = f"{disk_info['used']}/{disk_info['total']} ({disk_info['usage_percent']} used)"
        
        # Get signal strength
        signal_info = get_signal_strength()
        signal_text = "Unknown"
        if signal_info:
            signal_text = f"{signal_info['signal_quality']} ({signal_info['rssi']})"
        
        # Generate report message
        report = f"""SIM800L System Report
{timestamp}

SMS Stats:
- Total: {total_sms}
- Senders: {unique_senders}

System:
- Battery: {battery_text}
- Disk: {disk_text}
- Signal: {signal_text}
- Sys Messages: {system_messages}

System operational."""
        
        return report
        
    except Exception as e:
        print(f"[Report] Error generating report: {e}")
        return f"SIM800L Report Error: {str(e)} at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

def update_env_file(key, value):
    """Update environment variable in .env.server file"""
    try:
        env_file = '.env.server'
        if not os.path.exists(env_file):
            return False
        
        # Read current file
        with open(env_file, 'r') as f:
            lines = f.readlines()
        
        # Update or add the key
        updated = False
        for i, line in enumerate(lines):
            if line.strip().startswith(f"{key}="):
                lines[i] = f"{key}={value}\n"
                updated = True
                break
        
        if not updated:
            lines.append(f"{key}={value}\n")
        
        # Write updated file
        with open(env_file, 'w') as f:
            f.writelines(lines)
        
        return True
        
    except Exception as e:
        print(f"[Env] Error updating environment file: {e}")
        return False

def check_and_send_report():
    """Check if it's time to send a report and send it"""
    global SMS_REPORT_LAST_SENT
    
    if not ENABLE_SMS_REPORTS or not SMS_REPORT_RECIPIENT:
        return
    
    current_time = time.time()
    
    # Check if it's time for a new report
    if current_time - SMS_REPORT_LAST_SENT >= SMS_REPORT_INTERVAL:
        print("[Report] Generating and sending status report...")
        
        try:
            # Generate report
            report = generate_status_report()
            
            # Send report
            if send_sms(SMS_REPORT_RECIPIENT, report):
                # Update last sent timestamp
                SMS_REPORT_LAST_SENT = current_time
                update_env_file('SMS_REPORT_LAST_SENT', str(int(current_time)))
                
                log_system_message(f"Status report sent to {SMS_REPORT_RECIPIENT}")
                print(f"[Report] Report sent successfully to {SMS_REPORT_RECIPIENT}")
            else:
                log_system_message("Failed to send status report")
                print("[Report] Failed to send report")
                
        except Exception as e:
            print(f"[Report] Error in report sending: {e}")
            log_system_message(f"Report error: {str(e)}")

def sms_report_thread():
    """Background thread to handle SMS reporting"""
    print(f"[Report] Starting SMS report monitor (interval: {SMS_REPORT_INTERVAL//3600:.1f}h, recipient: {SMS_REPORT_RECIPIENT or 'None'})")
    
    # Check every hour (or every 10 minutes if interval is less than 1 hour)
    check_interval = min(3600, SMS_REPORT_INTERVAL // 6) if SMS_REPORT_INTERVAL > 600 else 600
    
    while True:
        try:
            if ENABLE_SMS_REPORTS and SMS_REPORT_RECIPIENT:
                check_and_send_report()
            time.sleep(check_interval)
        except Exception as e:
            print(f"[Report] Thread error: {e}")
            time.sleep(600)  # Wait 10 minutes on error

# --- Init DB ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender TEXT,
            timestamp TEXT,
            text TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS system_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            message TEXT
        )
    """)
    conn.commit()
    conn.close()

# Initialize database
init_db()

# Start the DB worker thread
db_worker = DBWorker(DB_FILE, db_queue, db_result_queue)
db_worker.start()

# Start the API server in a separate thread
api_thread = threading.Thread(target=start_api_server, daemon=True)
api_thread.start()
print(f"API server started on http://{API_HOST}:{API_PORT}")

# Start battery monitoring thread
battery_thread = threading.Thread(target=battery_monitor_thread, daemon=True)
battery_thread.start()
print(f"Battery monitoring started (interval: {BATTERY_CHECK_INTERVAL}s, threshold: {LOW_BATTERY_THRESHOLD}V, auto-shutdown: {ENABLE_AUTO_SHUTDOWN})")

# Start SMS report monitoring thread
if ENABLE_SMS_REPORTS:
    sms_report_monitoring_thread = threading.Thread(target=sms_report_thread, daemon=True)
    sms_report_monitoring_thread.start()
    print(f"SMS reporting started (interval: {SMS_REPORT_INTERVAL//3600:.1f}h, recipient: {SMS_REPORT_RECIPIENT or 'Not set'})")
else:
    print("SMS reporting disabled")

# Initialize and start OLED display
if ENABLE_OLED and OLED_AVAILABLE:
    try:
        # Check battery percentage before initializing OLED display
        print("[OLED Init] Checking battery before display initialization...")
        initial_battery_info = get_battery_voltage()
        if initial_battery_info:
            print(f"[OLED Init] Initial battery: {initial_battery_info['voltage']:.3f}V ({initial_battery_info['charge_level']}%)")
        else:
            print("[OLED Init] ⚠️ Could not read initial battery status")
        
        oled_display = OLEDDisplay(database_path=DB_FILE, i2c_address=OLED_I2C_ADDRESS)
        if oled_display.start():
            print(f"OLED Display started (I2C: 0x{OLED_I2C_ADDRESS:02x})")
            
            # Update OLED with initial battery data if available
            if initial_battery_info:
                try:
                    oled_display.battery_percent = initial_battery_info['charge_level']
                    oled_display.force_update()
                    print(f"[OLED Init] Display updated with initial battery: {initial_battery_info['charge_level']}%")
                except Exception as e:
                    print(f"[OLED Init] ⚠️ Failed to update display with initial battery data: {e}")
        else:
            print("⚠️ OLED Display failed to start")
            oled_display = None
    except Exception as e:
        print(f"⚠️ OLED Display initialization failed: {e}")
        oled_display = None
else:
    print("OLED Display disabled or not available")
    oled_display = None

# Display configuration
print("\n" + "="*50)
print("SMS CAPTURE SYSTEM CONFIGURATION")
print("="*50)
print(f"GPIO RX Pin: {RX_PIN}")
print(f"GPIO TX Pin: {TX_PIN}")
print(f"Baudrate: {BAUDRATE}")
print(f"SIM PIN: {'*' * len(SIM_PIN)}")  # Hide actual PIN for security
print(f"Database: {DB_FILE}")
print(f"Battery Check Interval: {BATTERY_CHECK_INTERVAL}s")
print(f"Battery Warning Threshold: {BATTERY_WARNING_THRESHOLD}V")
print(f"Battery Shutdown Threshold: {LOW_BATTERY_THRESHOLD}V")
print(f"Auto Shutdown: {ENABLE_AUTO_SHUTDOWN}")
print(f"API Server: http://{API_HOST}:{API_PORT}")
print(f"OLED Display: {'Enabled' if ENABLE_OLED and OLED_AVAILABLE else 'Disabled'} (I2C: 0x{OLED_I2C_ADDRESS:02x})")
print(f"SMS Reports: {'Enabled' if ENABLE_SMS_REPORTS else 'Disabled'} (Interval: {SMS_REPORT_INTERVAL//3600:.1f}h, Recipient: {SMS_REPORT_RECIPIENT or 'Not set'})")
print("="*50)

# --- SIM setup ---
flush_uart()
wait_for_modem()
send_at("ATE0")                  # echo off
send_at(f"AT+CPIN={SIM_PIN}")    # SIM PIN
time.sleep(1)
send_at("AT+CMGF=1")             # text mode
send_at("AT+CNMI=2,2,0,0,0")     # new SMS -> directly to serial

# --- Capture loop ---
print("Waiting for new messages...")

try:
    buffer = ""
    while True:
        # Only read UART data if lock is available (non-blocking check)
        if uart_lock.acquire(blocking=False):
            try:
                data = uart_read()
                if data:
                    buffer += data
            finally:
                uart_lock.release()
        else:
            # If lock is held by battery monitoring, just wait a bit
            time.sleep(0.1)
            continue
            
        if buffer:
            # split into lines
            while "\r\n" in buffer:
                line, buffer = buffer.split("\r\n", 1)
                line = line.strip()
                if not line:
                    continue
                print(f"line: {line}")

                if line.startswith("+CMT:"):
                    m = re.search(r'\+CMT: "([^"]+)"', line)
                    sender = m.group(1) if m else "UNKNOWN"
                    body = ""

                    # collect SMS content
                    timeout = time.time() + 5
                    while time.time() < timeout:
                        # Use the same lock-aware approach for reading SMS content
                        if uart_lock.acquire(blocking=False):
                            try:
                                newdata = uart_read()
                                if newdata:
                                    buffer += newdata
                            finally:
                                uart_lock.release()
                        else:
                            time.sleep(0.05)
                            continue
                            
                        if newdata:
                            while "\r\n" in buffer:
                                next_line, buffer = buffer.split("\r\n", 1)
                                next_line = next_line.strip()
                                if not next_line:
                                    continue
                                if next_line.startswith("+CMT:"):
                                    # new SMS started
                                    buffer = next_line + "\r\n" + buffer
                                    timeout = 0
                                    break
                                body += next_line + " "
                        else:
                            time.sleep(0.05)

                    body = body.strip()
                    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                    print(f"[New SMS] From: {sender} @ {timestamp}: {body}")

                    # Insert into DB using worker thread
                    db_execute(
                        "INSERT INTO sms (sender, timestamp, text) VALUES (?, ?, ?)",
                        (sender, timestamp, body)
                    )
                    
                    # Update OLED display immediately when new SMS arrives
                    if oled_display and oled_display.is_available():
                        oled_display.force_update()

        time.sleep(0.1)

except KeyboardInterrupt:
    print("Exiting...")

finally:
    # Stop OLED display
    if oled_display:
        oled_display.stop()
    
    pi.bb_serial_read_close(RX_PIN)
    pi.stop()
    
    # Shutdown DB worker
    db_queue.put(None)
    db_worker.join()
    db_worker.close()
