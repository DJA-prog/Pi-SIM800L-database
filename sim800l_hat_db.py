#!/usr/bin/env python3
import time
import re
import sqlite3
import datetime
import pigpio
import threading
import queue

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
