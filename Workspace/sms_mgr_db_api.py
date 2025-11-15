#!/usr/bin/env python3
"""
SIM800L SMS Manager API with SQLite Database
Combined SMS sending and receiving with REST API interface and database storage
"""

import os
import time
import pigpio
import logging
import threading
import re
import json
import asyncio
import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from queue import Queue, Empty

# FastAPI imports
from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn

# Configuration from environment variables
RX_PIN = int(os.getenv('RX_PIN', 13))   # GPIO for SIM800L TX -> Pi RX
TX_PIN = int(os.getenv('TX_PIN', 12))   # GPIO for SIM800L RX <- Pi TX
BAUDRATE = int(os.getenv('BAUDRATE', 9600))
SIM_PIN = os.getenv('SIM_PIN', '9438')
DB_PATH = os.getenv('DB_PATH', '/tmp/sms_manager.db')

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
    id: Optional[int] = None
    index: str
    sender: str
    timestamp: str
    message: str
    received_at: str

class SystemMessage(BaseModel):
    id: Optional[int] = None
    level: str
    component: str
    message: str
    timestamp: str

class StatusInfo(BaseModel):
    connected: bool
    listening: bool
    battery_voltage: Optional[float] = None
    signal_strength: Optional[int] = None
    timestamp: str

class BulkDeleteRequest(BaseModel):
    message_ids: List[int]

class FilterRequest(BaseModel):
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    sender: Optional[str] = None
    keyword: Optional[str] = None
    limit: Optional[int] = 100

@dataclass
class SMS:
    index: str
    sender: str
    timestamp: str
    message: str
    received_at: str
    id: Optional[int] = None

# Initialize FastAPI
app = FastAPI(
    title="SIM800L SMS Manager API with Database",
    description="REST API for sending and receiving SMS messages via SIM800L GSM module with SQLite database storage",
    version="2.0.0"
)

class DatabaseManager:
    """SQLite database manager for SMS and system messages"""
    
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize SQLite database with tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create SMS messages table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sms_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                index_number TEXT,
                sender TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                message TEXT NOT NULL,
                received_at TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create system messages table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level TEXT NOT NULL,
                component TEXT NOT NULL,
                message TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create indexes for better performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sms_sender ON sms_messages(sender)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sms_timestamp ON sms_messages(timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sms_received_at ON sms_messages(received_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_system_level ON system_messages(level)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_system_timestamp ON system_messages(timestamp)')
        
        conn.commit()
        conn.close()
        logger.info("✓ Database initialized")
    
    def save_sms(self, sms: SMS) -> int:
        """Save SMS to database and return the ID"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO sms_messages (index_number, sender, timestamp, message, received_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (sms.index, sms.sender, sms.timestamp, sms.message, sms.received_at))
        
        sms_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        logger.info(f"✓ SMS saved to database with ID: {sms_id}")
        return sms_id
    
    def save_system_message(self, level: str, component: str, message: str) -> int:
        """Save system message to database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        timestamp = datetime.now().isoformat()
        cursor.execute('''
            INSERT INTO system_messages (level, component, message, timestamp)
            VALUES (?, ?, ?, ?)
        ''', (level, component, message, timestamp))
        
        msg_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return msg_id
    
    def get_sms_messages(self, filters: Optional[FilterRequest] = None) -> List[Dict]:
        """Get SMS messages with optional filters"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        query = "SELECT * FROM sms_messages WHERE 1=1"
        params = []
        
        if filters:
            if filters.start_date:
                query += " AND received_at >= ?"
                params.append(filters.start_date)
            
            if filters.end_date:
                query += " AND received_at <= ?"
                params.append(filters.end_date)
            
            if filters.sender:
                query += " AND sender LIKE ?"
                params.append(f"%{filters.sender}%")
            
            if filters.keyword:
                query += " AND message LIKE ?"
                params.append(f"%{filters.keyword}%")
        
        query += " ORDER BY received_at DESC"
        
        if filters and filters.limit:
            query += f" LIMIT {filters.limit}"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        columns = ['id', 'index_number', 'sender', 'timestamp', 'message', 'received_at', 'created_at']
        return [dict(zip(columns, row)) for row in rows]
    
    def get_system_messages(self, filters: Optional[FilterRequest] = None) -> List[Dict]:
        """Get system messages with optional filters"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        query = "SELECT * FROM system_messages WHERE 1=1"
        params = []
        
        if filters:
            if filters.start_date:
                query += " AND timestamp >= ?"
                params.append(filters.start_date)
            
            if filters.end_date:
                query += " AND timestamp <= ?"
                params.append(filters.end_date)
            
            if filters.keyword:
                query += " AND (component LIKE ? OR message LIKE ?)"
                params.extend([f"%{filters.keyword}%", f"%{filters.keyword}%"])
        
        query += " ORDER BY timestamp DESC"
        
        if filters and filters.limit:
            query += f" LIMIT {filters.limit}"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        columns = ['id', 'level', 'component', 'message', 'timestamp', 'created_at']
        return [dict(zip(columns, row)) for row in rows]
    
    def delete_sms_message(self, message_id: int) -> bool:
        """Delete single SMS message by ID"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM sms_messages WHERE id = ?", (message_id,))
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        
        return affected > 0
    
    def delete_sms_messages_bulk(self, message_ids: List[int]) -> int:
        """Delete multiple SMS messages by IDs"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        placeholders = ','.join(['?' for _ in message_ids])
        cursor.execute(f"DELETE FROM sms_messages WHERE id IN ({placeholders})", message_ids)
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        
        return affected
    
    def delete_system_message(self, message_id: int) -> bool:
        """Delete single system message by ID"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM system_messages WHERE id = ?", (message_id,))
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        
        return affected > 0
    
    def delete_system_messages_bulk(self, message_ids: List[int]) -> int:
        """Delete multiple system messages by IDs"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        placeholders = ','.join(['?' for _ in message_ids])
        cursor.execute(f"DELETE FROM system_messages WHERE id IN ({placeholders})", message_ids)
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        
        return affected
    
    def get_message_counts(self) -> Dict[str, int]:
        """Get counts of messages in database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM sms_messages")
        sms_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM system_messages")
        system_count = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            "sms_messages": sms_count,
            "system_messages": system_count
        }

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
    """Enhanced SMS Manager with database storage and hardware monitoring"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.pi = None
        self.listening = False
        self.received_sms_queue = Queue()
        self.listener_thread = None
        self.connected = False
        self.db = db_manager
        self.battery_voltage = None
        self.signal_strength = None
        
    def connect(self):
        """Initialize connection to SIM800L"""
        try:
            self.pi = init_pigpio()
            self.connected = True
            self.db.save_system_message("INFO", "SMSManager", "SMS Manager connected to SIM800L")
            logger.info("✓ SMS Manager connected to SIM800L")
            time.sleep(2)
            return True
        except Exception as e:
            error_msg = f"Failed to initialize SMS Manager: {e}"
            self.db.save_system_message("ERROR", "SMSManager", error_msg)
            logger.error(error_msg)
            self.connected = False
            return False
    
    def disconnect(self):
        """Disconnect from SIM800L and cleanup"""
        self.stop_listening()
        cleanup_pigpio()
        self.connected = False
        self.pi = None
        self.db.save_system_message("INFO", "SMSManager", "SMS Manager disconnected")
        
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
            
            # Log command execution
            if not success and expected_response != "OK":
                self.db.save_system_message("WARNING", "SMSManager", f"Command failed: {command}")
            
            return success, response.strip()
            
        except Exception as e:
            error_msg = f"Error sending command '{command}': {e}"
            self.db.save_system_message("ERROR", "SMSManager", error_msg)
            logger.error(error_msg)
            return False, ""
    
    def get_battery_voltage(self) -> Optional[float]:
        """Get battery voltage from SIM800L"""
        try:
            success, response = self.send_command("AT+CBC", 1)
            if success and "+CBC:" in response:
                # Parse response: +CBC: 0,87,4.156V
                match = re.search(r'\+CBC:\s*\d+,\d+,(\d+\.\d+)V', response)
                if match:
                    voltage = float(match.group(1))
                    self.battery_voltage = voltage
                    logger.debug(f"Battery voltage: {voltage}V")
                    return voltage
        except Exception as e:
            error_msg = f"Failed to get battery voltage: {e}"
            self.db.save_system_message("WARNING", "SMSManager", error_msg)
            logger.warning(error_msg)
        return None
    
    def get_signal_strength(self) -> Optional[int]:
        """Get signal strength from SIM800L"""
        try:
            success, response = self.send_command("AT+CSQ", 1)
            if success and "+CSQ:" in response:
                # Parse response: +CSQ: 15,99
                match = re.search(r'\+CSQ:\s*(\d+),\d+', response)
                if match:
                    rssi = int(match.group(1))
                    # Convert RSSI to signal strength percentage
                    if rssi == 99:
                        strength = 0
                    elif rssi >= 31:
                        strength = 100
                    else:
                        strength = int((rssi / 31) * 100)
                    
                    self.signal_strength = strength
                    logger.debug(f"Signal strength: {strength}% (RSSI: {rssi})")
                    return strength
        except Exception as e:
            error_msg = f"Failed to get signal strength: {e}"
            self.db.save_system_message("WARNING", "SMSManager", error_msg)
            logger.warning(error_msg)
        return None
    
    def update_hardware_status(self):
        """Update battery and signal status"""
        try:
            self.get_battery_voltage()
            self.get_signal_strength()
        except Exception as e:
            logger.warning(f"Failed to update hardware status: {e}")
    
    def initialize_module(self):
        """Initialize SIM800L module for SMS operations"""
        try:
            # Test basic communication
            logger.info("Testing basic communication...")
            success, response = self.send_command("AT", 1, "OK")
            if not success:
                logger.error("Failed basic communication test")
                self.db.save_system_message("ERROR", "SMSManager", "Failed basic communication test")
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
                        self.db.save_system_message("ERROR", "SMSManager", "Failed to unlock SIM")
                        return False
                else:
                    logger.error("SIM requires PIN but none provided")
                    self.db.save_system_message("ERROR", "SMSManager", "SIM requires PIN but none provided")
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
                self.db.save_system_message("ERROR", "SMSManager", "Failed to set SMS text mode")
                return False
            
            # Update hardware status
            self.update_hardware_status()
            
            logger.info("✓ SIM800L module initialized successfully")
            self.db.save_system_message("INFO", "SMSManager", "SIM800L module initialized successfully")
            return True
            
        except Exception as e:
            error_msg = f"Module initialization failed: {e}"
            logger.error(error_msg)
            self.db.save_system_message("ERROR", "SMSManager", error_msg)
            return False
    
    def send_sms(self, phone_number: str, message: str) -> bool:
        """Send SMS message and log to database"""
        try:
            logger.info(f"Sending SMS to {phone_number}...")
            
            # Set SMS text mode
            success, response = self.send_command("AT+CMGF=1", 1, "OK")
            if not success:
                error_msg = "Failed to set SMS text mode for sending"
                logger.error(error_msg)
                self.db.save_system_message("ERROR", "SMSManager", error_msg)
                return False
            
            # Start SMS composition
            success, response = self.send_command(f'AT+CMGS="{phone_number}"', 1, ">")
            if not success:
                error_msg = f"Failed to start SMS composition to {phone_number}"
                logger.error(error_msg)
                self.db.save_system_message("ERROR", "SMSManager", error_msg)
                return False
            
            # Send message content
            with uart_lock:
                flush_uart()
                # Send message without \r\n
                self.pi.wave_clear()
                self.pi.wave_add_serial(TX_PIN, BAUDRATE, message.encode())
                wid = self.pi.wave_create()
                self.pi.wave_send_once(wid)
                while self.pi.wave_tx_busy():
                    time.sleep(0.01)
                self.pi.wave_delete(wid)
                
                # Send Ctrl+Z
                self.pi.wave_clear()
                self.pi.wave_add_serial(TX_PIN, BAUDRATE, chr(26).encode())
                wid = self.pi.wave_create()
                self.pi.wave_send_once(wid)
                while self.pi.wave_tx_busy():
                    time.sleep(0.01)
                self.pi.wave_delete(wid)
                
                # Wait for response
                initial_response = uart_read(timeout=5)
                total_response = initial_response
                
                # Wait for network confirmation if needed
                if initial_response and "+CMGS:" not in initial_response and "ERROR" not in initial_response:
                    deadline = time.time() + 25
                    while time.time() < deadline:
                        count, data = self.pi.bb_serial_read(RX_PIN)
                        if count:
                            chunk = data.decode(errors='ignore')
                            total_response += chunk
                            if "+CMGS:" in total_response or "ERROR" in total_response:
                                time.sleep(0.2)
                                count, data = self.pi.bb_serial_read(RX_PIN)
                                if count:
                                    total_response += data.decode(errors='ignore')
                                break
                        time.sleep(0.1)
                
                response = total_response
            
            if "+CMGS:" in response and "OK" in response:
                logger.info("✓ SMS sent successfully")
                self.db.save_system_message("INFO", "SMSManager", f"SMS sent to {phone_number}")
                return True
            else:
                error_msg = f"SMS sending failed to {phone_number}: {response}"
                logger.error(error_msg)
                self.db.save_system_message("ERROR", "SMSManager", error_msg)
                return False
                
        except Exception as e:
            error_msg = f"Error sending SMS to {phone_number}: {e}"
            logger.error(error_msg)
            self.db.save_system_message("ERROR", "SMSManager", error_msg)
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
            self.db.save_system_message("WARNING", "SMSManager", "Failed to enable SMS notifications")
            return
        
        # Start listener thread
        self.listener_thread = threading.Thread(target=self._sms_listener, daemon=True)
        self.listener_thread.start()
        logger.info("✓ SMS listener started")
        self.db.save_system_message("INFO", "SMSManager", "SMS listener started")
    
    def stop_listening(self):
        """Stop listening for incoming SMS messages"""
        self.listening = False
        if self.listener_thread:
            self.listener_thread.join(timeout=2)
        logger.info("✓ SMS listener stopped")
        self.db.save_system_message("INFO", "SMSManager", "SMS listener stopped")
    
    def _sms_listener(self):
        """Background thread to listen for SMS notifications"""
        logger.info("SMS listener thread started")
        
        while self.listening:
            try:
                with uart_lock:
                    count, data = self.pi.bb_serial_read(RX_PIN)
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
                                        # Save to database
                                        sms_id = self.db.save_sms(sms)
                                        sms.id = sms_id
                                        
                                        # Add to queue for API access
                                        self.received_sms_queue.put(sms)
                                        logger.info(f"✓ SMS from {sms.sender} saved and queued")
                                    
                                    # Auto-delete if enabled
                                    if AUTO_DELETE_SMS:
                                        self._delete_sms_direct(sms_index)
                                        
                            except Exception as e:
                                error_msg = f"Failed to process SMS notification: {e}"
                                logger.error(error_msg)
                                self.db.save_system_message("ERROR", "SMSManager", error_msg)
                
                time.sleep(0.1)
                
            except Exception as e:
                error_msg = f"SMS listener error: {e}"
                logger.error(error_msg)
                self.db.save_system_message("ERROR", "SMSManager", error_msg)
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
            error_msg = f"Error reading SMS {index}: {e}"
            logger.error(error_msg)
            self.db.save_system_message("ERROR", "SMSManager", error_msg)
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
            error_msg = f"Error deleting SMS {index}: {e}"
            logger.error(error_msg)
            self.db.save_system_message("ERROR", "SMSManager", error_msg)
    
    def get_received_messages(self) -> List[SMS]:
        """Get all received messages from queue (for backward compatibility)"""
        messages = []
        try:
            while True:
                sms = self.received_sms_queue.get_nowait()
                messages.append(sms)
        except Empty:
            pass
        return messages

# Global instances
db_manager = None
sms_manager = None

# API Endpoints

@app.on_event("startup")
async def startup_event():
    """Initialize Database and SMS Manager on startup"""
    global sms_manager, db_manager
    
    # Initialize database
    db_manager = DatabaseManager()
    
    # Initialize SMS Manager with database
    sms_manager = SMSManager(db_manager)
    
    if not sms_manager.connect():
        logger.error("Failed to connect to SIM800L")
        raise RuntimeError("SIM800L connection failed")
    
    if not sms_manager.initialize_module():
        logger.error("Failed to initialize SIM800L module")
        raise RuntimeError("SIM800L initialization failed")
    
    # Start listening for incoming SMS
    sms_manager.start_listening()
    logger.info("✓ SMS Manager API with Database started successfully")

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
        <title>SIM800L SMS Manager API with Database</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            .endpoint { margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }
            .method { font-weight: bold; color: #007acc; }
            .method.get { color: #61affe; }
            .method.post { color: #49cc90; }
            .method.delete { color: #f93e3e; }
            .url { font-family: monospace; background: #f5f5f5; padding: 2px 5px; }
            .category { color: #666; font-weight: bold; margin-top: 30px; }
            pre { background: #f5f5f5; padding: 10px; border-radius: 3px; }
        </style>
    </head>
    <body>
        <h1>📱 SIM800L SMS Manager API with Database</h1>
        <p>REST API for sending and receiving SMS messages via SIM800L GSM module with SQLite database storage</p>
        
        <div class="category">📤 SMS Operations</div>
        <div class="endpoint">
            <h3><span class="method post">POST</span> <span class="url">/send</span></h3>
            <p>Send an SMS message</p>
            <pre>{"phone_number": "+1234567890", "message": "Hello World"}</pre>
        </div>
        
        <div class="endpoint">
            <h3><span class="method get">GET</span> <span class="url">/messages</span></h3>
            <p>Get received SMS messages (from queue)</p>
        </div>
        
        <div class="category">📊 Status & Control</div>
        <div class="endpoint">
            <h3><span class="method get">GET</span> <span class="url">/status</span></h3>
            <p>Get SMS Manager status, battery voltage, signal strength, and message counts</p>
        </div>
        
        <div class="endpoint">
            <h3><span class="method post">POST</span> <span class="url">/start-listening</span></h3>
            <p>Start listening for incoming SMS</p>
        </div>
        
        <div class="endpoint">
            <h3><span class="method post">POST</span> <span class="url">/stop-listening</span></h3>
            <p>Stop listening for incoming SMS</p>
        </div>
        
        <div class="category">🗄️ Database Operations</div>
        <div class="endpoint">
            <h3><span class="method get">GET</span> <span class="url">/db/sms</span></h3>
            <p>Get SMS messages from database with filtering</p>
            <p>Query parameters: start_date, end_date, sender, keyword, limit</p>
        </div>
        
        <div class="endpoint">
            <h3><span class="method get">GET</span> <span class="url">/db/system</span></h3>
            <p>Get system messages from database with filtering</p>
            <p>Query parameters: start_date, end_date, keyword, limit</p>
        </div>
        
        <div class="endpoint">
            <h3><span class="method get">GET</span> <span class="url">/db/stats</span></h3>
            <p>Get database statistics and message counts</p>
        </div>
        
        <div class="category">🗑️ Message Deletion</div>
        <div class="endpoint">
            <h3><span class="method delete">DELETE</span> <span class="url">/db/sms/{message_id}</span></h3>
            <p>Delete single SMS message by ID</p>
        </div>
        
        <div class="endpoint">
            <h3><span class="method delete">DELETE</span> <span class="url">/db/sms/bulk</span></h3>
            <p>Delete multiple SMS messages by IDs</p>
            <pre>{"message_ids": [1, 2, 3]}</pre>
        </div>
        
        <div class="endpoint">
            <h3><span class="method delete">DELETE</span> <span class="url">/db/system/{message_id}</span></h3>
            <p>Delete single system message by ID</p>
        </div>
        
        <div class="endpoint">
            <h3><span class="method delete">DELETE</span> <span class="url">/db/system/bulk</span></h3>
            <p>Delete multiple system messages by IDs</p>
            <pre>{"message_ids": [1, 2, 3]}</pre>
        </div>
        
        <div class="category">📋 Documentation</div>
        <p><strong>Interactive API Documentation:</strong> <a href="/docs">/docs</a> | <a href="/redoc">/redoc</a></p>
        
        <div class="category">⚙️ Features</div>
        <ul>
            <li>📤 Send SMS messages via REST API</li>
            <li>📥 Receive SMS messages in real-time</li>
            <li>🗄️ SQLite database storage for all messages</li>
            <li>🔍 Advanced filtering by date, sender, keywords</li>
            <li>🗑️ Selective and bulk message deletion</li>
            <li>🔋 Battery voltage monitoring</li>
            <li>📶 Signal strength monitoring</li>
            <li>📊 System logging and statistics</li>
            <li>🔗 RESTful API interface</li>
            <li>📱 Auto-delete received messages from SIM card</li>
        </ul>
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
    """Get SMS Manager status with hardware information"""
    if not sms_manager:
        return {
            "status": "disconnected", 
            "connected": False, 
            "listening": False,
            "battery_voltage": None,
            "signal_strength": None
        }
    
    # Update hardware status
    sms_manager.update_hardware_status()
    
    # Get message counts
    counts = db_manager.get_message_counts() if db_manager else {"sms_messages": 0, "system_messages": 0}
    
    return {
        "status": "connected" if sms_manager.connected else "disconnected",
        "connected": sms_manager.connected,
        "listening": sms_manager.listening,
        "battery_voltage": sms_manager.battery_voltage,
        "signal_strength": sms_manager.signal_strength,
        "message_counts": counts,
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

# Database API Endpoints

@app.get("/db/sms")
async def get_sms_from_db(
    start_date: Optional[str] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[str] = Query(None, description="End date (ISO format)"),
    sender: Optional[str] = Query(None, description="Sender phone number or name"),
    keyword: Optional[str] = Query(None, description="Search keyword in message content"),
    limit: Optional[int] = Query(100, description="Maximum number of messages to return")
):
    """Get SMS messages from database with filtering"""
    if not db_manager:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        filters = FilterRequest(
            start_date=start_date,
            end_date=end_date,
            sender=sender,
            keyword=keyword,
            limit=limit
        )
        
        messages = db_manager.get_sms_messages(filters)
        return {
            "messages": messages,
            "count": len(messages),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Database SMS fetch error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch SMS messages: {str(e)}")

@app.get("/db/system")
async def get_system_messages_from_db(
    start_date: Optional[str] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[str] = Query(None, description="End date (ISO format)"),
    keyword: Optional[str] = Query(None, description="Search keyword in component or message"),
    limit: Optional[int] = Query(100, description="Maximum number of messages to return")
):
    """Get system messages from database with filtering"""
    if not db_manager:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        filters = FilterRequest(
            start_date=start_date,
            end_date=end_date,
            keyword=keyword,
            limit=limit
        )
        
        messages = db_manager.get_system_messages(filters)
        return {
            "messages": messages,
            "count": len(messages),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Database system messages fetch error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch system messages: {str(e)}")

@app.delete("/db/sms/{message_id}")
async def delete_sms_message(message_id: int):
    """Delete single SMS message by ID"""
    if not db_manager:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        success = db_manager.delete_sms_message(message_id)
        if success:
            return {
                "success": True,
                "message": f"SMS message {message_id} deleted",
                "timestamp": datetime.now().isoformat()
            }
        else:
            raise HTTPException(status_code=404, detail=f"SMS message {message_id} not found")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Database SMS delete error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete SMS message: {str(e)}")

@app.delete("/db/sms/bulk")
async def delete_sms_messages_bulk(request: BulkDeleteRequest):
    """Delete multiple SMS messages by IDs"""
    if not db_manager:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        affected = db_manager.delete_sms_messages_bulk(request.message_ids)
        return {
            "success": True,
            "message": f"Deleted {affected} SMS messages",
            "deleted_count": affected,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Database SMS bulk delete error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete SMS messages: {str(e)}")

@app.delete("/db/system/{message_id}")
async def delete_system_message(message_id: int):
    """Delete single system message by ID"""
    if not db_manager:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        success = db_manager.delete_system_message(message_id)
        if success:
            return {
                "success": True,
                "message": f"System message {message_id} deleted",
                "timestamp": datetime.now().isoformat()
            }
        else:
            raise HTTPException(status_code=404, detail=f"System message {message_id} not found")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Database system message delete error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete system message: {str(e)}")

@app.delete("/db/system/bulk")
async def delete_system_messages_bulk(request: BulkDeleteRequest):
    """Delete multiple system messages by IDs"""
    if not db_manager:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        affected = db_manager.delete_system_messages_bulk(request.message_ids)
        return {
            "success": True,
            "message": f"Deleted {affected} system messages",
            "deleted_count": affected,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Database system messages bulk delete error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete system messages: {str(e)}")

@app.get("/db/stats")
async def get_database_stats():
    """Get database statistics"""
    if not db_manager:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        counts = db_manager.get_message_counts()
        
        # Get recent message counts (last 24 hours)
        yesterday = (datetime.now() - timedelta(days=1)).isoformat()
        recent_filters = FilterRequest(start_date=yesterday, limit=1000)
        
        recent_sms = db_manager.get_sms_messages(recent_filters)
        recent_system = db_manager.get_system_messages(recent_filters)
        
        return {
            "total_counts": counts,
            "recent_24h": {
                "sms_messages": len(recent_sms),
                "system_messages": len(recent_system)
            },
            "database_path": DB_PATH,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Database stats error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get database stats: {str(e)}")

if __name__ == "__main__":
    import sys
    
    print("🚀 Starting SIM800L SMS Manager API with Database")
    print("="*60)
    print("Features:")
    print("  📤 Send SMS messages via REST API")
    print("  📥 Receive SMS messages in real-time")
    print("  �️ SQLite database storage for all messages")
    print("  🔍 Advanced filtering by date, sender, keywords")
    print("  �️ Selective and bulk message deletion")
    print("  🔋 Battery voltage monitoring")
    print("  📶 Signal strength monitoring")
    print("  📊 System logging and statistics")
    print("  � RESTful API interface")
    print("  �📱 Auto-delete received messages from SIM card")
    print("")
    print("Environment variables:")
    print("  SIM_PIN          - SIM card PIN if required")
    print("  RX_PIN           - GPIO pin for SIM800L TX (default: 13)")
    print("  TX_PIN           - GPIO pin for SIM800L RX (default: 12)")
    print("  BAUDRATE         - Serial communication baud rate (default: 9600)")
    print("  DB_PATH          - SQLite database path (default: /tmp/sms_manager.db)")
    print("  SHOW_RAW_DEBUG   - Show raw communication data (true/false)")
    print("  AUTO_DELETE_SMS  - Auto-delete SMS after reading (true/false)")
    print("")
    print("Database Features:")
    print("  • Persistent SMS and system message storage")
    print("  • Advanced filtering and search capabilities")
    print("  • Bulk operations for message management")
    print("  • Performance optimized with database indexes")
    print("")
    print("API will be available at: http://localhost:8000")
    print("Documentation: http://localhost:8000/docs")
    print("Database: {}".format(DB_PATH))
    print("="*60)
    
    # Get port from command line or use default
    port = 8000
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"Invalid port '{sys.argv[1]}', using default 8000")
    
    # Run the API server
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
