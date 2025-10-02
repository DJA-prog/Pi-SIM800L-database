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
# -----------------------------------------

# Global variables for battery monitoring
last_battery_voltage = 0.0
battery_status = "unknown"
low_battery_warnings = 0

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
    """Log a system message to both SMS and system_messages tables"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        # Log to SMS table for backward compatibility
        db_execute(
            "INSERT INTO sms (sender, timestamp, text) VALUES (?, ?, ?)",
            ("SYSTEM", timestamp, message)
        )
        # Log to dedicated system messages table
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
    """Get battery-related system messages from SMS log"""
    try:
        result = db_execute(
            "SELECT * FROM sms WHERE sender = 'SYSTEM' AND text LIKE '%battery%' OR text LIKE '%Battery%' ORDER BY timestamp DESC LIMIT 50"
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

def get_battery_voltage():
    """Get battery voltage from SIM800L using AT+CBC command"""
    global last_battery_voltage, battery_status
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
                
                return {
                    'voltage': voltage_v,
                    'voltage_mv': voltage_mv,
                    'charge_level': bcl,
                    'status': 'measured',
                    'timestamp': datetime.datetime.now().isoformat(),
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

        time.sleep(0.1)

except KeyboardInterrupt:
    print("Exiting...")

finally:
    pi.bb_serial_read_close(RX_PIN)
    pi.stop()
    
    # Shutdown DB worker
    db_queue.put(None)
    db_worker.join()
    db_worker.close()
