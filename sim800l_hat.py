#!/usr/bin/env python3
import time
import re
import sqlite3
import datetime
import pigpio

# ---------------- CONFIG ----------------
RX_PIN = 13   # GPIO for SIM800L TX -> Pi RX
TX_PIN = 12   # GPIO for SIM800L RX <- Pi TX
BAUDRATE = 9600
SIM_PIN = "9438"
DB_FILE = "sms_messages.db"
# -----------------------------------------

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
    return conn, cur

conn, cur = init_db()

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

                    # Insert into DB
                    cur.execute(
                        "INSERT INTO sms (sender, timestamp, text) VALUES (?, ?, ?)",
                        (sender, timestamp, body)
                    )
                    conn.commit()

        time.sleep(0.1)

except KeyboardInterrupt:
    print("Exiting...")

finally:
    pi.bb_serial_read_close(RX_PIN)
    pi.stop()
    conn.close()
