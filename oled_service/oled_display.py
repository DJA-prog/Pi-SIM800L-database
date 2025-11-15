#!/usr/bin/env python3
"""
Lightweight OLED Display Module for SIM800L System (Pi Zero Optimized)
Shows WiFi IP, Battery %, and Message count on 128x32 SSD1306 display
"""

import time
from luma.core.interface.serial import i2c
from luma.core.render import canvas
from luma.oled.device import ssd1306
import threading
from datetime import datetime

class OLEDDisplay:
    def __init__(self, i2c_address=0x3c) -> None:
        """
        Initialize lightweight OLED display
        
        Args:
            i2c_address (int): I2C address of display (0x3c or 0x3d)
        """
        self.device = None
        self.running = False

        # custom1 data placeholders
        self.wifi_ip = "N/A"
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

    def draw_custom1(self) -> None:
        """Display custom1 data: WiFi IP, Battery %, Message count"""
        if not self.device:
            return
        
        try:
            with canvas(self.device) as draw:
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

    def draw_datetime(self) -> None:
        """Display current date and time"""
        if not self.device:
            return
        
        try:
            with canvas(self.device) as draw:
                now = datetime.now()
                date_str = now.strftime("%Y-%m-%d")
                time_str = now.strftime("%H:%M:%S")
                
                draw.text((0, 0), f"Date: {date_str}", fill="white")
                draw.text((0, 11), f"Time: {time_str}", fill="white")
        except Exception as e:
            print(f"DateTime display error: {e}")

    def update_custom1_data(self, wifi_ip="N/A", battery_percent=0, message_count=0) -> None:
        """Update display data"""
        self.wifi_ip = wifi_ip
        self.battery_percent = battery_percent
        self.message_count = message_count

    def draw_display(self)  -> None:
        """Draw content on OLED display"""
        self.draw_custom1()
    
    def display_startup_message(self) -> None:
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
        
    def start_time(self) -> None:
        """Start time display thread"""
        if not self.device:
            return
        
        self.running = True

        def time_thread() -> None:
            while self.running:
                self.draw_datetime()
                time.sleep(1)
        
        threading.Thread(target=time_thread, daemon=True).start()

    def stop_time(self) -> None:
        """Stop time display thread"""
        self.running = False

    def is_available(self) -> bool:
        """Check if display is available"""
        return self.device is not None

    def clear(self) -> None:
        """Clear the display"""
        if self.device:
            try:
                with canvas(self.device) as draw:
                    pass  # Clear by drawing nothing
            except Exception as e:
                print(f"Clear error: {e}")