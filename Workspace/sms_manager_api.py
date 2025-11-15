#!/usr/bin/env python3
"""
SIM800L SMS Manager API for Raspberry Pi Zero W
Combined SMS sending and receiving with REST API interface
"""

import os
import time
import pigpio
import logging
import threading
import re
import json
import asyncio
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass
from queue import Queue, Empty

# FastAPI imports
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn

# Configuration from environment variables
RX_PIN = int(os.getenv('RX_PIN', 13))   # GPIO for SIM800L TX -> Pi RX
TX_PIN = int(os.getenv('TX_PIN', 12))   # GPIO for SIM800L RX <- Pi TX
BAUDRATE = int(os.getenv('BAUDRATE', 9600))
SIM_PIN = os.getenv('SIM_PIN', '9438')

# Debug configuration
SHOW_RAW_DEBUG = os.getenv('SHOW_RAW_DEBUG', 'false').lower() == 'true'
AUTO_DELETE_SMS = os.getenv('AUTO_DELETE_SMS', 'true').lower() == 'true'

# Global pigpio instance and locks
pi = None
uart_lock = threading.Lock()
sms_manager = None

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/sms_manager.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# FastAPI models
class SMSMessage(BaseModel):
    phone_number: str
    message: str

class SMSResponse(BaseModel):
    success: bool
    message: str
    timestamp: str

class ReceivedSMS(BaseModel):
    index: str
    sender: str
    timestamp: str
    message: str
    received_at: str

@dataclass
class SMS:
    index: str
    sender: str
    timestamp: str
    message: str
    received_at: str

# Initialize FastAPI
app = FastAPI(
    title="SIM800L SMS Manager API",
    description="REST API for sending and receiving SMS messages via SIM800L GSM module",
    version="1.0.0"
)

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

class SMSManager:
    """Combined SMS Manager for sending and receiving messages"""
    
    def __init__(self):
        self.pi = None
        self.listening = False
        self.received_sms_queue = Queue()
        self.listener_thread = None
        self.connected = False
        
    def connect(self):
        """Initialize connection to SIM800L"""
        try:
            self.pi = init_pigpio()
            self.connected = True
            logger.info("✓ SMS Manager connected to SIM800L")
            time.sleep(2)
            return True
        except Exception as e:
            logger.error(f"Failed to initialize SMS Manager: {e}")
            self.connected = False
            return False
    
    def disconnect(self):
        """Disconnect from SIM800L and cleanup"""
        self.stop_listening()
        cleanup_pigpio()
        self.connected = False
        self.pi = None
        
    def send_command(self, command, wait_time=0.1, expected_response="OK", timeout=None):
        """Send AT command with timeout handling"""
        if not self.connected:
            logger.error("SMS Manager not connected")
            return False, ""
        
        try:
            # Use command-specific timeout if not provided
            if timeout is None:
                if command.startswith("AT+COPS="):
                    timeout = 15
                elif command.startswith("AT+CFUN="):
                    timeout = 8
                elif command.startswith("AT+CPIN="):
                    timeout = 5
                elif "?" in command:
                    timeout = 3
                else:
                    timeout = 2
            
            response = send_at(command, delay=wait_time, timeout=timeout)
            success = expected_response in response if expected_response else True
            return success, response.strip()
            
        except Exception as e:
            logger.error(f"Error sending command '{command}': {e}")
            return False, ""
    
    def initialize_module(self):
        """Initialize SIM800L module for SMS operations"""
        try:
            # Test basic communication
            logger.info("Testing basic communication...")
            success, response = self.send_command("AT", 1, "OK")
            if not success:
                logger.error("Failed basic communication test")
                return False
            
            # Check SIM PIN
            logger.info("Checking SIM PIN status...")
            success, response = self.send_command("AT+CPIN?", 0.1)
            if "SIM PIN" in response:
                if SIM_PIN:
                    logger.info("Unlocking SIM with PIN...")
                    success, response = self.send_command(f"AT+CPIN={SIM_PIN}", 0.1)
                    if not success:
                        logger.error("Failed to unlock SIM")
                        return False
                else:
                    logger.error("SIM requires PIN but none provided")
                    return False
            
            # Enable full functionality
            logger.info("Enabling full functionality...")
            self.send_command("AT+CFUN=1", 5)
            time.sleep(3)
            
            # Set SMS text mode
            logger.info("Setting SMS text mode...")
            success, response = self.send_command("AT+CMGF=1", 1, "OK")
            if not success:
                logger.error("Failed to set SMS text mode")
                return False
            
            logger.info("✓ SIM800L module initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Module initialization failed: {e}")
            return False
    
    def send_sms(self, phone_number: str, message: str) -> bool:
        """Send SMS message"""
        try:
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
            
            # Send message content
            with uart_lock:
                flush_uart()
                # Send message without \r\n
                pi.wave_clear()
                pi.wave_add_serial(TX_PIN, BAUDRATE, message.encode())
                wid = pi.wave_create()
                pi.wave_send_once(wid)
                while pi.wave_tx_busy():
                    time.sleep(0.01)
                pi.wave_delete(wid)
                
                # Send Ctrl+Z
                pi.wave_clear()
                pi.wave_add_serial(TX_PIN, BAUDRATE, chr(26).encode())
                wid = pi.wave_create()
                pi.wave_send_once(wid)
                while pi.wave_tx_busy():
                    time.sleep(0.01)
                pi.wave_delete(wid)
                
                # Wait for response
                initial_response = uart_read(timeout=5)
                total_response = initial_response
                
                # Wait for network confirmation if needed
                if initial_response and "+CMGS:" not in initial_response and "ERROR" not in initial_response:
                    deadline = time.time() + 25
                    while time.time() < deadline:
                        count, data = pi.bb_serial_read(RX_PIN)
                        if count:
                            chunk = data.decode(errors='ignore')
                            total_response += chunk
                            if "+CMGS:" in total_response or "ERROR" in total_response:
                                time.sleep(0.2)
                                count, data = pi.bb_serial_read(RX_PIN)
                                if count:
                                    total_response += data.decode(errors='ignore')
                                break
                        time.sleep(0.1)
                
                response = total_response
            
            if "+CMGS:" in response and "OK" in response:
                logger.info("✓ SMS sent successfully")
                return True
            else:
                logger.error(f"SMS sending failed: {response}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending SMS: {e}")
            return False
    
    def start_listening(self):
        """Start listening for incoming SMS messages"""
        if self.listening:
            logger.warning("Already listening for SMS")
            return
        
        logger.info("Starting SMS listener...")
        self.listening = True
        
        # Enable SMS notifications
        success, response = self.send_command("AT+CNMI=2,1,0,0,0", 2, "OK")
        if not success:
            logger.warning("Failed to enable SMS notifications")
            return
        
        # Start listener thread
        self.listener_thread = threading.Thread(target=self._sms_listener, daemon=True)
        self.listener_thread.start()
        logger.info("✓ SMS listener started")
    
    def stop_listening(self):
        """Stop listening for incoming SMS messages"""
        self.listening = False
        if self.listener_thread:
            self.listener_thread.join(timeout=2)
        logger.info("✓ SMS listener stopped")
    
    def _sms_listener(self):
        """Background thread to listen for SMS notifications"""
        logger.info("SMS listener thread started")
        
        while self.listening:
            try:
                with uart_lock:
                    count, data = pi.bb_serial_read(RX_PIN)
                    if count > 0:
                        message = data.decode(errors='ignore')
                        if SHOW_RAW_DEBUG:
                            print(f"RAW RECEIVE: {repr(message)}")
                        
                        # Check for SMS notification
                        if "+CMTI:" in message:
                            logger.info("📱 New SMS notification received!")
                            try:
                                match = re.search(r'\+CMTI:\s*"[^"]*",(\d+)', message)
                                if match:
                                    sms_index = match.group(1)
                                    logger.info(f"Reading SMS at index {sms_index}")
                                    
                                    # Read the SMS message
                                    sms = self._read_sms_direct(sms_index)
                                    if sms:
                                        self.received_sms_queue.put(sms)
                                        logger.info(f"✓ SMS from {sms.sender} queued")
                                    
                                    # Auto-delete if enabled
                                    if AUTO_DELETE_SMS:
                                        self._delete_sms_direct(sms_index)
                                        
                            except Exception as e:
                                logger.error(f"Failed to process SMS notification: {e}")
                
                time.sleep(0.1)
                
            except Exception as e:
                logger.error(f"SMS listener error: {e}")
                time.sleep(1)
        
        logger.info("SMS listener thread stopped")
    
    def _read_sms_direct(self, index: str) -> Optional[SMS]:
        """Read SMS message directly using UART commands"""
        try:
            # Send read command directly
            flush_uart()
            command = f"AT+CMGR={index}"
            uart_send(command)
            time.sleep(0.5)
            
            response = uart_read(timeout=3)
            
            if "+CMGR:" in response:
                lines = response.strip().split('\n')
                sender = "Unknown"
                timestamp = "Unknown"
                message = "Could not parse content"
                
                for i, line in enumerate(lines):
                    if '+CMGR:' in line:
                        try:
                            parts = line.split(',')
                            if len(parts) >= 2:
                                sender = parts[1].strip(' "')
                            if len(parts) >= 4:
                                timestamp = parts[3].strip(' "')
                        except:
                            pass
                        
                        # Content is on the next line
                        if i + 1 < len(lines) and lines[i + 1].strip():
                            message = lines[i + 1].strip()
                        break
                
                return SMS(
                    index=index,
                    sender=sender,
                    timestamp=timestamp,
                    message=message,
                    received_at=datetime.now().isoformat()
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Error reading SMS {index}: {e}")
            return None
    
    def _delete_sms_direct(self, index: str):
        """Delete SMS message directly"""
        try:
            flush_uart()
            delete_command = f"AT+CMGD={index}"
            uart_send(delete_command)
            time.sleep(0.5)
            delete_response = uart_read(timeout=2)
            
            if "OK" in delete_response:
                logger.info(f"✓ Deleted SMS #{index}")
            else:
                logger.warning(f"Failed to delete SMS #{index}")
                
        except Exception as e:
            logger.error(f"Error deleting SMS {index}: {e}")
    
    def get_received_messages(self) -> List[SMS]:
        """Get all received messages from queue"""
        messages = []
        try:
            while True:
                sms = self.received_sms_queue.get_nowait()
                messages.append(sms)
        except Empty:
            pass
        return messages

# API Endpoints

@app.on_event("startup")
async def startup_event():
    """Initialize SMS Manager on startup"""
    global sms_manager
    sms_manager = SMSManager()
    
    if not sms_manager.connect():
        logger.error("Failed to connect to SIM800L")
        raise RuntimeError("SIM800L connection failed")
    
    if not sms_manager.initialize_module():
        logger.error("Failed to initialize SIM800L module")
        raise RuntimeError("SIM800L initialization failed")
    
    # Start listening for incoming SMS
    sms_manager.start_listening()
    logger.info("✓ SMS Manager API started successfully")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    global sms_manager
    if sms_manager:
        sms_manager.disconnect()
    logger.info("✓ SMS Manager API shutdown complete")

@app.get("/", response_class=HTMLResponse)
async def root():
    """API documentation page"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>SIM800L SMS Manager API</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            .endpoint { margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }
            .method { font-weight: bold; color: #007acc; }
            .url { font-family: monospace; background: #f5f5f5; padding: 2px 5px; }
            pre { background: #f5f5f5; padding: 10px; border-radius: 3px; }
        </style>
    </head>
    <body>
        <h1>📱 SIM800L SMS Manager API</h1>
        <p>REST API for sending and receiving SMS messages via SIM800L GSM module</p>
        
        <div class="endpoint">
            <h3><span class="method">POST</span> <span class="url">/send</span></h3>
            <p>Send an SMS message</p>
            <pre>{"phone_number": "+1234567890", "message": "Hello World"}</pre>
        </div>
        
        <div class="endpoint">
            <h3><span class="method">GET</span> <span class="url">/messages</span></h3>
            <p>Get received SMS messages</p>
        </div>
        
        <div class="endpoint">
            <h3><span class="method">GET</span> <span class="url">/status</span></h3>
            <p>Get SMS Manager status</p>
        </div>
        
        <div class="endpoint">
            <h3><span class="method">POST</span> <span class="url">/start-listening</span></h3>
            <p>Start listening for incoming SMS</p>
        </div>
        
        <div class="endpoint">
            <h3><span class="method">POST</span> <span class="url">/stop-listening</span></h3>
            <p>Stop listening for incoming SMS</p>
        </div>
        
        <p><strong>Documentation:</strong> <a href="/docs">/docs</a> | <a href="/redoc">/redoc</a></p>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.post("/send", response_model=SMSResponse)
async def send_sms(sms: SMSMessage):
    """Send an SMS message"""
    if not sms_manager or not sms_manager.connected:
        raise HTTPException(status_code=503, detail="SMS Manager not available")
    
    try:
        success = sms_manager.send_sms(sms.phone_number, sms.message)
        
        return SMSResponse(
            success=success,
            message=f"SMS {'sent successfully' if success else 'sending failed'} to {sms.phone_number}",
            timestamp=datetime.now().isoformat()
        )
        
    except Exception as e:
        logger.error(f"API send error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send SMS: {str(e)}")

@app.get("/messages", response_model=List[ReceivedSMS])
async def get_messages():
    """Get received SMS messages"""
    if not sms_manager:
        raise HTTPException(status_code=503, detail="SMS Manager not available")
    
    try:
        messages = sms_manager.get_received_messages()
        
        return [
            ReceivedSMS(
                index=msg.index,
                sender=msg.sender,
                timestamp=msg.timestamp,
                message=msg.message,
                received_at=msg.received_at
            )
            for msg in messages
        ]
        
    except Exception as e:
        logger.error(f"API messages error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get messages: {str(e)}")

@app.get("/status")
async def get_status():
    """Get SMS Manager status"""
    if not sms_manager:
        return {"status": "disconnected", "connected": False, "listening": False}
    
    return {
        "status": "connected" if sms_manager.connected else "disconnected",
        "connected": sms_manager.connected,
        "listening": sms_manager.listening,
        "timestamp": datetime.now().isoformat()
    }

@app.post("/start-listening")
async def start_listening():
    """Start listening for incoming SMS"""
    if not sms_manager or not sms_manager.connected:
        raise HTTPException(status_code=503, detail="SMS Manager not available")
    
    try:
        sms_manager.start_listening()
        return {"success": True, "message": "SMS listening started", "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"API start listening error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start listening: {str(e)}")

@app.post("/stop-listening")
async def stop_listening():
    """Stop listening for incoming SMS"""
    if not sms_manager:
        raise HTTPException(status_code=503, detail="SMS Manager not available")
    
    try:
        sms_manager.stop_listening()
        return {"success": True, "message": "SMS listening stopped", "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"API stop listening error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to stop listening: {str(e)}")

if __name__ == "__main__":
    import sys
    
    print("🚀 Starting SIM800L SMS Manager API")
    print("="*50)
    print("Features:")
    print("  📤 Send SMS messages via REST API")
    print("  📥 Receive SMS messages in real-time")
    print("  🔗 RESTful API interface")
    print("  📊 Status monitoring")
    print("  📱 Auto-delete received messages")
    print("")
    print("Environment variables:")
    print("  SIM_PIN          - SIM card PIN if required")
    print("  RX_PIN           - GPIO pin for SIM800L TX (default: 13)")
    print("  TX_PIN           - GPIO pin for SIM800L RX (default: 12)")
    print("  BAUDRATE         - Serial communication baud rate (default: 9600)")
    print("  SHOW_RAW_DEBUG   - Show raw communication data (true/false)")
    print("  AUTO_DELETE_SMS  - Auto-delete SMS after reading (true/false)")
    print("")
    print("API will be available at: http://localhost:8000")
    print("Documentation: http://localhost:8000/docs")
    print("="*50)
    
    # Get port from command line or use default
    port = 8000
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"Invalid port '{sys.argv[1]}', using default 8000")
    
    # Run the API server
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
