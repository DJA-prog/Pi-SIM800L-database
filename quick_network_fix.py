#!/usr/bin/env python3
"""
Quick SIM800L Network Registration Fix
Addresses common network registration and SMS center issues
"""

import os
import time
import pigpio
from dotenv import load_dotenv

load_dotenv('.env.server')

RX_PIN = int(os.getenv('RX_PIN', 13))
TX_PIN = int(os.getenv('TX_PIN', 12))
BAUDRATE = int(os.getenv('BAUDRATE', 9600))
SIM_PIN = os.getenv('SIM_PIN', '9438')

pi = None

def init_uart():
    global pi
    pi = pigpio.pi()
    if not pi.connected:
        print("❌ pigpio daemon not running")
        return False
    pi.set_mode(RX_PIN, pigpio.INPUT)
    pi.set_mode(TX_PIN, pigpio.OUTPUT)
    pi.bb_serial_read_open(RX_PIN, BAUDRATE, 8)
    return True

def cleanup():
    global pi
    if pi and pi.connected:
        pi.bb_serial_read_close(RX_PIN)
        pi.stop()

def send_command(cmd, wait_time=2):
    # Clear buffer
    while True:
        count, _ = pi.bb_serial_read(RX_PIN)
        if count == 0:
            break
    
    # Send command
    print(f">>> {cmd}")
    pi.wave_clear()
    pi.wave_add_serial(TX_PIN, BAUDRATE, (cmd + "\r\n").encode())
    wid = pi.wave_create()
    pi.wave_send_once(wid)
    while pi.wave_tx_busy():
        time.sleep(0.01)
    pi.wave_delete(wid)
    
    # Read response
    time.sleep(wait_time)
    response = ""
    for _ in range(30):  # 3 seconds total
        count, data = pi.bb_serial_read(RX_PIN)
        if count:
            response += data.decode(errors="ignore")
        time.sleep(0.1)
    
    print(f"<<< {response.strip()}")
    return response

def main():
    print("🔧 SIM800L Quick Network Fix")
    print("=" * 40)
    
    try:
        if not init_uart():
            return
        
        # Test basic communication
        response = send_command("AT")
        if "OK" not in response:
            print("❌ No communication with SIM800L")
            return
        
        # Force network registration
        print("\n🔄 Forcing network registration...")
        send_command("AT+CREG=2", 2)  # Enable network registration notifications
        send_command("AT+COPS=0", 10)  # Auto select operator
        
        # Wait for registration
        print("⏳ Waiting for network registration (60 seconds)...")
        for i in range(60):
            response = send_command("AT+CREG?", 1)
            if "+CREG: 2,1" in response or "+CREG: 2,5" in response:
                print(f"\n✅ Network registered after {i+1} seconds!")
                break
            print(".", end="", flush=True)
            time.sleep(1)
        else:
            print("\n❌ Network registration failed")
            print("💡 Try moving to a location with better signal")
            return
        
        # Set SMS text mode
        print("\n📱 Configuring SMS...")
        send_command("AT+CMGF=1", 1)
        
        # Try to auto-configure SMS center
        print("🔧 Configuring SMS center...")
        
        # First check if there's already an SMS center
        response = send_command("AT+CSCA?", 1)
        if '"+' not in response or '"00000"' in response:
            print("SMS center not set, trying common ones...")
            
            # Try common SMS centers for Namibian networks
            centers = [
                "+264811000100",  # MTC
                "+264850000100",  # TN Mobile
                "+27831000100",   # Fallback
            ]
            
            for center in centers:
                print(f"Trying {center}...")
                response = send_command(f'AT+CSCA="{center}"', 2)
                if "OK" in response:
                    print(f"✅ SMS center set to {center}")
                    break
            else:
                print("⚠️ Could not auto-set SMS center")
                print("💡 Contact your carrier for the correct SMS center number")
        
        # Enable SMS notifications
        send_command("AT+CNMI=1,2,0,0,0", 1)
        
        print("\n🎉 Setup completed! Try sending SMS now.")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        cleanup()

if __name__ == "__main__":
    main()