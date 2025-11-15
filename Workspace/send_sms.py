#!/usr/bin/env python3
"""
SIM800L GSM Module SMS Sender for Raspberry Pi Zero W
Complete test suite: CPIN check, network connection, SMS sending
"""

import os
import time
import pigpio
import logging
import threading
import re
from datetime import datetime

# Configuration from environment variables
RX_PIN = int(os.getenv('RX_PIN', 13))   # GPIO for SIM800L TX -> Pi RX
TX_PIN = int(os.getenv('TX_PIN', 12))   # GPIO for SIM800L RX <- Pi TX
BAUDRATE = int(os.getenv('BAUDRATE', 9600))
SIM_PIN = os.getenv('SIM_PIN', '9438')

# Pigpio configuration
TIMEOUT = 10  # Command timeout in seconds

# Test phone number (replace with actual number for testing)
TEST_PHONE_NUMBER = os.getenv('TEST_PHONE_NUMBER', '+264816828893')

# Debug configuration
SHOW_RAW_DEBUG = os.getenv('SHOW_RAW_DEBUG', 'true').lower() == 'true'  # Set to False to disable raw output

# Global pigpio instance
pi = None
uart_lock = threading.Lock()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/sms_test.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


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
    logger.info(f"✓ Initialized pigpio - RX:{RX_PIN}, TX:{TX_PIN}, Baudrate:{BAUDRATE}")
    return pi


def cleanup_pigpio():
    """Cleanup pigpio resources"""
    global pi
    if pi and pi.connected:
        try:
            pi.bb_serial_read_close(RX_PIN)
            pi.stop()
            logger.info("✓ pigpio cleanup completed")
        except Exception as e:
            logger.warning(f"pigpio cleanup warning: {e}")


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
    """Read whatever is in RX buffer with timeout and immediate response detection."""
    response = ""
    deadline = time.time() + timeout
    last_data_time = 0
    trailing_delay = 0.05  # 50ms delay after last data received
    
    while time.time() < deadline:
        count, data = pi.bb_serial_read(RX_PIN)
        if count:
            response += data.decode(errors="ignore")
            last_data_time = time.time()
            
            # Check for common response terminators
            if any(terminator in response for terminator in ['\nOK\r\n', '\nERROR\r\n', '\n> ']):
                # Wait a short time for any trailing data
                time.sleep(trailing_delay)
                # Read any final trailing data
                count, data = pi.bb_serial_read(RX_PIN)
                if count:
                    response += data.decode(errors="ignore")
                break
        else:
            # If we have data and haven't received anything new for trailing_delay, we're probably done
            if response and last_data_time > 0 and (time.time() - last_data_time) > trailing_delay:
                break
        
        time.sleep(0.01)  # Shorter polling interval
    
    return response


def send_at(cmd, delay=0.1, timeout=5):
    """Send AT command and wait for response with thread-safe UART access."""
    with uart_lock:
        # Clear any existing data first
        flush_uart()
        
        # Send command
        print(f"RAW SEND: {repr(cmd + chr(13) + chr(10))}")
        print(f"RAW SEND HEX: {(cmd + chr(13) + chr(10)).encode().hex()}")
        uart_send(cmd)
        time.sleep(delay)  # Reduced default delay
        
        # Read response with timeout
        response = uart_read(timeout)
        print(f"RAW RECEIVE: {repr(response)}")
        print(f"RAW RECEIVE HEX: {response.encode().hex()}")
        print(f"DECODED RESPONSE: {response.strip()}")
        return response


class SIM800L:
    """SIM800L GSM module controller using pigpio bit-banging"""
    
    def __init__(self, rx_pin=RX_PIN, tx_pin=TX_PIN, baudrate=BAUDRATE, timeout=TIMEOUT):
        self.rx_pin = rx_pin
        self.tx_pin = tx_pin
        self.baudrate = baudrate
        self.timeout = timeout
        self.pi = None
        
    def connect(self):
        """Initialize pigpio connection to SIM800L"""
        try:
            self.pi = init_pigpio()
            logger.info(f"Connected to SIM800L via GPIO pins RX:{self.rx_pin}, TX:{self.tx_pin}")
            time.sleep(2)  # Wait for connection to stabilize
            return True
        except Exception as e:
            logger.error(f"Failed to initialize pigpio: {e}")
            return False
    
    def send_command(self, command, wait_time=0.1, expected_response="OK", timeout=None):
        """Send AT command using improved UART handling with optimized timing"""
        if not self.pi or not self.pi.connected:
            logger.error("Pigpio connection not available")
            return False, ""
        
        try:
            # Use command-specific timeout if not provided
            if timeout is None:
                # Set timeouts based on command type
                if command.startswith("AT+COPS="):
                    timeout = 15  # Network selection takes time
                elif command.startswith("AT+CFUN="):
                    timeout = 8   # Functionality changes take time
                elif command.startswith("AT+CPIN="):
                    timeout = 5   # PIN unlock can take time
                elif "?" in command:
                    timeout = 3   # Query commands are usually fast
                else:
                    timeout = 2   # Default for most commands
            
            response = send_at(command, delay=wait_time, timeout=timeout)
            success = expected_response in response if expected_response else True
            logger.debug(f"Command: {command}, Success: {success}")
            return success, response.strip()
            
        except Exception as e:
            logger.error(f"Error sending command '{command}': {e}")
            return False, ""
    
    def test_basic_communication(self):
        """Test basic AT communication with enhanced debugging"""
        logger.info("Testing basic AT communication...")
        
        # Try multiple approaches to establish communication
        for attempt in range(3):
            logger.info(f"Communication attempt {attempt + 1}/3...")
            
            # First try a simple AT
            success, response = self.send_command("AT", 1, "OK")
            if success:
                logger.info("✓ Basic AT communication successful")
                return True
            
            # If no response, try some recovery steps
            if not response.strip():
                logger.warning(f"No response on attempt {attempt + 1}, trying recovery...")
                
                # Try different timing
                success, response = self.send_command("AT", 2, "OK")
                if success:
                    logger.info("✓ Basic AT communication successful (slower timing)")
                    return True
                
                # Try sending multiple ATs to wake up the module
                logger.info("Trying to wake up module with multiple AT commands...")
                with uart_lock:
                    flush_uart()
                    for i in range(3):
                        uart_send("AT")
                        time.sleep(0.5)
                    
                    # Read any response
                    response = uart_read(timeout=3)
                    print(f"Wake-up response: {repr(response)}")
                    if "OK" in response:
                        logger.info("✓ Module responded after wake-up sequence")
                        return True
                
                # Try autobaud detection
                logger.info("Trying autobaud detection...")
                with uart_lock:
                    flush_uart()
                    # Send "AT" multiple times at different speeds (conceptually)
                    for i in range(5):
                        uart_send("AT")
                        time.sleep(0.1)
                    
                    response = uart_read(timeout=3)
                    print(f"Autobaud response: {repr(response)}")
                    if "OK" in response:
                        logger.info("✓ Module responded after autobaud")
                        return True
            
            time.sleep(2)  # Wait between attempts
        
        logger.error("✗ Basic AT communication failed after all attempts")
        logger.error("Troubleshooting tips:")
        logger.error("- Check wiring: SIM800L TX -> Pi GPIO13, SIM800L RX -> Pi GPIO12")
        logger.error("- Verify SIM800L power (needs stable 3.7-4.2V, high current)")
        logger.error("- Check if SIM800L power LED is on")
        logger.error("- Try different baud rate (9600, 115200)")
        logger.error("- Verify pigpio daemon is running: sudo systemctl status pigpiod")
        return False
    
    def hardware_diagnostic(self):
        """Run hardware diagnostic checks"""
        logger.info("Running hardware diagnostic...")
        
        # Check GPIO pin states
        try:
            rx_level = self.pi.read(RX_PIN)
            tx_level = self.pi.read(TX_PIN)
            logger.info(f"GPIO states - RX pin {RX_PIN}: {rx_level}, TX pin {TX_PIN}: {tx_level}")
            
            # TX should be high when idle, RX state varies
            if tx_level == 0:
                logger.warning("TX pin is LOW - should be HIGH when idle")
            
        except Exception as e:
            logger.error(f"Cannot read GPIO states: {e}")
        
        # Test if we can send data (even without response)
        logger.info("Testing TX transmission capability...")
        try:
            with uart_lock:
                flush_uart()
                uart_send("AT")
                # Just verify the send worked without checking response
                logger.info("✓ TX transmission completed")
        except Exception as e:
            logger.error(f"✗ TX transmission failed: {e}")
            return False
        
        # Check if we're receiving any data at all
        logger.info("Listening for any RX data (5 seconds)...")
        with uart_lock:
            flush_uart()
            time.sleep(1)
            
            total_data = ""
            for i in range(50):  # 5 seconds of listening
                count, data = self.pi.bb_serial_read(RX_PIN)
                if count > 0:
                    chunk = data.decode(errors='ignore')
                    total_data += chunk
                    print(f"[RX] Received {count} bytes: {repr(chunk)}")
                time.sleep(0.1)
            
            if total_data:
                logger.info(f"✓ Received data: {repr(total_data)}")
                return True
            else:
                logger.warning("✗ No data received on RX pin")
                return False
    
    def check_cpin(self):
        """Check SIM card PIN status"""
        logger.info("Checking SIM card PIN status...")
        success, response = self.send_command("AT+CPIN?", 0.1)
        
        if "READY" in response:
            logger.info("✓ SIM card is ready (no PIN required)")
            return True
        elif "SIM PIN" in response:
            logger.info("SIM card requires PIN, attempting to unlock...")
            return self.unlock_sim()
        else:
            logger.error(f"✗ SIM card error: {response}")
            return False
    
    def unlock_sim(self):
        """Unlock SIM card with PIN"""
        if not SIM_PIN:
            logger.error("No SIM PIN provided in environment variables")
            return False
        
        logger.info(f"Attempting to unlock SIM with PIN: {SIM_PIN}")
        success, response = self.send_command(f"AT+CPIN={SIM_PIN}", 0.1)
        
        if success:
            logger.info("✓ SIM unlocked successfully")
            time.sleep(2)  # Reduced wait time after unlock
        else:
            logger.error(f"✗ Failed to unlock SIM: {response}")
        
        return success
    
    def check_network_registration(self):
        """Check network registration status"""
        logger.info("Checking network registration...")
        
        # Run some diagnostic commands first
        logger.info("Running network diagnostics...")
        
        # Check if antenna is detected
        self.send_command("AT+CSQ", 0.1)  # Signal quality
        
        # Check current operator and ensure automatic selection
        success, cops_response = self.send_command("AT+COPS?", 0.1)  # Current operator
        
        # Always set to automatic operator selection for best results
        if "+COPS:" in cops_response:
            logger.info(f"Current operator mode: {cops_response.strip()}")
            if not "+COPS: 0" in cops_response:  # If not already in automatic mode
                logger.info("Setting to automatic network selection (recommended)...")
                self.send_command("AT+COPS=0", 15)  # Automatic network selection
                time.sleep(5)
                success, new_cops = self.send_command("AT+COPS?", 2)
                if success:
                    logger.info(f"Updated operator mode: {new_cops.strip()}")
            else:
                logger.info("✓ Already in automatic network selection mode")
        else:
            logger.warning("Could not determine operator mode, setting to automatic...")
            self.send_command("AT+COPS=0", 15)  # Set to automatic anyway
        
        # Check SIM card service status
        self.send_command("AT+CIMI", 2)  # International Mobile Subscriber Identity
        
        # Check if module is in airplane mode or has restrictions
        self.send_command("AT+CFUN?", 2)  # Phone functionality
        
        # Make sure module is in full functionality mode
        logger.info("Ensuring full functionality mode...")
        self.send_command("AT+CFUN=1", 5)  # Enable full functionality
        
        # Wait for module to reinitialize network components
        time.sleep(3)
        
        # Check if network registration started automatically
        success, initial_creg = self.send_command("AT+CREG?", 2)
        if "+CREG:" in initial_creg:
            logger.info(f"Initial registration status after CFUN=1: {initial_creg.strip()}")
            # If status is already searching (status=2) or registered (status=1,5), we might not need more commands
            if "+CREG: 1,1" in initial_creg or "+CREG: 1,5" in initial_creg:
                logger.info("✓ Already registered after enabling full functionality!")
                return True
            elif "+CREG: 1,2" in initial_creg:
                logger.info("Already searching for network after enabling full functionality")
                # Continue to monitoring loop below
        
        # First enable network registration
        logger.info("Enabling network registration...")
        success, response = self.send_command("AT+CREG=1", 2)
        if not success:
            logger.warning("Failed to enable network registration, continuing anyway...")
        else:
            logger.info("✓ Network registration enabled")
            time.sleep(3)  # Wait for registration to start
        
        # Check registration status
        for attempt in range(30):  # Wait up to 30 seconds
            success, response = self.send_command("AT+CREG?", 1)
            
            if "+CREG:" in response:
                # Parse registration status - extract just the +CREG line
                creg_line = ""
                for line in response.split('\n'):
                    if '+CREG:' in line:
                        creg_line = line.strip()
                        break
                
                if creg_line:
                    # Parse the +CREG: n,stat response
                    match = re.search(r'\+CREG:\s*(\d+),(\d+)', creg_line)
                    if match:
                        n = match.group(1)
                        status = match.group(2)
                        
                        status_meanings = {
                            "0": "Not registered, not searching",
                            "1": "Registered (home network)",
                            "2": "Not registered, searching for operator",
                            "3": "Registration denied",
                            "4": "Unknown registration status",
                            "5": "Registered (roaming)"
                        }
                        
                        status_text = status_meanings.get(status, f"Unknown status {status}")
                        logger.info(f"Registration n={n}, status={status}: {status_text}")
                        
                        if status == "1":
                            logger.info("✓ Registered on home network")
                            return True
                        elif status == "5":
                            logger.info("✓ Registered on roaming network")
                            return True
                        elif status == "2":
                            logger.info(f"Searching for network... (attempt {attempt + 1}/30)")
                            time.sleep(2)
                            continue
                        elif status == "0":
                            if attempt < 5:  # Only try re-enabling a few times
                                logger.info("Not searching for network, trying to enable registration...")
                                # Try to enable registration again
                                self.send_command("AT+CREG=1", 1)
                                time.sleep(2)
                                continue
                            else:
                                logger.warning("Module not searching after multiple attempts, trying alternative approaches...")
                                # Try forcing automatic network selection
                                self.send_command("AT+COPS=0", 10)  # Automatic network selection
                                # Try enabling both CREG and CGREG
                                self.send_command("AT+CGREG=1", 2)  # Enable GPRS registration
                                # Wait a bit more
                                time.sleep(5)
                                continue
                        else:
                            logger.warning(f"Registration status {status}: {status_text}")
                            time.sleep(1)
                            continue
                    else:
                        logger.warning(f"Could not parse CREG response: {creg_line}")
                else:
                    logger.warning("No +CREG line found in response")
            
            logger.warning(f"Network registration response: {response}")
            time.sleep(1)
        
        logger.error("✗ Failed to register on network")
        logger.info("Troubleshooting tips:")
        logger.info("- Check SIM card has active service")
        logger.info("- Verify antenna is connected")
        logger.info("- Check network coverage in your area")
        logger.info("- Try manual network selection: AT+COPS=?")
        return False
    
    def scan_available_networks(self):
        """Scan for available networks (debugging helper)"""
        logger.info("Scanning for available networks...")
        success, response = self.send_command("AT+COPS=?", 30, "OK")  # This can take a long time
        
        if success and "+COPS:" in response:
            logger.info("Available networks:")
            # Parse network list
            networks = response.split("+COPS:")[1].strip()
            logger.info(f"Networks found: {networks}")
        else:
            logger.warning("Failed to scan networks or no networks found")
        
        return success
    
    def check_signal_quality(self):
        """Check signal strength"""
        logger.info("Checking signal quality...")
        success, response = self.send_command("AT+CSQ", 1)
        
        if "+CSQ:" in response:
            parts = response.split("+CSQ:")[1].strip().split(",")
            if len(parts) >= 1:
                rssi = parts[0].strip()
                if rssi != "99":
                    signal_strength = int(rssi) * 2 - 113  # Convert to dBm
                    logger.info(f"✓ Signal strength: {signal_strength} dBm (RSSI: {rssi})")
                    return int(rssi) > 10  # Minimum acceptable signal
                else:
                    logger.error("✗ No signal detected")
                    return False
        
        logger.error(f"✗ Failed to get signal quality: {response}")
        return False
    
    def send_sms(self, phone_number, message):
        """Send SMS message using improved UART handling"""
        logger.info(f"Sending SMS to {phone_number}...")
        
        # Set SMS text mode
        success, response = self.send_command("AT+CMGF=1", 1, "OK")
        if not success:
            logger.error("Failed to set SMS text mode")
            return False
        
        # Start SMS composition
        success, response = self.send_command(f'AT+CMGS="{phone_number}"', 1, ">")
        if not success:
            logger.error("Failed to start SMS composition")
            return False
        
        # Send message content using improved method
        try:
            print(f"RAW SMS SEND: {repr(message + chr(26))}")
            print(f"RAW SMS SEND HEX: {(message + chr(26)).encode().hex()}")
            
            with uart_lock:
                flush_uart()
                # Send message without \r\n (uart_send adds it automatically, but we don't want it for SMS content)
                self.pi.wave_clear()
                self.pi.wave_add_serial(TX_PIN, BAUDRATE, message.encode())
                wid = self.pi.wave_create()
                self.pi.wave_send_once(wid)
                while self.pi.wave_tx_busy():
                    time.sleep(0.01)
                self.pi.wave_delete(wid)
                
                # Send Ctrl+Z separately
                self.pi.wave_clear()
                self.pi.wave_add_serial(TX_PIN, BAUDRATE, chr(26).encode())
                wid = self.pi.wave_create()
                self.pi.wave_send_once(wid)
                while self.pi.wave_tx_busy():
                    time.sleep(0.01)
                self.pi.wave_delete(wid)
                
                # SMS has a special response pattern:
                # 1. Message echo (immediately)
                # 2. Network processing time (5-30 seconds)  
                # 3. +CMGS: response or ERROR
                
                print("Waiting for message echo...")
                initial_response = uart_read(timeout=5)  # Get the echo quickly
                print(f"Initial response: {repr(initial_response)}")
                
                total_response = initial_response
                
                # If we got the echo but not the final response, wait for network confirmation
                if initial_response and "+CMGS:" not in initial_response and "ERROR" not in initial_response:
                    print("Message echo received, waiting for network confirmation...")
                    
                    # Use a custom read loop for SMS responses
                    deadline = time.time() + 25  # Wait up to 25 seconds for network response
                    while time.time() < deadline:
                        count, data = self.pi.bb_serial_read(RX_PIN)
                        if count:
                            chunk = data.decode(errors='ignore')
                            total_response += chunk
                            print(f"Network response chunk: {repr(chunk)}")
                            
                            # Check if we have the final response
                            if "+CMGS:" in total_response or "ERROR" in total_response:
                                # Wait a bit more for any trailing data (like OK)
                                time.sleep(0.2)
                                count, data = self.pi.bb_serial_read(RX_PIN)
                                if count:
                                    total_response += data.decode(errors='ignore')
                                break
                        time.sleep(0.1)
                
                response = total_response
            
            print(f"RAW SMS RECEIVE: {repr(response)}")
            print(f"RAW SMS RECEIVE HEX: {response.encode().hex()}")
            print(f"DECODED SMS RESPONSE: {response.strip()}")
            
            if "+CMGS:" in response and "OK" in response:
                logger.info("✓ SMS sent successfully")
                return True
            elif "ERROR" in response:
                logger.error(f"✗ SMS sending failed: {response}")
                return False
            else:
                logger.error(f"✗ SMS sending timeout or failed: {response}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending SMS: {e}")
            return False
    
    def disconnect(self):
        """Close pigpio connection"""
        cleanup_pigpio()
        self.pi = None


def run_complete_sms_test():
    """Run complete SMS test suite"""
    logger.info("="*60)
    logger.info("Starting SIM800L SMS Test Suite")
    logger.info("="*60)
    
    gsm = SIM800L()
    
    try:
        # Step 1: Connect to module
        if not gsm.connect():
            logger.error("Failed to connect to SIM800L module")
            return False
        
        # Step 2: Test basic communication
        if not gsm.test_basic_communication():
            logger.error("Basic communication test failed")
            logger.info("Running hardware diagnostics...")
            gsm.hardware_diagnostic()
            return False
        
        # Step 3: Check SIM card PIN status
        if not gsm.check_cpin():
            logger.error("SIM card PIN check failed")
            return False
        
        # Step 4: Check network registration
        if not gsm.check_network_registration():
            logger.error("Network registration failed")
            logger.info("Running network diagnostics...")
            
            # Try to get more information about the network
            gsm.send_command("AT+COPS?", 2)  # Check current operator
            gsm.send_command("AT+CGREG?", 2)  # Check GPRS registration
            
            # Optionally scan networks (this takes time)
            user_choice = input("\nDo you want to scan for available networks? (y/N): ").strip().lower()
            if user_choice == 'y':
                gsm.scan_available_networks()
            
            return False
        
        # Step 5: Check signal quality
        if not gsm.check_signal_quality():
            logger.error("Signal quality check failed")
            return False
        
        # Step 6: Send test SMS
        test_message = f"Test SMS from Pi Zero W - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        if not gsm.send_sms(TEST_PHONE_NUMBER, test_message):
            logger.error("SMS sending test failed")
            return False
        
        logger.info("="*60)
        logger.info("✓ ALL TESTS PASSED - SMS functionality working correctly!")
        logger.info("="*60)
        return True
        
    except Exception as e:
        logger.error(f"Test suite failed with error: {e}")
        return False
    
    finally:
        gsm.disconnect()


def send_custom_sms(phone_number, message):
    """Send a custom SMS message"""
    logger.info(f"Sending custom SMS to {phone_number}")
    
    gsm = SIM800L()
    
    try:
        if not gsm.connect():
            return False
        
        if not gsm.test_basic_communication():
            return False
        
        if not gsm.check_cpin():
            return False
        
        success = gsm.send_sms(phone_number, message)
        return success
        
    except Exception as e:
        logger.error(f"Failed to send custom SMS: {e}")
        return False
    
    finally:
        gsm.disconnect()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) == 1:
        # Run complete test suite
        run_complete_sms_test()
    elif len(sys.argv) == 3:
        # Send custom SMS
        phone_number = sys.argv[1]
        message = sys.argv[2]
        success = send_custom_sms(phone_number, message)
        if success:
            print("SMS sent successfully!")
        else:
            print("Failed to send SMS")
            sys.exit(1)
    else:
        print("Usage:")
        print("  python3 send_sms.py                    # Run complete test suite")
        print("  python3 send_sms.py <phone> <message>  # Send custom SMS")
        print("")
        print("Environment variables:")
        print("  TEST_PHONE_NUMBER - Phone number for test SMS")
        print("  SIM_PIN          - SIM card PIN if required")
        print("  RX_PIN           - GPIO pin for SIM800L TX")
        print("  TX_PIN           - GPIO pin for SIM800L RX")
        print("  BAUDRATE         - Serial communication baud rate")
        print("")
        print("Requirements:")
        print("  - pigpio daemon running: sudo systemctl start pigpiod")
        print("  - pigpio Python library: pip3 install pigpio")

