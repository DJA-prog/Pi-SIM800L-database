#!/usr/bin/env python3
"""
SIM800L GSM Module SMS Receiver for Raspberry Pi Zero W
Listen for incoming SMS messages and display them
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

# Debug configuration
SHOW_RAW_DEBUG = os.getenv('SHOW_RAW_DEBUG', 'true').lower() == 'true'  # Set to False to disable raw output
AUTO_DELETE_SMS = os.getenv('AUTO_DELETE_SMS', 'true').lower() == 'true'  # Auto-delete SMS after reading

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
        if count > 0 and SHOW_RAW_DEBUG:
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
        if SHOW_RAW_DEBUG:
            print(f"RAW SEND: {repr(cmd + chr(13) + chr(10))}")
            print(f"RAW SEND HEX: {(cmd + chr(13) + chr(10)).encode().hex()}")
        uart_send(cmd)
        time.sleep(delay)  # Reduced default delay
        
        # Read response with timeout
        response = uart_read(timeout)
        if SHOW_RAW_DEBUG:
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
                    if SHOW_RAW_DEBUG:
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
    
    def check_and_read_sms(self, timeout_override=None):
        """Check for new SMS messages and return them"""
        logger.info("Checking for SMS messages...")
        
        # Set SMS text mode
        success, response = self.send_command("AT+CMGF=1", 0.5, "OK", timeout_override or 2)
        if not success:
            logger.error("Failed to set SMS text mode")
            return []
        
        # List all messages (unread and read) with shorter timeout
        success, response = self.send_command("AT+CMGL=\"ALL\"", 0.5, "OK", timeout_override or 3)
        if not success:
            logger.error("Failed to list SMS messages")
            return []
        
        messages = []
        if "+CMGL:" in response:
            # Parse SMS messages from response
            lines = response.split('\n')
            i = 0
            while i < len(lines):
                line = lines[i].strip()
                if line.startswith('+CMGL:'):
                    # Parse SMS header: +CMGL: index,"status","sender","","timestamp"
                    try:
                        # Extract message info
                        parts = line.split(',')
                        if len(parts) >= 3:
                            index = parts[0].split(':')[1].strip()
                            status = parts[1].strip(' "')
                            sender = parts[2].strip(' "')
                            
                            # Get timestamp if available
                            timestamp = ""
                            if len(parts) >= 5:
                                timestamp = parts[4].strip(' "')
                            
                            # The message content is on the next line
                            if i + 1 < len(lines):
                                message_content = lines[i + 1].strip()
                                
                                messages.append({
                                    'index': index,
                                    'status': status,
                                    'sender': sender,
                                    'timestamp': timestamp,
                                    'content': message_content
                                })
                                
                                logger.info(f"Found SMS #{index} from {sender}: {message_content[:50]}...")
                    except Exception as e:
                        logger.warning(f"Failed to parse SMS line: {line}, error: {e}")
                i += 1
        else:
            logger.info("No SMS messages found")
        
        return messages
    
    def delete_sms(self, index):
        """Delete SMS message by index"""
        success, response = self.send_command(f"AT+CMGD={index}", 0.5, "OK", 3)
        if success:
            logger.info(f"✓ Deleted SMS message #{index}")
        else:
            logger.warning(f"Failed to delete SMS #{index}: {response}")
        return success
    
    def delete_all_sms(self):
        """Delete all SMS messages"""
        success, response = self.send_command("AT+CMGDA=\"DEL ALL\"", 5, "OK")
        if success:
            logger.info("✓ Deleted all SMS messages")
        else:
            logger.warning(f"Failed to delete all SMS: {response}")
        return success
    
    def listen_for_new_sms(self, duration_seconds=None):
        """Listen for incoming SMS notifications"""
        logger.info("Setting up SMS notifications...")
        
        # Enable SMS notifications
        success, response = self.send_command("AT+CNMI=2,1,0,0,0", 2, "OK")
        if not success:
            logger.warning("Failed to enable SMS notifications, will use polling instead")
            return self.poll_for_sms(duration_seconds)
        
        logger.info(f"✓ SMS notifications enabled")
        if duration_seconds:
            logger.info(f"Listening for incoming SMS for {duration_seconds} seconds...")
            logger.info("Press Ctrl+C to stop listening")
        else:
            logger.info("Listening for incoming SMS indefinitely...")
            logger.info("Press Ctrl+C to stop listening")
        
        start_time = time.time()
        
        try:
            while True:
                # Check if duration limit reached
                if duration_seconds and (time.time() - start_time) > duration_seconds:
                    logger.info(f"Listening duration of {duration_seconds} seconds completed")
                    break
                
                # Listen for incoming data
                with uart_lock:
                    count, data = self.pi.bb_serial_read(RX_PIN)
                    if count > 0:
                        message = data.decode(errors='ignore')
                        if SHOW_RAW_DEBUG:
                            print(f"RAW RECEIVE: {repr(message)}")
                        
                        # Check for SMS notification: +CMTI: "SM",index
                        if "+CMTI:" in message:
                            logger.info("📱 New SMS notification received!")
                            # Extract SMS index
                            try:
                                match = re.search(r'\+CMTI:\s*"[^"]*",(\d+)', message)
                                if match:
                                    sms_index = match.group(1)
                                    logger.info(f"New SMS detected at index {sms_index}")
                                    
                                    # Show immediate notification
                                    print(f"\n📱 NEW SMS RECEIVED - Index {sms_index}")
                                    print("=" * 60)
                                    print(f"⏰ Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
                                    
                                    # Try direct SMS read with AT+CMGR (simple and fast)
                                    try:
                                        logger.info(f"Attempting direct read of SMS #{sms_index}...")
                                        
                                        # Use direct UART functions (we're already in the listening loop)
                                        logger.info(f"Sending AT+CMGR={sms_index} command...")
                                        
                                        # Send the read command directly without send_at (avoid lock issues)
                                        try:
                                            flush_uart()  # Clear any pending data
                                            
                                            command = f"AT+CMGR={sms_index}"
                                            if SHOW_RAW_DEBUG:
                                                print(f"RAW SEND: {repr(command + chr(13) + chr(10))}")
                                            uart_send(command)
                                            time.sleep(0.5)  # Wait for response
                                            
                                            # Read response
                                            response = uart_read(timeout=3)
                                            if SHOW_RAW_DEBUG:
                                                print(f"RAW RECEIVE: {repr(response)}")
                                            
                                            logger.info(f"Got response: {response[:50]}...")
                                        except Exception as uart_error:
                                            logger.error(f"UART error: {uart_error}")
                                            response = ""
                                        
                                        if "+CMGR:" in response:
                                            # Parse the response quickly
                                            lines = response.strip().split('\n')
                                            sender = "Unknown"
                                            timestamp = "Unknown"
                                            content = "Could not parse content"
                                            
                                            for i, line in enumerate(lines):
                                                if '+CMGR:' in line:
                                                    # Parse header: +CMGR: "status","sender","","timestamp"
                                                    try:
                                                        parts = line.split(',')
                                                        if len(parts) >= 2:
                                                            sender = parts[1].strip(' "')
                                                        if len(parts) >= 4:
                                                            timestamp = parts[3].strip(' "')
                                                    except:
                                                        pass
                                                    
                                                    # Content is usually on the next line
                                                    if i + 1 < len(lines) and lines[i + 1].strip():
                                                        content = lines[i + 1].strip()
                                                    break
                                            
                                            # Display the message
                                            print(f"� From: {sender}")
                                            if timestamp != "Unknown":
                                                print(f"⏰ Time: {timestamp}")
                                            print(f"💬 Message: {content}")
                                            print("=" * 60)
                                            
                                            logger.info(f"✓ Successfully read SMS from {sender}: {content[:30]}...")
                                            
                                        else:
                                            # Direct read failed, show basic info
                                            print(f"⚠️  Could not read message content (AT+CMGR failed)")
                                            print(f"📍 SMS stored at index: {sms_index}")
                                            print(f"📍 Response: {response.strip()[:100]}...")
                                            print("=" * 60)
                                            logger.warning(f"Direct SMS read failed: {response[:100]}...")
                                        
                                    except Exception as read_error:
                                        print(f"❌ Error reading SMS: {read_error}")
                                        print(f"📍 SMS notification received for index: {sms_index}")
                                        print("=" * 60)
                                        logger.error(f"SMS read exception: {read_error}")
                                    
                                    # Always try to delete the message to prevent backlog
                                    if AUTO_DELETE_SMS:
                                        try:
                                            logger.info(f"Deleting SMS #{sms_index} to keep storage clean...")
                                            # Use direct UART for delete as well
                                            try:
                                                flush_uart()  # Clear any pending data
                                                
                                                delete_command = f"AT+CMGD={sms_index}"
                                                if SHOW_RAW_DEBUG:
                                                    print(f"DELETE RAW SEND: {repr(delete_command + chr(13) + chr(10))}")
                                                uart_send(delete_command)
                                                time.sleep(0.5)  # Wait for response
                                                
                                                delete_response = uart_read(timeout=2)
                                                if SHOW_RAW_DEBUG:
                                                    print(f"DELETE RAW RECEIVE: {repr(delete_response)}")
                                                
                                                if "OK" in delete_response:
                                                    print(f"🗑️  Message #{sms_index} deleted from storage")
                                                    logger.info(f"✓ Deleted SMS #{sms_index}")
                                                else:
                                                    print(f"⚠️  Could not delete message #{sms_index}")
                                                    logger.warning(f"Delete failed: {delete_response}")
                                                    
                                            except Exception as uart_delete_error:
                                                logger.error(f"UART delete error: {uart_delete_error}")
                                                print(f"❌ UART delete error: {uart_delete_error}")
                                                
                                        except Exception as delete_error:
                                            logger.error(f"Delete failed: {delete_error}")
                                            print(f"❌ Delete error: {delete_error}")
                                
                                else:
                                    logger.warning(f"Could not extract SMS index from: {message}")
                            except Exception as e:
                                logger.warning(f"Failed to parse SMS notification: {e}")
                                # Fall back to reading all messages
                                logger.info("Reading all messages as fallback...")
                                try:
                                    messages = self.check_and_read_sms()
                                    self.display_messages(messages)
                                    # Delete all messages to prevent re-processing
                                    if messages:
                                        self.delete_all_sms()
                                except Exception as fallback_error:
                                    logger.error(f"Fallback message reading failed: {fallback_error}")
                        
                        # Also check for other unsolicited messages
                        elif message.strip() and not message.startswith('AT'):
                            if SHOW_RAW_DEBUG:
                                print(f"Other notification: {message.strip()}")
                
                time.sleep(0.1)  # Short polling interval
                
        except KeyboardInterrupt:
            logger.info("\n📱 Stopped listening for SMS")
    
    def read_single_sms(self, index, auto_delete=True):
        """Read a single SMS message by index and optionally delete it"""
        logger.info(f"Reading SMS #{index}...")
        
        # Use shorter timeout and proper parameter order
        success, response = self.send_command(f"AT+CMGR={index}", 0.5, "OK", 3)
        if not success:
            logger.error(f"Failed to read SMS #{index}: {response}")
            logger.warning("Trying alternative approach - reading all messages...")
            # Fallback: read all messages and find the one we want
            try:
                all_messages = self.check_and_read_sms()
                for msg in all_messages:
                    if msg['index'] == str(index):
                        self.display_single_message(msg)
                        if auto_delete:
                            logger.info(f"Auto-deleting SMS #{index} to keep storage clean...")
                            self.delete_sms(index)
                        return msg
            except Exception as e:
                logger.error(f"Fallback read failed: {e}")
            return None
        
        message = None
        if "+CMGR:" in response:
            lines = response.split('\n')
            for i, line in enumerate(lines):
                if line.strip().startswith('+CMGR:'):
                    try:
                        # Parse header
                        parts = line.split(',')
                        if len(parts) >= 3:
                            status = parts[0].split(':')[1].strip(' "')
                            sender = parts[1].strip(' "')
                            timestamp = ""
                            if len(parts) >= 4:
                                timestamp = parts[3].strip(' "')
                            
                            # Get message content
                            if i + 1 < len(lines):
                                content = lines[i + 1].strip()
                                
                                message = {
                                    'index': index,
                                    'status': status,
                                    'sender': sender,
                                    'timestamp': timestamp,
                                    'content': content
                                }
                                
                                self.display_single_message(message)
                                break
                    except Exception as e:
                        logger.error(f"Failed to parse SMS: {e}")
        
        if message and auto_delete:
            # Delete the message after reading to prevent accumulation
            logger.info(f"Auto-deleting SMS #{index} to keep storage clean...")
            self.delete_sms(index)
        
        return message
    
    def display_single_message(self, message):
        """Display a single SMS message in a formatted way"""
        print("\n" + "="*60)
        print("📱 NEW SMS MESSAGE")
        print("="*60)
        print(f"From: {message['sender']}")
        if message['timestamp']:
            print(f"Time: {message['timestamp']}")
        print(f"Status: {message['status']}")
        print(f"Index: {message['index']}")
        print("-" * 60)
        print(f"Message: {message['content']}")
        print("="*60)
    
    def display_messages(self, messages):
        """Display SMS messages in a formatted way"""
        if not messages:
            print("📱 No SMS messages found")
            return
        
        print(f"\n📱 Found {len(messages)} SMS message(s):")
        print("="*80)
        
        for i, msg in enumerate(messages, 1):
            print(f"\n[{i}] SMS #{msg['index']}")
            print(f"    From: {msg['sender']}")
            if msg['timestamp']:
                print(f"    Time: {msg['timestamp']}")
            print(f"    Status: {msg['status']}")
            print(f"    Message: {msg['content']}")
            print("-" * 60)
    
    def poll_for_sms(self, duration_seconds=None):
        """Poll for SMS messages at regular intervals"""
        logger.info("Using polling mode to check for SMS...")
        
        if duration_seconds:
            logger.info(f"Polling for SMS for {duration_seconds} seconds...")
        else:
            logger.info("Polling for SMS indefinitely...")
        
        logger.info("Press Ctrl+C to stop")
        
        start_time = time.time()
        last_message_count = 0
        
        try:
            while True:
                # Check if duration limit reached
                if duration_seconds and (time.time() - start_time) > duration_seconds:
                    logger.info(f"Polling duration of {duration_seconds} seconds completed")
                    break
                
                # Check for messages
                messages = self.check_and_read_sms()
                
                # Display new messages
                if len(messages) > last_message_count:
                    new_messages = messages[last_message_count:]
                    print(f"\n📱 Found {len(new_messages)} new message(s)!")
                    for msg in new_messages:
                        self.display_single_message(msg)
                    last_message_count = len(messages)
                
                # Wait before next poll
                time.sleep(10)  # Poll every 10 seconds
                
        except KeyboardInterrupt:
            logger.info("\n📱 Stopped polling for SMS")
    
    def disconnect(self):
        """Close pigpio connection"""
        cleanup_pigpio()
        self.pi = None


def run_sms_receiver():
    """Run SMS receiver - listen for incoming messages"""
    logger.info("="*60)
    logger.info("Starting SIM800L SMS Receiver")
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
            return False
        
        # Step 5: Check signal quality
        if not gsm.check_signal_quality():
            logger.error("Signal quality check failed")
            return False
        
        # Step 6: Read existing messages first
        logger.info("Checking for existing SMS messages...")
        existing_messages = gsm.check_and_read_sms()
        if existing_messages:
            gsm.display_messages(existing_messages)
            
            # Ask user if they want to delete old messages
            try:
                choice = input("\nDelete existing messages before listening? (y/N): ").strip().lower()
                if choice == 'y':
                    gsm.delete_all_sms()
                    logger.info("✓ Cleared existing messages")
            except (EOFError, KeyboardInterrupt):
                logger.info("Keeping existing messages")
        
        # Step 7: Listen for new SMS messages
        logger.info("\n📱 SMS Receiver is ready!")
        logger.info("Send an SMS to this SIM card number to test reception")
        
        # Ask for duration or listen indefinitely
        try:
            duration_input = input("Enter listening duration in seconds (or press Enter for indefinite): ").strip()
            duration = int(duration_input) if duration_input else None
        except (ValueError, EOFError, KeyboardInterrupt):
            duration = None
        
        gsm.listen_for_new_sms(duration)
        
        logger.info("="*60)
        logger.info("✓ SMS Receiver session completed")
        logger.info("="*60)
        return True
        
    except KeyboardInterrupt:
        logger.info("\n📱 SMS Receiver stopped by user")
        return True
    except Exception as e:
        logger.error(f"SMS Receiver failed with error: {e}")
        return False
    
    finally:
        gsm.disconnect()


def check_existing_sms():
    """Check and display existing SMS messages"""
    logger.info("Checking for existing SMS messages...")
    
    gsm = SIM800L()
    
    try:
        if not gsm.connect():
            return False
        
        if not gsm.test_basic_communication():
            return False
        
        if not gsm.check_cpin():
            return False
        
        messages = gsm.check_and_read_sms()
        gsm.display_messages(messages)
        
        return len(messages) > 0
        
    except Exception as e:
        logger.error(f"Failed to check existing SMS: {e}")
        return False
    
    finally:
        gsm.disconnect()


def run_complete_sms_test():
    """Run complete SMS test suite - backwards compatibility"""
    logger.info("Note: This script is now configured for SMS receiving.")
    logger.info("Use send_sms.py for sending SMS messages.")
    logger.info("Starting SMS receiver instead...")
    return run_sms_receiver()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) == 1:
        # Run SMS receiver
        run_sms_receiver()
    elif len(sys.argv) == 2 and sys.argv[1] == "--check":
        # Check existing messages only
        check_existing_sms()
    else:
        print("Usage:")
        print("  python3 recv_sms.py          # Listen for incoming SMS messages")
        print("  python3 recv_sms.py --check  # Check existing messages only")
        print("")
        print("Environment variables:")
        print("  SIM_PIN          - SIM card PIN if required")
        print("  RX_PIN           - GPIO pin for SIM800L TX")
        print("  TX_PIN           - GPIO pin for SIM800L RX")
        print("  BAUDRATE         - Serial communication baud rate")
        print("  SHOW_RAW_DEBUG   - Show raw communication data (true/false)")
        print("  AUTO_DELETE_SMS  - Auto-delete SMS after reading (true/false)")
        print("")
        print("Requirements:")
        print("  - pigpio daemon running: sudo systemctl start pigpiod")
        print("  - pigpio Python library: pip3 install pigpio")
        print("")
        print("Features:")
        print("  - Real-time SMS notifications")
        print("  - Display existing messages")
        print("  - Auto-delete messages after reading (configurable)")
        print("  - Formatted message display")
        print("  - Robust error handling and timeout management")

