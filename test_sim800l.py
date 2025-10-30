#!/usr/bin/env python3
"""
SIM800L Test Script - Comprehensive SMS Send/Receive Testing
This script tests the SIM800L module for proper SMS functionality
including network registration, signal strength, and message handling.
"""

import os
import time
import pigpio
import re
import threading
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
test_results = {}

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
            print(f"[Flush] Cleared {count} bytes: {data[:50]}...")

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

def send_at(cmd, delay=1, timeout=5):
    """Send AT command and wait for response with thread-safe UART access."""
    with uart_lock:
        # Clear any existing data first
        flush_uart()
        
        # Send command
        print(f">>> {cmd}")
        uart_send(cmd)
        time.sleep(delay)
        
        # Read response with timeout
        response = uart_read(timeout)
        print(f"<<< {response.strip()}")
        return response

def test_basic_communication():
    """Test 1: Basic AT command communication"""
    print("\n" + "="*60)
    print("TEST 1: Basic Communication")
    print("="*60)
    
    # Test basic AT command
    response = send_at("AT", delay=0.5)
    if "OK" in response:
        print("✓ Basic AT communication working")
        test_results['basic_comm'] = True
        return True
    else:
        print("✗ Basic AT communication failed")
        print(f"Response: {repr(response)}")
        test_results['basic_comm'] = False
        return False

def test_sim_status():
    """Test 2: SIM card status and PIN"""
    print("\n" + "="*60)
    print("TEST 2: SIM Card Status")
    print("="*60)
    
    # Check SIM status
    response = send_at("AT+CPIN?", delay=2)
    
    if "READY" in response:
        print("✓ SIM card is ready (no PIN required or already unlocked)")
        test_results['sim_ready'] = True
        return True
    elif "SIM PIN" in response:
        print(f"⚠ SIM requires PIN. Attempting to unlock with PIN: {SIM_PIN}")
        pin_response = send_at(f"AT+CPIN={SIM_PIN}", delay=3)
        
        if "OK" in pin_response:
            print("✓ SIM PIN accepted")
            # Wait a bit then check status again
            time.sleep(2)
            check_response = send_at("AT+CPIN?", delay=2)
            if "READY" in check_response:
                print("✓ SIM is now ready")
                test_results['sim_ready'] = True
                return True
            else:
                print("✗ SIM still not ready after PIN")
                test_results['sim_ready'] = False
                return False
        else:
            print("✗ SIM PIN rejected")
            test_results['sim_ready'] = False
            return False
    else:
        print("✗ Unknown SIM status")
        print(f"Response: {repr(response)}")
        test_results['sim_ready'] = False
        return False

def test_network_registration():
    """Test 3: Network registration status"""
    print("\n" + "="*60)
    print("TEST 3: Network Registration")
    print("="*60)
    
    # Check network registration
    response = send_at("AT+CREG?", delay=2)
    
    # Parse +CREG: n,stat response
    match = re.search(r'\+CREG:\s*\d+,(\d+)', response)
    if match:
        status = int(match.group(1))
        status_meanings = {
            0: "Not searching for new operator (disabled)",
            1: "Registered (home network)",
            2: "Not registered, but searching for new operator",
            3: "Registration denied",
            4: "Unknown registration status",
            5: "Registered (roaming)"
        }
        
        status_text = status_meanings.get(status, f"Unknown status {status}")
        print(f"Network registration status: {status} - {status_text}")
        
        if status in [1, 5]:  # Registered
            print("✓ Network registration successful")
            test_results['network_registered'] = True
            return True
        else:
            print("✗ Not registered to network")
            test_results['network_registered'] = False
            return False
    else:
        print("✗ Could not parse network registration response")
        print(f"Response: {repr(response)}")
        test_results['network_registered'] = False
        return False

def test_signal_strength():
    """Test 4: Signal strength"""
    print("\n" + "="*60)
    print("TEST 4: Signal Strength")
    print("="*60)
    
    response = send_at("AT+CSQ", delay=2)
    
    # Parse +CSQ: rssi,ber response
    match = re.search(r'\+CSQ:\s*(\d+),(\d+)', response)
    if match:
        rssi = int(match.group(1))
        ber = int(match.group(2))
        
        if rssi == 99:
            print("✗ Signal not detectable (RSSI: 99)")
            test_results['signal_strength'] = False
            return False
        else:
            # Convert RSSI to dBm: -113 + (rssi * 2)
            dbm = -113 + (rssi * 2)
            
            if rssi >= 10:  # Good signal
                signal_quality = "Excellent" if rssi >= 20 else "Good"
                print(f"✓ {signal_quality} signal strength: RSSI {rssi} ({dbm} dBm)")
                test_results['signal_strength'] = True
                return True
            elif rssi >= 5:
                print(f"⚠ Weak signal: RSSI {rssi} ({dbm} dBm)")
                test_results['signal_strength'] = True
                return True
            else:
                print(f"✗ Very weak signal: RSSI {rssi} ({dbm} dBm)")
                test_results['signal_strength'] = False
                return False
    else:
        print("✗ Could not parse signal strength response")
        print(f"Response: {repr(response)}")
        test_results['signal_strength'] = False
        return False

def test_sms_mode_setup():
    """Test 5: SMS mode configuration"""
    print("\n" + "="*60)
    print("TEST 5: SMS Mode Configuration")
    print("="*60)
    
    # Set SMS text mode
    response1 = send_at("AT+CMGF=1", delay=1)
    if "OK" not in response1:
        print("✗ Failed to set SMS text mode")
        test_results['sms_mode'] = False
        return False
    
    print("✓ SMS text mode enabled")
    
    # Configure new SMS indication
    response2 = send_at("AT+CNMI=2,2,0,0,0", delay=2)
    if "OK" not in response2:
        print("✗ Failed to configure SMS notification")
        test_results['sms_mode'] = False
        return False
    
    print("✓ SMS notifications configured (direct to serial)")
    test_results['sms_mode'] = True
    return True

def test_sms_storage_info():
    """Test 6: SMS storage information"""
    print("\n" + "="*60)
    print("TEST 6: SMS Storage Information")
    print("="*60)
    
    # Check preferred message storage
    response1 = send_at("AT+CPMS?", delay=2)
    print(f"Current message storage: {response1.strip()}")
    
    # List all messages
    response2 = send_at("AT+CMGL=\"ALL\"", delay=3, timeout=10)
    
    # Count messages
    message_count = response2.count('+CMGL:')
    print(f"Messages in storage: {message_count}")
    
    if message_count > 0:
        print("📨 Found existing messages:")
        lines = response2.split('\n')
        for i, line in enumerate(lines):
            if '+CMGL:' in line:
                print(f"  {line.strip()}")
                # Print the message content (usually next line)
                if i + 1 < len(lines):
                    content = lines[i + 1].strip()
                    if content and not content.startswith('AT') and not content.startswith('+'):
                        print(f"    Content: {content}")
    
    test_results['sms_storage'] = True
    return True

def send_test_sms(phone_number):
    """Test 7: Send test SMS"""
    print("\n" + "="*60)
    print("TEST 7: Send Test SMS")
    print("="*60)
    
    if not phone_number or phone_number == '+1234567890':
        print("⚠ No valid test phone number configured")
        print("Set TEST_PHONE_NUMBER in .env.server file to test SMS sending")
        test_results['sms_send'] = 'skipped'
        return False
    
    print(f"Sending test SMS to {phone_number}")
    
    # Initiate SMS send
    response1 = send_at(f"AT+CMGS=\"{phone_number}\"", delay=2)
    
    if ">" not in response1:
        print("✗ Failed to initiate SMS send")
        print(f"Response: {repr(response1)}")
        test_results['sms_send'] = False
        return False
    
    print("✓ SMS prompt received, sending message...")
    
    # Send message content and Ctrl+Z
    test_message = f"SIM800L Test Message - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    message_with_ctrlz = test_message + chr(26)  # Ctrl+Z to end message
    
    with uart_lock:
        flush_uart()
        uart_send(message_with_ctrlz[:-1])  # Send without \r\n
        pi.wave_clear()
        pi.wave_add_serial(TX_PIN, BAUDRATE, chr(26).encode())
        wid = pi.wave_create()
        pi.wave_send_once(wid)
        while pi.wave_tx_busy():
            time.sleep(0.01)
        pi.wave_delete(wid)
        
        # Wait for response (SMS sending can take time)
        response2 = uart_read(timeout=30)
    
    print(f"Send response: {repr(response2)}")
    
    if "+CMGS:" in response2 and "OK" in response2:
        print("✓ SMS sent successfully!")
        test_results['sms_send'] = True
        return True
    elif "ERROR" in response2:
        print("✗ SMS send failed")
        test_results['sms_send'] = False
        return False
    else:
        print("⚠ SMS send status unclear")
        test_results['sms_send'] = 'unclear'
        return False

def test_receive_mode():
    """Test 8: SMS receive mode test"""
    print("\n" + "="*60)
    print("TEST 8: SMS Receive Mode Test")
    print("="*60)
    
    print("📱 SMS receive test active for 30 seconds...")
    print("   Send an SMS to this SIM card now to test reception")
    print("   Monitoring for incoming messages...")
    
    start_time = time.time()
    received_messages = 0
    
    with uart_lock:
        flush_uart()
    
    while time.time() - start_time < 30:  # Monitor for 30 seconds
        with uart_lock:
            count, data = pi.bb_serial_read(RX_PIN)
            if count > 0:
                message = data.decode(errors='ignore')
                print(f"[Raw] {repr(message)}")
                
                # Look for SMS indicators
                if '+CMTI:' in message:  # SMS received indication
                    print("✓ SMS received indication detected!")
                    received_messages += 1
                elif '+CMT:' in message:  # Direct SMS content
                    print("✓ Direct SMS content received!")
                    received_messages += 1
                    
        time.sleep(0.5)
        print(".", end="", flush=True)
    
    print()  # New line after dots
    
    if received_messages > 0:
        print(f"✓ Received {received_messages} SMS indication(s)")
        test_results['sms_receive'] = True
        return True
    else:
        print("✗ No SMS received during test period")
        print("  This could mean:")
        print("  - No SMS was sent to this number")
        print("  - SMS notification is not working properly")
        print("  - Network/carrier issues")
        test_results['sms_receive'] = False
        return False

def test_stored_messages():
    """Test 9: Read stored messages"""
    print("\n" + "="*60)
    print("TEST 9: Read Stored Messages")
    print("="*60)
    
    # Read all messages
    response = send_at("AT+CMGL=\"ALL\"", delay=3, timeout=15)
    
    messages = []
    lines = response.split('\n')
    
    current_message = None
    for line in lines:
        line = line.strip()
        if '+CMGL:' in line:
            if current_message:
                messages.append(current_message)
            
            # Parse message header
            match = re.search(r'\+CMGL:\s*(\d+),"([^"]+)","([^"]+)",[^,]*,"([^"]+)"', line)
            if match:
                current_message = {
                    'index': match.group(1),
                    'status': match.group(2), 
                    'sender': match.group(3),
                    'timestamp': match.group(4),
                    'content': ''
                }
        elif current_message and line and not line.startswith('AT') and not line.startswith('+'):
            current_message['content'] = line
    
    if current_message:
        messages.append(current_message)
    
    print(f"Found {len(messages)} stored message(s):")
    for msg in messages:
        print(f"  [{msg['index']}] From: {msg['sender']}")
        print(f"      Status: {msg['status']}")
        print(f"      Time: {msg['timestamp']}")
        print(f"      Content: {msg['content']}")
        print()
    
    test_results['stored_messages'] = len(messages)
    return len(messages) > 0

def run_diagnostic_tests():
    """Run comprehensive SIM800L diagnostics"""
    print("🔧 SIM800L Comprehensive Test Suite")
    print(f"Configuration: RX={RX_PIN}, TX={TX_PIN}, Baud={BAUDRATE}")
    print(f"Test phone number: {TEST_PHONE_NUMBER}")
    
    try:
        init_pigpio()
        
        # Run all tests
        tests = [
            test_basic_communication,
            test_sim_status,
            test_network_registration, 
            test_signal_strength,
            test_sms_mode_setup,
            test_sms_storage_info,
            lambda: send_test_sms(TEST_PHONE_NUMBER),
            test_receive_mode,
            test_stored_messages
        ]
        
        passed = 0
        failed = 0
        
        for test in tests:
            try:
                if test():
                    passed += 1
                else:
                    failed += 1
            except Exception as e:
                print(f"✗ Test failed with exception: {e}")
                failed += 1
            
            time.sleep(1)  # Brief pause between tests
        
        # Print summary
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)
        print(f"Tests passed: {passed}")
        print(f"Tests failed: {failed}")
        print(f"Success rate: {passed/(passed+failed)*100:.1f}%")
        
        print("\nDetailed Results:")
        for test_name, result in test_results.items():
            status = "✓ PASS" if result else "✗ FAIL" if result is False else f"⚠ {result}"
            print(f"  {test_name:<20}: {status}")
        
        print("\nTroubleshooting Tips:")
        if not test_results.get('basic_comm', False):
            print("- Check wiring: SIM800L TX -> Pi GPIO13, SIM800L RX -> Pi GPIO12")
            print("- Verify pigpio daemon is running: sudo systemctl start pigpiod")
            print("- Check power supply (SIM800L needs stable 3.7-4.2V)")
        
        if not test_results.get('sim_ready', False):
            print("- Verify SIM card is inserted properly")
            print("- Check SIM PIN is correct in .env.server")
            print("- Try a different SIM card")
        
        if not test_results.get('network_registered', False):
            print("- Check SIM card has active service")
            print("- Verify you're in an area with network coverage")
            print("- Try waiting longer for network registration")
        
        if not test_results.get('sms_receive', False):
            print("- Make sure someone actually sent an SMS during the test")
            print("- Check that SMS notifications are properly configured")
            print("- Verify the SIM card number and network settings")
            
    except Exception as e:
        print(f"Test suite failed: {e}")
    finally:
        cleanup_pigpio()

def interactive_mode():
    """Interactive mode for manual testing"""
    print("\n" + "="*60)
    print("INTERACTIVE MODE")
    print("="*60)
    print("Enter AT commands manually (or 'quit' to exit)")
    
    try:
        init_pigpio()
        
        while True:
            cmd = input("\nAT> ").strip()
            if cmd.lower() in ['quit', 'exit', 'q']:
                break
            
            if cmd:
                if not cmd.upper().startswith('AT'):
                    cmd = 'AT' + cmd
                
                response = send_at(cmd, delay=2)
                print(f"Response: {repr(response)}")
                
    except KeyboardInterrupt:
        print("\nExiting interactive mode...")
    except Exception as e:
        print(f"Interactive mode error: {e}")
    finally:
        cleanup_pigpio()

def main():
    """Main function"""
    print("SIM800L Test Utility")
    print("Select test mode:")
    print("1. Full diagnostic test suite")
    print("2. Interactive AT command mode")
    print("3. Quick SMS send test") 
    print("4. SMS receive monitor")
    
    try:
        choice = input("\nEnter choice (1-4): ").strip()
        
        if choice == '1':
            run_diagnostic_tests()
        elif choice == '2':
            interactive_mode()
        elif choice == '3':
            init_pigpio()
            try:
                phone = input("Enter phone number (+1234567890): ").strip()
                if phone:
                    send_test_sms(phone)
            finally:
                cleanup_pigpio()
        elif choice == '4':
            init_pigpio()
            try:
                print("Monitoring for SMS (30 seconds)...")
                test_receive_mode()
            finally:
                cleanup_pigpio()
        else:
            print("Invalid choice")
            
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
