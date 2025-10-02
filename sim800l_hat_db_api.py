#!/usr/bin/env python3
import time
import re
import sqlite3
import datetime
import pigpio
import threading
import queue
from flask import Flask, request, jsonify

# ---------------- CONFIG ----------------
RX_PIN = 13   # GPIO for SIM800L TX -> Pi RX
TX_PIN = 12   # GPIO for SIM800L RX <- Pi TX
BAUDRATE = 9600
SIM_PIN = "9438"
DB_FILE = "sms_messages.db"
# -----------------------------------------

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

def start_api_server():
    """Start the Flask API server in a separate thread"""
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)

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
        resp = send_at("AT", delay=1)
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
    """Send AT command and wait for response."""
    uart_send(cmd)
    time.sleep(delay)
    resp = uart_read()
    print(f">>> {cmd.strip()} \n{resp}")
    return resp

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
print("API server started on http://0.0.0.0:5000")

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
        data = uart_read()
        if data:
            buffer += data
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
                        newdata = uart_read()
                        if newdata:
                            buffer += newdata
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
