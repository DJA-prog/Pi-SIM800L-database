#!/usr/bin/env python3
import time
import re
import datetime
import pigpio

# ---------------- CONFIG ----------------
RX_PIN = 13   # GPIO for SIM800L TX -> Pi RX
TX_PIN = 12   # GPIO for SIM800L RX <- Pi TX
BAUDRATE = 9600
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


# --- SIM setup ---
flush_uart()
wait_for_modem()
send_at("ATE0")                  # echo off
time.sleep(1)

# --- CBC Battery Check ---
print("\n" + "="*50)
print("PERFORMING BATTERY CHECK (AT+CBC)")
print("="*50)

# Send CBC command
cbc_response = send_at("AT+CBC", delay=2)

# Parse the response
print(f"\nRaw CBC Response: '{cbc_response}'")
print(f"Response length: {len(cbc_response)}")
print(f"Response bytes: {[hex(ord(c)) for c in cbc_response[:50]]}")  # First 50 chars as hex

# Try different parsing patterns
patterns = [
    r'\+CBC:\s*(\d+),(\d+),(\d+)',           # Standard: +CBC: 0,100,4150
    r'CBC:\s*(\d+),(\d+),(\d+)',             # Without +: CBC: 0,100,4150  
    r'\+CBC:\s*(\d+),(\d+)',                 # Two values: +CBC: 0,100
    r'CBC:\s*(\d+),(\d+)',                   # Two values without +: CBC: 0,100
    r'(\d+),(\d+),(\d+)',                    # Just numbers: 0,100,4150
    r'(\d+),(\d+)'                           # Just two numbers: 0,100
]

voltage = None
battery_status = None
charge_level = None

for i, pattern in enumerate(patterns):
    match = re.search(pattern, cbc_response)
    if match:
        print(f"\nPattern {i+1} matched: {pattern}")
        groups = match.groups()
        print(f"Captured groups: {groups}")
        
        if len(groups) == 3:
            status, level, voltage_mv = groups
            battery_status = int(status)
            charge_level = int(level)
            voltage = int(voltage_mv) / 1000.0  # Convert mV to V
            print(f"Parsed - Status: {battery_status}, Level: {charge_level}%, Voltage: {voltage}V")
        elif len(groups) == 2:
            battery_status = int(groups[0])
            charge_level = int(groups[1])
            print(f"Parsed - Status: {battery_status}, Level: {charge_level}%")
        break

if voltage is None:
    print("\n❌ Failed to parse battery voltage from response")
    print("Trying alternative commands...")
    
    # Try alternative commands
    alt_commands = ['AT+CPAS', 'AT+CSQ', 'AT+CREG?', 'AT']
    for cmd in alt_commands:
        print(f"\nTesting {cmd}:")
        alt_resp = send_at(cmd, delay=1)
else:
    print(f"\n✅ Battery Check Successful!")
    print(f"   Voltage: {voltage}V")
    if battery_status is not None:
        status_desc = {0: "Not charging", 1: "Charging", 2: "Charge complete"}.get(battery_status, "Unknown")
        print(f"   Status: {battery_status} ({status_desc})")
    if charge_level is not None:
        print(f"   Charge Level: {charge_level}%")

print("\n" + "="*50)
print("BATTERY CHECK COMPLETE")
print("="*50)

# Clean up and exit
pi.bb_serial_read_close(RX_PIN)
pi.stop()
print("Script finished.")