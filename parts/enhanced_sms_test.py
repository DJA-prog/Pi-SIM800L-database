#!/usr/bin/env python3
"""
Enhanced SIM800L SMS Send/Receive Test Script
This script provides interactive testing for SMS functionality with real-time monitoring
"""

import os
import time
import pigpio
import re
import threading
import signal
import sys
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv('.env.server')

# Configuration from environment or defaults
RX_PIN = int(os.getenv('RX_PIN', 13))   # GPIO for SIM800L TX -> Pi RX
TX_PIN = int(os.getenv('TX_PIN', 12))   # GPIO for SIM800L RX <- Pi TX
BAUDRATE = int(os.getenv('BAUDRATE', 9600))
SIM_PIN = os.getenv('SIM_PIN', '9438')
TEST_PHONE_NUMBER = os.getenv('TEST_PHONE_NUMBER', '+264816828893')  # Set your phone number for testing

# Global variables
pi = None
uart_lock = threading.Lock()
running = True
sms_received_count = 0
message_buffer = ""

def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully"""
    global running
    print("\n\n🛑 Received interrupt signal. Shutting down gracefully...")
    running = False
    cleanup_pigpio()
    sys.exit(0)

def init_pigpio():
    """Initialize pigpio and configure pins"""
    global pi
    pi = pigpio.pi()
    if not pi.connected:
        raise RuntimeError("pigpio daemon not running. Run: sudo systemctl start pigpiod")
    
    # Configure pins
    pi.set_mode(RX_PIN, pigpio.INPUT)
    pi.set_mode(TX_PIN, pigpio.OUTPUT)
    pi.bb_serial_read_open(RX_PIN, BAUDRATE, 8)
    print(f"✓ Initialized pigpio - RX:{RX_PIN}, TX:{TX_PIN}, Baudrate:{BAUDRATE}")

def cleanup_pigpio():
    """Clean up pigpio resources"""
    if pi and pi.connected:
        pi.bb_serial_read_close(RX_PIN)
        pi.stop()
        print("✓ Cleaned up pigpio resources")

def flush_uart():
    """Clear out any old data in RX buffer."""
    count = 1
    while count > 0:
        count, data = pi.bb_serial_read(RX_PIN)
        if count > 0:
            print(f"[Flush] Cleared {count} bytes")

def uart_send(cmd):
    """Send AT command or raw string over TX_PIN."""
    pi.wave_clear()
    pi.wave_add_serial(TX_PIN, BAUDRATE, (cmd + "\r\n").encode())
    wid = pi.wave_create()
    pi.wave_send_once(wid)
    while pi.wave_tx_busy():
        time.sleep(0.01)
    pi.wave_delete(wid)

def uart_read(timeout=2):
    """Read whatever is in RX buffer with timeout."""
    response = ""
    deadline = time.time() + timeout
    
    while time.time() < deadline:
        count, data = pi.bb_serial_read(RX_PIN)
        if count:
            response += data.decode(errors="ignore")
        time.sleep(0.1)
    
    return response

def send_at(cmd, delay=1, timeout=5, verbose=True):
    """Send AT command and wait for response with thread-safe UART access."""
    with uart_lock:
        # Clear any existing data first
        flush_uart()
        
        # Send command
        if verbose:
            print(f">>> {cmd}")
        uart_send(cmd)
        time.sleep(delay)
        
        # Read response with timeout
        response = uart_read(timeout)
        if verbose:
            print(f"<<< {response.strip()}")
        return response

def setup_sms_mode():
    """Setup SMS text mode and other necessary settings"""
    print("🔧 Setting up SMS mode...")
    
    # Set SMS text mode
    response = send_at("AT+CMGF=1", delay=1)
    if "OK" not in response:
        print("✗ Failed to set SMS text mode")
        return False
    
    # Enable SMS notifications
    response = send_at("AT+CNMI=1,2,0,0,0", delay=1)
    if "OK" not in response:
        print("✗ Failed to enable SMS notifications")
        return False
    
    print("✓ SMS mode configured")
    return True

def check_network_status():
    """Check if device is ready for SMS operations"""
    print("📡 Checking network status...")
    
    # Check SIM status
    response = send_at("AT+CPIN?", delay=2, verbose=False)
    if "READY" not in response:
        if "SIM PIN" in response:
            print(f"🔐 Unlocking SIM with PIN...")
            pin_response = send_at(f"AT+CPIN={SIM_PIN}", delay=3, verbose=False)
            if "OK" not in pin_response:
                print("✗ Failed to unlock SIM")
                return False
            time.sleep(3)  # Wait for SIM to be ready
        else:
            print("✗ SIM not ready")
            return False
    
    # Check network registration
    response = send_at("AT+CREG?", delay=1, verbose=False)
    match = re.search(r'\+CREG:\s*\d+,(\d+)', response)
    if match:
        status = int(match.group(1))
        if status not in [1, 5]:  # Not registered
            print("✗ Not registered to network")
            return False
    else:
        print("✗ Could not check network registration")
        return False
    
    # Check signal strength
    response = send_at("AT+CSQ", delay=1, verbose=False)
    match = re.search(r'\+CSQ:\s*(\d+),', response)
    if match:
        signal = int(match.group(1))
        if signal == 99 or signal < 10:
            print(f"⚠️ Weak signal strength: {signal}")
        else:
            print(f"✓ Good signal strength: {signal}")
    
    print("✓ Network ready for SMS operations")
    return True

def send_test_sms(phone_number, message=None):
    """Send a test SMS message"""
    if not message:
        message = f"Test SMS from SIM800L at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    
    print(f"📤 Sending SMS to {phone_number}")
    print(f"Message: {message}")
    
    # Start SMS composition
    response = send_at(f'AT+CMGS="{phone_number}"', delay=1, timeout=10)
    
    if ">" in response:
        print("✓ SMS prompt received, sending message...")
        
        # Send message and end with Ctrl+Z (ASCII 26)
        with uart_lock:
            uart_send(message + chr(26))  # Ctrl+Z to send
            time.sleep(3)
            response = uart_read(timeout=15)
            print(f"<<< {response.strip()}")
        
        if "+CMGS:" in response and "OK" in response:
            print("✓ SMS sent successfully!")
            return True
        else:
            print("✗ SMS sending failed")
            print(f"Response: {response}")
            return False
    else:
        print("✗ Failed to get SMS prompt")
        print(f"Response: {response}")
        return False

def monitor_incoming_sms(duration=60):
    """Monitor for incoming SMS messages for specified duration"""
    global sms_received_count, message_buffer, running
    
    print(f"📥 Monitoring for incoming SMS messages for {duration} seconds...")
    print("💡 Send an SMS to this device now to test reception")
    print("⏹️  Press Ctrl+C to stop monitoring early")
    
    start_time = time.time()
    sms_received_count = 0
    
    try:
        while running and (time.time() - start_time) < duration:
            # Read any incoming data
            count, data = pi.bb_serial_read(RX_PIN)
            if count:
                message_buffer += data.decode(errors="ignore")
                
                # Check for SMS notification
                if "+CMTI:" in message_buffer:
                    sms_received_count += 1
                    print(f"\n🔔 SMS notification received! (Count: {sms_received_count})")
                    print(f"Raw notification: {message_buffer.strip()}")
                    
                    # Try to read the message
                    read_sms_from_notification(message_buffer)
                    message_buffer = ""  # Clear buffer
                
                # Check for direct SMS content (some configurations)
                elif "+CMT:" in message_buffer:
                    sms_received_count += 1
                    print(f"\n📨 Direct SMS received! (Count: {sms_received_count})")
                    print(f"Message data: {message_buffer.strip()}")
                    message_buffer = ""  # Clear buffer
            
            time.sleep(0.1)
    
    except KeyboardInterrupt:
        print("\n⏹️ Monitoring stopped by user")
    
    elapsed = time.time() - start_time
    print(f"\n📊 Monitoring completed:")
    print(f"   Duration: {elapsed:.1f} seconds")
    print(f"   SMS received: {sms_received_count}")
    
    return sms_received_count

def read_sms_from_notification(notification):
    """Extract and read SMS from notification"""
    # Parse +CMTI: "SM",index notification
    match = re.search(r'\+CMTI:\s*"([^"]*)",(\d+)', notification)
    if match:
        storage = match.group(1)
        index = match.group(2)
        print(f"📖 Reading SMS from {storage} index {index}")
        
        # Read the SMS
        response = send_at(f"AT+CMGR={index}", delay=1, timeout=5)
        print(f"📄 SMS Content:\n{response}")
        
        # Optionally delete the message to free storage
        delete_response = send_at(f"AT+CMGD={index}", delay=1, timeout=3, verbose=False)
        if "OK" in delete_response:
            print(f"🗑️ Deleted SMS from index {index}")

def interactive_menu():
    """Show interactive menu for testing"""
    while running:
        print("\n" + "="*60)
        print("📱 SIM800L SMS Test Menu")
        print("="*60)
        print("1. Send test SMS")
        print("2. Send custom SMS")
        print("3. Monitor for incoming SMS (60 seconds)")
        print("4. Monitor for incoming SMS (custom duration)")
        print("5. Check SMS storage status")
        print("6. Read all stored SMS")
        print("7. Delete all SMS")
        print("8. Network status check")
        print("9. Exit")
        print("-"*60)
        
        try:
            choice = input("Select option (1-9): ").strip()
            
            if choice == "1":
                send_test_sms(TEST_PHONE_NUMBER)
            
            elif choice == "2":
                phone = input("Enter phone number (with country code): ").strip()
                message = input("Enter message: ").strip()
                if phone and message:
                    send_test_sms(phone, message)
                else:
                    print("❌ Phone number and message required")
            
            elif choice == "3":
                monitor_incoming_sms(60)
            
            elif choice == "4":
                try:
                    duration = int(input("Enter monitoring duration (seconds): ").strip())
                    monitor_incoming_sms(duration)
                except ValueError:
                    print("❌ Invalid duration")
            
            elif choice == "5":
                check_sms_storage()
            
            elif choice == "6":
                read_all_sms()
            
            elif choice == "7":
                if input("Delete all SMS? (y/N): ").lower() == 'y':
                    delete_all_sms()
            
            elif choice == "8":
                check_network_status()
                
            elif choice == "9":
                print("👋 Exiting...")
                break
            
            else:
                print("❌ Invalid option")
                
        except KeyboardInterrupt:
            print("\n👋 Exiting...")
            break
        except Exception as e:
            print(f"❌ Error: {e}")

def check_sms_storage():
    """Check SMS storage information"""
    print("💾 Checking SMS storage...")
    response = send_at("AT+CPMS?", delay=1)
    print(f"Storage info: {response}")

def read_all_sms():
    """Read all stored SMS messages"""
    print("📖 Reading all stored SMS...")
    response = send_at('AT+CMGL="ALL"', delay=2, timeout=10)
    if "+CMGL:" in response:
        print("📄 Stored messages:")
        print(response)
    else:
        print("📭 No messages found")

def delete_all_sms():
    """Delete all SMS messages"""
    print("🗑️ Deleting all SMS...")
    response = send_at('AT+CMGD=1,4', delay=2)  # Delete all messages
    if "OK" in response:
        print("✓ All SMS deleted")
    else:
        print("✗ Failed to delete messages")

def main():
    """Main test function"""
    global running
    
    # Set up signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    
    print("🚀 SIM800L SMS Send/Receive Test")
    print("="*60)
    
    try:
        # Initialize
        init_pigpio()
        time.sleep(1)
        
        # Basic communication test
        print("🔌 Testing basic communication...")
        response = send_at("AT", delay=0.5)
        if "OK" not in response:
            print("❌ Basic communication failed!")
            return False
        print("✓ Basic communication OK")
        
        # Check network and setup
        if not check_network_status():
            print("❌ Network not ready!")
            return False
        
        if not setup_sms_mode():
            print("❌ SMS setup failed!")
            return False
        
        print("\n✅ SIM800L ready for SMS operations!")
        
        # Start interactive menu
        interactive_menu()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    
    finally:
        running = False
        cleanup_pigpio()
    
    return True

if __name__ == "__main__":
    main()