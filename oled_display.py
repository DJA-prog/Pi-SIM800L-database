#!/usr/bin/env python3
"""
Lightweight OLED Display Module for SIM800L System (Pi Zero Optimized)
Shows WiFi IP, Battery %, and Message count on 128x32 SSD1306 display
"""

import time
import socket
import subprocess
from luma.core.interface.serial import i2c
from luma.core.render import canvas
from luma.oled.device import ssd1306
import sqlite3
import threading
from datetime import datetime

class OLEDDisplay:
    def __init__(self, database_path="sms_messages.db", i2c_address=0x3c):
        """
        Initialize lightweight OLED display
        
        Args:
            database_path (str): Path to SMS database
            i2c_address (int): I2C address of display (0x3c or 0x3d)
        """
        self.database_path = database_path
        self.device = None
        self.running = False
        self.update_thread = None
        self.wifi_ip = "No IP"
        self.battery_percent = 0
        self.message_count = 0
        
        try:
            # Initialize I2C interface and SSD1306 device
            serial = i2c(port=1, address=i2c_address)
            self.device = ssd1306(serial, width=128, height=32)
            print(f"✅ OLED initialized (0x{i2c_address:02x})")
        except Exception as e:
            print(f"❌ OLED init failed: {e}")
            self.device = None
    
    def get_wifi_ip(self):
        """Get WiFi IP address - optimized for Pi Zero"""
        try:
            # Quick method - get first IP
            result = subprocess.run(['hostname', '-I'], capture_output=True, text=True, timeout=3)
            if result.returncode == 0:
                ip = result.stdout.strip().split()[0]
                return ip if ip else "No IP"
            return "No IP"
        except Exception:
            return "No IP"
    
    def get_battery_percent(self):
        """Get battery percentage via API call"""
        try:
            import requests
            response = requests.get("http://localhost:5000/battery_status", timeout=2)
            if response.status_code == 200:
                data = response.json()
                if 'battery' in data and 'percentage' in data['battery']:
                    return int(data['battery']['percentage'])
            return 0
        except Exception:
            return 0
    
    def get_message_count(self):
        """Get total message count from database"""
        try:
            conn = sqlite3.connect(self.database_path, timeout=1.0)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM sms_messages")
            count = cursor.fetchone()[0]
            conn.close()
            return count
        except Exception:
            return 0
    
    def update_data(self):
        """Update display data"""
        self.wifi_ip = self.get_wifi_ip()
        self.battery_percent = self.get_battery_percent()
        self.message_count = self.get_message_count()
    
    def draw_display(self):
        """Draw content on OLED display"""
        if not self.device:
            return
        
        try:
            with canvas(self.device) as draw:
                # Line 1: WiFi IP (truncated if needed)
                ip_text = self.wifi_ip
                if len(ip_text) > 15:
                    ip_text = ip_text[:12] + "..."
                draw.text((0, 0), f"IP: {ip_text}", fill="white")
                
                # Line 2: Battery percentage
                draw.text((0, 11), f"Bat: {self.battery_percent}%", fill="white")
                
                # Line 3: Message count
                draw.text((0, 22), f"SMS: {self.message_count}", fill="white")
        except Exception as e:
            print(f"Display error: {e}")
    
    def display_startup_message(self):
        """Show startup message"""
        if not self.device:
            return
        
        try:
            with canvas(self.device) as draw:
                draw.text((0, 0), "SIM800L Starting", fill="white")
                draw.text((0, 11), "Please wait...", fill="white")
                draw.text((0, 22), datetime.now().strftime("%H:%M"), fill="white")
        except Exception as e:
            print(f"Startup display error: {e}")
    
    def update_loop(self):
        """Main update loop for display"""
        while self.running:
            try:
                self.update_data()
                self.draw_display()
                time.sleep(10)  # Update every 10 seconds (Pi Zero friendly)
            except Exception as e:
                print(f"Update error: {e}")
                time.sleep(15)  # Wait longer on error
    
    def start(self):
        """Start the display update thread"""
        if not self.device:
            print("❌ Cannot start display - device not initialized")
            return False
        
        if self.running:
            return True
        
        self.running = True
        self.display_startup_message()
        time.sleep(2)
        
        self.update_thread = threading.Thread(target=self.update_loop, daemon=True)
        self.update_thread.start()
        print("✅ OLED Display started")
        return True
    
    def stop(self):
        """Stop the display update thread"""
        self.running = False
        if self.update_thread:
            self.update_thread.join(timeout=3)
        
        if self.device:
            try:
                with canvas(self.device) as draw:
                    draw.text((0, 11), "System Stopped", fill="white")
            except:
                pass
        print("🛑 OLED Display stopped")
    
    def is_available(self):
        """Check if display is available"""
        return self.device is not None


# Test function
def test_display():
    """Test the OLED display"""
    print("🧪 Testing OLED Display...")
    
    display = OLEDDisplay()
    
    if not display.is_available():
        print("❌ Display not available - check I2C connection")
        return
    
    print("✅ Display available, starting test...")
    display.start()
    
    try:
        print("Running for 30 seconds... Press Ctrl+C to stop")
        time.sleep(30)
    except KeyboardInterrupt:
        print("\n⏹️ Test stopped by user")
    finally:
        display.stop()


if __name__ == "__main__":
    test_display()