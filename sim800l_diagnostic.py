#!/usr/bin/env python3
"""
SIM800L Network Diagnostic Script
Helps diagnose network registration and SMS issues
"""

import os
import time
import pigpio
import re
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv('.env.server')

# Configuration
RX_PIN = int(os.getenv('RX_PIN', 13))
TX_PIN = int(os.getenv('TX_PIN', 12))
BAUDRATE = int(os.getenv('BAUDRATE', 9600))
SIM_PIN = os.getenv('SIM_PIN', '9438')

# Global variables
pi = None

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

def cleanup():
    """Clean up resources"""
    global pi
    if pi and pi.connected:
        pi.bb_serial_read_close(RX_PIN)
        pi.stop()
    print("✓ Cleanup completed")

def send_command(cmd, wait_time=2, timeout=10):
    """Send AT command and get response"""
    # Clear buffer first
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
    
    # Wait and read response
    time.sleep(wait_time)
    response = ""
    deadline = time.time() + timeout
    while time.time() < deadline:
        count, data = pi.bb_serial_read(RX_PIN)
        if count:
            response += data.decode(errors="ignore")
        time.sleep(0.1)
    
    print(f"<<< {response.strip()}")
    return response

def test_basic_commands():
    """Test basic AT commands"""
    print("\n🔧 Testing Basic Commands")
    print("=" * 50)
    
    # Basic communication
    response = send_command("AT")
    if "OK" not in response:
        print("❌ Basic AT command failed")
        return False
    print("✓ Basic communication OK")
    
    # Get module info
    print("\n📋 Module Information:")
    send_command("ATI")  # Module identification
    send_command("AT+GMM")  # Model
    send_command("AT+GMR")  # Firmware version
    send_command("AT+GSN")  # IMEI
    
    return True

def test_sim_card():
    """Test SIM card status and operations"""
    print("\n🔐 Testing SIM Card")
    print("=" * 50)
    
    # Check SIM status
    response = send_command("AT+CPIN?", 2)
    if "READY" in response:
        print("✓ SIM card is ready")
    elif "SIM PIN" in response:
        print("🔐 SIM requires PIN, attempting unlock...")
        response = send_command(f"AT+CPIN={SIM_PIN}", 3)
        if "OK" in response:
            print("✓ SIM PIN accepted")
            time.sleep(3)  # Wait for SIM to initialize
            response = send_command("AT+CPIN?", 2)
            if "READY" in response:
                print("✓ SIM is now ready")
            else:
                print("❌ SIM still not ready after PIN")
                return False
        else:
            print("❌ SIM PIN rejected")
            return False
    else:
        print("❌ SIM card issue")
        print(f"Response: {response}")
        return False
    
    # Get SIM info
    print("\n📱 SIM Information:")
    send_command("AT+CIMI")  # IMSI
    send_command("AT+CCID")  # SIM card ID
    send_command("AT+CNUM")  # Own phone number (if available)
    
    return True

def test_network_registration():
    """Test network registration in detail"""
    print("\n📡 Testing Network Registration")
    print("=" * 50)
    
    # Check current registration status
    response = send_command("AT+CREG?", 2)
    print("Current registration status:")
    
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
        
        print(f"  n={n}, stat={stat}")
        print(f"  Status: {stat_meanings.get(stat, 'Unknown')}")
        
        if stat in [1, 5]:
            print("✓ Network registered")
        elif stat == 2:
            print("⏳ Searching for network...")
            # Wait and check again
            print("Waiting 30 seconds for registration...")
            for i in range(30):
                time.sleep(1)
                print(f".", end="", flush=True)
            print()
            
            response = send_command("AT+CREG?", 2)
            match = re.search(r'\+CREG:\s*(\d+),(\d+)', response)
            if match:
                new_stat = int(match.group(2))
                print(f"New status: {stat_meanings.get(new_stat, 'Unknown')}")
                if new_stat in [1, 5]:
                    print("✓ Network registered after waiting")
                    return True
            print("❌ Still not registered")
            return False
        else:
            print("❌ Registration failed or denied")
            return False
    else:
        print("❌ Could not parse registration response")
        return False
    
    return True

def test_network_info():
    """Get detailed network information"""
    print("\n🌐 Network Information")
    print("=" * 50)
    
    # Signal strength
    response = send_command("AT+CSQ", 1)
    match = re.search(r'\+CSQ:\s*(\d+),(\d+)', response)
    if match:
        rssi = int(match.group(1))
        ber = int(match.group(2))
        
        if rssi == 99:
            print("❌ No signal detected")
        elif rssi < 10:
            print(f"📶 Very weak signal: {rssi} (-113 to -109 dBm)")
        elif rssi < 15:
            print(f"📶 Weak signal: {rssi} (-109 to -98 dBm)")
        elif rssi < 20:
            print(f"📶 Good signal: {rssi} (-98 to -88 dBm)")
        else:
            print(f"📶 Excellent signal: {rssi} (-88+ dBm)")
        
        print(f"  RSSI: {rssi}, BER: {ber}")
    
    # Operator information
    print("\n📡 Operator Information:")
    send_command("AT+COPS?", 3)  # Current operator
    send_command("AT+COPS=?", 10)  # Available operators (takes time)

def test_sms_capabilities():
    """Test SMS-specific capabilities"""
    print("\n💬 Testing SMS Capabilities")
    print("=" * 50)
    
    # Set text mode
    response = send_command("AT+CMGF=1", 1)
    if "OK" in response:
        print("✓ SMS text mode set")
    else:
        print("❌ Failed to set SMS text mode")
        return False
    
    # Check SMS center number
    response = send_command("AT+CSCA?", 2)
    if "+CSCA:" in response:
        print("✓ SMS center configured")
        print(f"  {response.strip()}")
    else:
        print("❌ SMS center not configured")
        print("This might be why SMS sending fails!")
    
    # Check SMS storage
    send_command("AT+CPMS?", 2)  # SMS storage info
    
    # Try to get network-provided SMS center
    print("\nTrying to get SMS center from network...")
    send_command("AT+CSCA?", 2)
    
    return True

def try_sms_center_fix():
    """Try common SMS center numbers for different regions"""
    print("\n🔧 Trying SMS Center Fix")
    print("=" * 50)
    
    # Common SMS centers (you may need to find your carrier's specific one)
    sms_centers = [
        '"+264811000100"',  # MTC Namibia
        '"+264850000100"',  # TN Mobile Namibia  
        '"+27831000100"',   # Common South Africa
        '"+27821000100"',   # Alternative SA
    ]
    
    print("Trying common SMS center numbers...")
    for center in sms_centers:
        print(f"Trying SMS center: {center}")
        response = send_command(f"AT+CSCA={center}", 2)
        if "OK" in response:
            print(f"✓ SMS center set to {center}")
            # Verify it was set
            verify = send_command("AT+CSCA?", 1)
            print(f"Verification: {verify.strip()}")
            return True
        else:
            print(f"❌ Failed to set {center}")
    
    print("❌ Could not set any SMS center automatically")
    print("💡 You may need to contact your carrier for the correct SMS center number")
    return False

def main():
    """Main diagnostic function"""
    print("🔍 SIM800L Network Diagnostic Tool")
    print("=" * 60)
    
    try:
        if not init_uart():
            return
        
        # Run all diagnostic tests
        print("Running comprehensive diagnostics...\n")
        
        if not test_basic_commands():
            print("❌ Basic communication failed - check wiring")
            return
        
        if not test_sim_card():
            print("❌ SIM card issues detected")
            return
        
        network_ok = test_network_registration()
        test_network_info()
        
        sms_ok = test_sms_capabilities()
        
        if not sms_ok:
            print("\n🔧 SMS issues detected, trying fixes...")
            try_sms_center_fix()
        
        # Summary
        print("\n" + "=" * 60)
        print("📊 DIAGNOSTIC SUMMARY")
        print("=" * 60)
        print(f"✓ Basic communication: OK")
        print(f"✓ SIM card: OK")
        print(f"{'✓' if network_ok else '❌'} Network registration: {'OK' if network_ok else 'FAILED'}")
        print(f"{'✓' if sms_ok else '❌'} SMS capabilities: {'OK' if sms_ok else 'NEEDS ATTENTION'}")
        
        if network_ok and sms_ok:
            print("\n🎉 All tests passed! SMS should work now.")
        else:
            print("\n⚠️ Issues detected. See output above for details.")
            if not network_ok:
                print("💡 Network registration tips:")
                print("   - Check antenna connection")
                print("   - Verify SIM card has credit/active plan")
                print("   - Try different location for better signal")
                print("   - Contact carrier about network issues")
            
            if not sms_ok:
                print("💡 SMS tips:")
                print("   - Contact carrier for correct SMS center number")
                print("   - Verify SMS service is enabled on your plan")
    
    except Exception as e:
        print(f"❌ Error during diagnostics: {e}")
    
    finally:
        cleanup()

if __name__ == "__main__":
    main()