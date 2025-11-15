#!/usr/bin/env python3
"""
Simple SIM800L SMS Send/Receive Test
Focus on waiting for SMS reception and testing SMS sending
"""

import os
import time
import pigpio
import re
import signal
import sys
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv('.env.server')

# Configuration
RX_PIN = int(os.getenv('RX_PIN', 13))
TX_PIN = int(os.getenv('TX_PIN', 12))
BAUDRATE = int(os.getenv('BAUDRATE', 9600))
SIM_PIN = os.getenv('SIM_PIN', '9438')
TEST_PHONE_NUMBER = os.getenv('TEST_PHONE_NUMBER', '+264816828893')

# Global variables
pi = None
running = True

def cleanup(signum=None, frame=None):
    """Clean up on exit"""
    global running, pi
    running = False
    if pi and pi.connected:
        pi.bb_serial_read_close(RX_PIN)
        pi.stop()
    print("\n✓ Cleanup completed")
    if signum:
        sys.exit(0)

def init_uart():
    """Initialize UART communication"""
    global pi
    pi = pigpio.pi()
    if not pi.connected:
        print("❌ pigpio daemon not running. Start with: sudo systemctl start pigpiod")
        return False
    
    pi.set_mode(RX_PIN, pigpio.INPUT)
    pi.set_mode(TX_PIN, pigpio.OUTPUT)
    pi.bb_serial_read_open(RX_PIN, BAUDRATE, 8)
    print(f"✓ UART initialized (RX:{RX_PIN}, TX:{TX_PIN}, {BAUDRATE} baud)")
    return True

def send_command(cmd, wait_time=1, verbose=False):
    """Send AT command and get response"""
    # Clear buffer first
    if verbose:
        print(f"[DEBUG] Clearing RX buffer...")
    while True:
        count, data = pi.bb_serial_read(RX_PIN)
        if count == 0:
            break
        if verbose:
            print(f"[DEBUG] Cleared {count} bytes: {repr(data.decode(errors='ignore'))}")
    
    # Send command
    print(f">>> {cmd}")
    pi.wave_clear()
    pi.wave_add_serial(TX_PIN, BAUDRATE, (cmd + "\r\n").encode())
    wid = pi.wave_create()
    pi.wave_send_once(wid)
    while pi.wave_tx_busy():
        time.sleep(0.01)
    pi.wave_delete(wid)
    
    if verbose:
        print(f"[DEBUG] Command sent, waiting {wait_time}s...")
    
    # Wait and read response
    time.sleep(wait_time)
    response = ""
    deadline = time.time() + 3
    read_count = 0
    while time.time() < deadline:
        count, data = pi.bb_serial_read(RX_PIN)
        if count:
            read_count += 1
            decoded = data.decode(errors="ignore")
            response += decoded
            if verbose:
                print(f"[DEBUG] Read {read_count}: {count} bytes: {repr(decoded)}")
        time.sleep(0.1)
    
    print(f"<<< {response.strip()}")
    if verbose:
        print(f"[DEBUG] Total response length: {len(response)} chars")
    return response

def initialize_sms():
    """Initialize SIM800L for SMS operations"""
    print("🔧 Initializing SIM800L...")
    
    # Basic communication test
    response = send_command("AT")
    if "OK" not in response:
        print("❌ No response from SIM800L")
        return False
    
    # Check/unlock SIM
    response = send_command("AT+CPIN?", 2)
    if "SIM PIN" in response:
        print("🔐 Unlocking SIM...")
        response = send_command(f"AT+CPIN={SIM_PIN}", 3)
        if "OK" not in response:
            print("❌ Failed to unlock SIM")
            return False
        time.sleep(3)
    
    # Set SMS text mode
    response = send_command("AT+CMGF=1")
    if "OK" not in response:
        print("❌ Failed to set SMS text mode")
        return False
    
    # Enable SMS notifications
    response = send_command("AT+CNMI=1,2,0,0,0")
    if "OK" not in response:
        print("❌ Failed to enable SMS notifications")
        return False
    
    print("✅ SIM800L initialized and ready for SMS")
    return True

def send_sms(phone_number, message):
    """Send SMS message"""
    print(f"\n📤 Sending SMS to {phone_number}")
    print(f"Message: {message}")
    
    # Start SMS composition
    response = send_command(f'AT+CMGS="{phone_number}"', 2)
    
    if ">" not in response:
        print("❌ Failed to get SMS prompt")
        print(f"Response was: {repr(response)}")
        return False
    
    print("✓ Got SMS prompt, sending message...")
    
    # Clear buffer before sending message
    while True:
        count, _ = pi.bb_serial_read(RX_PIN)
        if count == 0:
            break
    
    # Send message + Ctrl+Z (ASCII 26)
    message_with_ctrl_z = message + chr(26)
    print(f"[DEBUG] Sending message with Ctrl+Z: {repr(message_with_ctrl_z)}")
    
    pi.wave_clear()
    pi.wave_add_serial(TX_PIN, BAUDRATE, message_with_ctrl_z.encode())
    wid = pi.wave_create()
    pi.wave_send_once(wid)
    while pi.wave_tx_busy():
        time.sleep(0.01)
    pi.wave_delete(wid)
    
    print("⏳ Waiting for SMS confirmation...")
    
    # Wait for confirmation with verbose output
    time.sleep(2)  # Initial wait
    response = ""
    deadline = time.time() + 20  # Longer timeout for SMS
    read_count = 0
    
    while time.time() < deadline:
        count, data = pi.bb_serial_read(RX_PIN)
        if count:
            read_count += 1
            decoded = data.decode(errors="ignore")
            response += decoded
            print(f"[SMS] Read {read_count}: {count} bytes: {repr(decoded)}")
            
            # Check if we got the confirmation
            if "+CMGS:" in response and "OK" in response:
                break
            elif "ERROR" in response:
                break
        time.sleep(0.2)
    
    print(f"[SMS] Final response: {repr(response)}")
    
    if "+CMGS:" in response and "OK" in response:
        # Extract message reference number
        match = re.search(r'\+CMGS:\s*(\d+)', response)
        if match:
            msg_ref = match.group(1)
            print(f"✅ SMS sent successfully! Message reference: {msg_ref}")
        else:
            print("✅ SMS sent successfully!")
        return True
    elif "ERROR" in response:
        print("❌ SMS sending failed with ERROR")
        return False
    else:
        print("❌ SMS sending failed - no confirmation received")
        print(f"Response: {response.strip()}")
        return False

def wait_for_sms(timeout_seconds=300):
    """Wait for incoming SMS messages"""
    print(f"\n📥 Waiting for SMS messages (timeout: {timeout_seconds}s)")
    print("💡 Send an SMS to this device now")
    print("⏹️  Press Ctrl+C to stop")
    print("🔍 Verbose mode: All RX data will be shown")
    
    start_time = time.time()
    buffer = ""
    sms_count = 0
    last_activity = time.time()
    
    try:
        while running and (time.time() - start_time) < timeout_seconds:
            count, data = pi.bb_serial_read(RX_PIN)
            if count:
                # Show raw data received (verbose output)
                raw_data = data.decode(errors="ignore")
                current_time = time.time() - start_time
                print(f"[{current_time:6.1f}s] RX({count} bytes): {repr(raw_data)}")
                
                buffer += raw_data
                last_activity = time.time()
                
                # Show accumulated buffer if it's getting long
                if len(buffer) > 100:
                    print(f"[{current_time:6.1f}s] Buffer({len(buffer)} chars): {repr(buffer[-100:])}")
                
                # Check for SMS notification
                if "+CMTI:" in buffer:
                    sms_count += 1
                    print(f"\n🔔 SMS {sms_count} received!")
                    print(f"Notification: {buffer.strip()}")
                    
                    # Extract SMS index and read it
                    match = re.search(r'\+CMTI:\s*"[^"]*",(\d+)', buffer)
                    if match:
                        index = match.group(1)
                        print(f"📖 Reading SMS from index {index}...")
                        
                        # Read the SMS
                        response = send_command(f"AT+CMGR={index}", 2)
                        print(f"📄 SMS Content:\n{response}")
                        
                        # Delete the SMS to free space
                        send_command(f"AT+CMGD={index}", 1)
                    
                    buffer = ""  # Clear buffer
                
                # Check for direct SMS content
                elif "+CMT:" in buffer:
                    sms_count += 1
                    print(f"\n📨 Direct SMS {sms_count} received!")
                    print(f"Content: {buffer.strip()}")
                    buffer = ""
                
                # Check for any other interesting patterns
                elif any(pattern in buffer.upper() for pattern in ["+CMGL:", "+CMGR:", "SMS", "MESSAGE"]):
                    print(f"[{current_time:6.1f}s] 📧 Possible SMS-related data: {repr(buffer)}")
            else:
                # Show periodic status when no data
                now = time.time()
                if now - last_activity > 30:  # Every 30 seconds of no activity
                    elapsed = now - start_time
                    remaining = timeout_seconds - elapsed
                    print(f"[{elapsed:6.1f}s] ⏳ No activity for 30s, {remaining:.0f}s remaining...")
                    last_activity = now
            
            time.sleep(0.1)
    
    except KeyboardInterrupt:
        print("\n⏹️ Stopped by user")
    
    elapsed = time.time() - start_time
    print(f"\n📊 Results:")
    print(f"   Duration: {elapsed:.1f} seconds")
    print(f"   SMS received: {sms_count}")
    
    return sms_count

def reset_gsm_module():
    """Reset the GSM module using various methods"""
    print("\n🔄 GSM Module Reset Options")
    print("=" * 40)
    print("1. Software reset (AT command)")
    print("2. Factory reset (clear all settings)")
    print("3. Power cycle simulation")
    print("4. Network reset only")
    print("5. Cancel")
    print("-" * 40)
    
    choice = input("Select reset method (1-5): ").strip()
    
    if choice == "1":
        print("\n🔄 Performing software reset...")
        print("⚠️ Module will restart and may take 10-15 seconds...")
        
        # Send reset command
        response = send_command("AT+CFUN=1,1", 3, verbose=True)
        
        print("Waiting for module to restart...")
        time.sleep(15)  # Wait for restart
        
        # Test communication after reset
        print("Testing communication after reset...")
        for i in range(10):
            response = send_command("AT", 1)
            if "OK" in response:
                print("✅ Module reset successful and responding!")
                return True
            print(f"Attempt {i+1}/10 - waiting...")
            time.sleep(2)
        
        print("❌ Module not responding after reset")
        return False
    
    elif choice == "2":
        print("\n🏭 Performing factory reset...")
        print("⚠️ This will erase ALL settings and stored data!")
        
        confirm = input("Are you sure? Type 'YES' to confirm: ")
        if confirm != "YES":
            print("Factory reset cancelled")
            return False
        
        # Factory reset commands
        print("Step 1: Reset to factory defaults...")
        send_command("AT&F", 2, verbose=True)
        
        print("Step 2: Clear all stored data...")
        send_command("AT+CMGD=1,4", 3, verbose=True)  # Delete all SMS
        
        print("Step 3: Reset network settings...")
        send_command("AT+COPS=2", 2, verbose=True)  # Deregister
        send_command("AT+COPS=0", 5, verbose=True)  # Auto register
        
        print("Step 4: Software restart...")
        send_command("AT+CFUN=1,1", 3, verbose=True)
        
        print("Waiting 20 seconds for complete restart...")
        time.sleep(20)
        
        # Test communication
        for i in range(10):
            response = send_command("AT", 1)
            if "OK" in response:
                print("✅ Factory reset completed successfully!")
                return True
            print(f"Attempt {i+1}/10 - waiting...")
            time.sleep(2)
        
        print("❌ Module not responding after factory reset")
        return False
    
    elif choice == "3":
        print("\n⚡ Performing power cycle simulation...")
        print("This uses AT commands to simulate power off/on")
        
        # Minimum functionality mode (power down radio)
        print("Step 1: Powering down radio...")
        send_command("AT+CFUN=0", 3, verbose=True)
        
        print("Waiting 5 seconds...")
        time.sleep(5)
        
        # Full functionality mode (power up)
        print("Step 2: Powering up radio...")
        send_command("AT+CFUN=1", 5, verbose=True)
        
        print("Step 3: Testing communication...")
        response = send_command("AT", 2)
        if "OK" in response:
            print("✅ Power cycle completed successfully!")
            return True
        else:
            print("❌ Power cycle failed")
            return False
    
    elif choice == "4":
        print("\n📡 Performing network reset only...")
        
        # Deregister from network
        print("Step 1: Deregistering from network...")
        send_command("AT+COPS=2", 3, verbose=True)
        
        # Reset network registration settings
        print("Step 2: Resetting network settings...")
        send_command("AT+CREG=0", 1, verbose=True)
        send_command("AT+CREG=2", 1, verbose=True)
        
        # Auto select network again
        print("Step 3: Re-registering to network...")
        send_command("AT+COPS=0", 10, verbose=True)
        
        # Check registration
        print("Step 4: Checking registration...")
        time.sleep(5)
        response = send_command("AT+CREG?", 2, verbose=True)
        
        match = re.search(r'\+CREG:\s*(\d+),(\d+)', response)
        if match:
            stat = int(match.group(2))
            if stat in [1, 5]:
                print("✅ Network reset successful - registered!")
                return True
            else:
                print(f"⚠️ Network reset completed but registration status: {stat}")
                return False
        else:
            print("❌ Could not determine registration status")
            return False
    
    elif choice == "5":
        print("Reset cancelled")
        return False
    
    else:
        print("❌ Invalid choice")
        return False

def hardware_reset_info():
    """Show information about hardware reset options"""
    print("\n🔌 Hardware Reset Options")
    print("=" * 50)
    print("For complete hardware reset, you can:")
    print()
    print("1. 🔌 Power Reset:")
    print("   - Disconnect VCC/power for 10+ seconds")
    print("   - Reconnect power")
    print("   - Wait 10-15 seconds for boot")
    print()
    print("2. 🔘 Reset Pin (if available):")
    print("   - Connect RESET/RST pin to GND for 1 second")
    print("   - Release to VCC")
    print("   - Wait 10-15 seconds for boot")
    print()
    print("3. 🔋 Battery Disconnect (if using battery):")
    print("   - Remove main power AND backup battery")
    print("   - Wait 30+ seconds")
    print("   - Reconnect power sources")
    print()
    print("4. ⚡ AT Command Power Control:")
    print("   - AT+CPOWD=1 (emergency shutdown)")
    print("   - Physically power cycle after shutdown")
    print()
    print("💡 Software resets (AT commands) are usually sufficient")
    print("   for most issues and don't require physical access.")

def try_network_registration():
    """Try to force network registration"""
    print("\n🔄 Attempting to fix network registration...")
    
    # Enable network registration notifications
    print("Enabling network registration notifications...")
    send_command("AT+CREG=2", 2, verbose=True)
    
    # Try manual then automatic network selection
    print("\nTrying automatic network selection...")
    send_command("AT+COPS=0", 10, verbose=True)  # Auto select operator
    
    # Wait and check registration
    print("Waiting 10 seconds for registration...")
    time.sleep(10)
    
    response = send_command("AT+CREG?", 2, verbose=True)
    match = re.search(r'\+CREG:\s*(\d+),(\d+)', response)
    if match:
        stat = int(match.group(2))
        if stat in [1, 5]:
            print("✅ Network registration successful!")
            return True
        elif stat == 2:
            print("🔄 Still searching for network...")
            print("Waiting additional 30 seconds...")
            for i in range(30):
                time.sleep(1)
                print(".", end="", flush=True)
            print()
            
            response = send_command("AT+CREG?", 2)
            match = re.search(r'\+CREG:\s*(\d+),(\d+)', response)
            if match:
                new_stat = int(match.group(2))
                if new_stat in [1, 5]:
                    print("✅ Network registration successful after waiting!")
                    return True
    
    # Try manual network selection
    print("\n🔍 Scanning for available networks...")
    response = send_command("AT+COPS=?", 30, verbose=True)  # Scan networks (slow)
    
    # Try to extract and select the first available network
    if "+COPS:" in response:
        print("Available networks found. Trying manual selection...")
        # This is a simplified approach - in practice you'd parse the full response
        send_command("AT+COPS=1,2,\"64801\"", 10, verbose=True)  # MTC Namibia
        time.sleep(10)
        
        response = send_command("AT+CREG?", 2)
        match = re.search(r'\+CREG:\s*(\d+),(\d+)', response)
        if match:
            stat = int(match.group(2))
            if stat in [1, 5]:
                print("✅ Manual network registration successful!")
                return True
    
    print("❌ Network registration failed")
    print("💡 Possible issues:")
    print("   - SIM card not activated or has no credit")
    print("   - SIM card not compatible with this network")
    print("   - Antenna not connected properly")
    print("   - Signal too weak at this location")
    print("   - Network issues in your area")
    
    return False

def check_network_status():
    """Check network registration and signal"""
    print("\n📡 Checking network status...")
    
    print("Network registration:")
    response = send_command("AT+CREG?", 1, verbose=True)
    
    # Parse registration status
    match = re.search(r'\+CREG:\s*(\d+),(\d+)', response)
    if match:
        n = int(match.group(1))
        stat = int(match.group(2))
        
        stat_meanings = {
            0: "Not searching for new operator (disabled)",
            1: "Registered (home network)",
            2: "Not registered, but searching for new operator", 
            3: "Registration denied",
            4: "Unknown registration status",
            5: "Registered (roaming)"
        }
        
        status_text = stat_meanings.get(stat, f"Unknown status {stat}")
        print(f"📊 Registration status: {stat} - {status_text}")
        
        if stat not in [1, 5]:
            print("⚠️ Not registered to network - this will prevent SMS sending!")
            return False
    
    print("\nSignal strength:")
    response = send_command("AT+CSQ", 1, verbose=True)
    
    match = re.search(r'\+CSQ:\s*(\d+),(\d+)', response)
    if match:
        rssi = int(match.group(1))
        if rssi == 99:
            print("📶 No signal detected")
            return False
        elif rssi < 10:
            print(f"📶 Very weak signal: {rssi}")
        elif rssi < 15:
            print(f"📶 Weak signal: {rssi}")
        elif rssi < 20:
            print(f"📶 Good signal: {rssi}")
        else:
            print(f"📶 Excellent signal: {rssi}")
    
    print("\nOperator info:")
    send_command("AT+COPS?", 2, verbose=True)
    
    return True

def check_sms_settings():
    """Check current SMS notification settings"""
    print("\n🔍 Checking SMS settings...")
    
    print("SMS text mode:")
    send_command("AT+CMGF?", 1, verbose=True)
    
    print("\nSMS notification settings:")
    send_command("AT+CNMI?", 1, verbose=True)
    
    print("\nSMS storage settings:")
    send_command("AT+CPMS?", 1, verbose=True)
    
    print("\nSMS center:")
    send_command("AT+CSCA?", 1, verbose=True)
    
    print("\nCheck for stored SMS:")
    send_command('AT+CMGL="ALL"', 2, verbose=True)

def main():
    """Main function"""
    # Set up signal handler
    signal.signal(signal.SIGINT, cleanup)
    
    print("📱 SIM800L SMS Send/Receive Test (Verbose Mode)")
    print("=" * 60)
    
    try:
        # Initialize
        if not init_uart():
            return
        
        if not initialize_sms():
            return
        
        while running:
            print("\n" + "=" * 60)
            print("Select test:")
            print("1. Send test SMS")
            print("2. Wait for incoming SMS (5 minutes)")
            print("3. Wait for incoming SMS (custom time)")
            print("4. Send custom SMS")
            print("5. Check SMS settings and storage")
            print("6. Test SMS notifications setup")
            print("7. Check network status")
            print("8. Try to fix network registration")
            print("9. Reset GSM module")
            print("10. Hardware reset info")
            print("11. Exit")
            print("-" * 60)
            
            try:
                choice = input("Choice (1-11): ").strip()
                
                if choice == "1":
                    message = f"Test SMS from SIM800L at {datetime.now().strftime('%H:%M:%S')}"
                    send_sms(TEST_PHONE_NUMBER, message)
                
                elif choice == "2":
                    wait_for_sms(300)  # 5 minutes
                
                elif choice == "3":
                    try:
                        timeout = int(input("Enter timeout in seconds: "))
                        wait_for_sms(timeout)
                    except ValueError:
                        print("❌ Invalid number")
                
                elif choice == "4":
                    phone = input("Phone number (with country code): ").strip()
                    message = input("Message: ").strip()
                    if phone and message:
                        send_sms(phone, message)
                    else:
                        print("❌ Phone and message required")
                
                elif choice == "5":
                    check_sms_settings()
                
                elif choice == "6":
                    print("\n🔧 Re-configuring SMS notifications...")
                    send_command("AT+CMGF=1", 1, verbose=True)  # Text mode
                    send_command("AT+CNMI=1,2,0,0,0", 1, verbose=True)  # Enable notifications
                    send_command("AT+CNMI?", 1, verbose=True)  # Verify setting
                
                elif choice == "7":
                    check_network_status()
                
                elif choice == "8":
                    try_network_registration()
                
                elif choice == "9":
                    reset_gsm_module()
                
                elif choice == "10":
                    hardware_reset_info()
                
                elif choice == "11":
                    break
                
                else:
                    print("❌ Invalid choice")
                    
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"❌ Error: {e}")
    
    finally:
        cleanup()

if __name__ == "__main__":
    main()