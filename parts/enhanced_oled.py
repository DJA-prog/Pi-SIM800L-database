#!/usr/bin/env python3
"""
Enhanced OLED Display with Multiple Font Support
"""

import time
from luma.core.interface.serial import i2c
from luma.core.render import canvas
from luma.oled.device import ssd1306
from PIL import ImageFont
import threading
from datetime import datetime
import os

class EnhancedOLEDDisplay:
    def __init__(self, i2c_address=0x3c) -> None:
        """Initialize OLED display with font support"""
        self.device = None
        self.running = False
        
        # Data placeholders
        self.wifi_ip = "N/A"
        self.battery_percent = 0
        self.message_count = 0
        
        # Initialize fonts
        self._setup_fonts()
        
        try:
            # Initialize I2C interface and SSD1306 device
            serial = i2c(port=1, address=i2c_address)
            self.device = ssd1306(serial, width=128, height=32)
            print(f"✅ OLED initialized (0x{i2c_address:02x})")
        except Exception as e:
            print(f"❌ OLED init failed: {e}")
            self.device = None

    def _setup_fonts(self):
        """Setup different fonts for the display"""
        try:
            # Default font (always available)
            self.font_default = ImageFont.load_default()
            
            # TrueType fonts (fallback to default if not available)
            font_paths = {
                'small': ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 8),
                'medium': ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10),
                'bold': ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 10),
                'mono': ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 9),
                'mono_bold': ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 9),
                'large': ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12),
            }
            
            self.fonts = {}
            
            for name, (path, size) in font_paths.items():
                try:
                    if os.path.exists(path):
                        self.fonts[name] = ImageFont.truetype(path, size)
                        print(f"✅ Font {name} loaded (size {size})")
                    else:
                        self.fonts[name] = self.font_default
                        print(f"⚠️ Font {name} fallback to default")
                except Exception as e:
                    self.fonts[name] = self.font_default
                    print(f"⚠️ Font {name} failed, using default: {e}")
                    
        except Exception as e:
            print(f"Font setup error: {e}")
            # Fallback: all fonts = default
            self.fonts = {
                'small': ImageFont.load_default(),
                'medium': ImageFont.load_default(),
                'bold': ImageFont.load_default(),
                'mono': ImageFont.load_default(),
                'mono_bold': ImageFont.load_default(),
                'large': ImageFont.load_default(),
            }

    def draw_custom1_basic(self) -> None:
        """Display custom1 data with default font"""
        if not self.device:
            return
        
        try:
            with canvas(self.device) as draw:
                ip_text = self.wifi_ip if len(self.wifi_ip) <= 15 else self.wifi_ip[:12] + "..."
                draw.text((0, 0), f"IP: {ip_text}", fill="white")
                draw.text((0, 11), f"Bat: {self.battery_percent}%", fill="white")
                draw.text((0, 22), f"SMS: {self.message_count}", fill="white")
        except Exception as e:
            print(f"Display error: {e}")

    def draw_custom1_styled(self) -> None:
        """Display custom1 data with different fonts"""
        if not self.device:
            return
        
        try:
            with canvas(self.device) as draw:
                # IP with small font
                ip_text = self.wifi_ip if len(self.wifi_ip) <= 12 else self.wifi_ip[:9] + "..."
                draw.text((0, 0), f"IP: {ip_text}", font=self.fonts['small'], fill="white")
                
                # Battery with bold font
                draw.text((0, 10), f"Battery: {self.battery_percent}%", font=self.fonts['bold'], fill="white")
                
                # SMS with mono font (good for numbers)
                draw.text((0, 21), f"SMS: {self.message_count}", font=self.fonts['mono'], fill="white")
        except Exception as e:
            print(f"Styled display error: {e}")

    def draw_time_styled(self) -> None:
        """Display time with styled fonts"""
        if not self.device:
            return
        
        try:
            with canvas(self.device) as draw:
                now = datetime.now()
                
                # Date with small font
                date_str = now.strftime("%m/%d/%Y")
                draw.text((0, 0), date_str, font=self.fonts['small'], fill="white")
                
                # Time with large mono font
                time_str = now.strftime("%H:%M:%S")
                draw.text((0, 12), time_str, font=self.fonts['mono_bold'], fill="white")
        except Exception as e:
            print(f"Time display error: {e}")

    def draw_mixed_layout(self) -> None:
        """Demo layout with mixed fonts"""
        if not self.device:
            return
        
        try:
            with canvas(self.device) as draw:
                # Title with bold
                draw.text((0, 0), "SIM800L Status", font=self.fonts['bold'], fill="white")
                
                # Data with different fonts
                draw.text((0, 12), f"IP:{self.wifi_ip[:8]}", font=self.fonts['small'], fill="white")
                draw.text((65, 12), f"Bat:{self.battery_percent}%", font=self.fonts['small'], fill="white")
                draw.text((0, 22), f"Messages: {self.message_count}", font=self.fonts['medium'], fill="white")
        except Exception as e:
            print(f"Mixed layout error: {e}")

    def update_custom1_data(self, wifi_ip="N/A", battery_percent=0, message_count=0) -> None:
        """Update display data"""
        self.wifi_ip = wifi_ip
        self.battery_percent = battery_percent
        self.message_count = message_count

    def display_startup_message(self) -> None:
        """Show startup message with styled fonts"""
        if not self.device:
            return
        
        try:
            with canvas(self.device) as draw:
                draw.text((0, 0), "SIM800L Starting", font=self.fonts['bold'], fill="white")
                draw.text((0, 12), "Please wait...", font=self.fonts['medium'], fill="white")
                draw.text((0, 23), datetime.now().strftime("%H:%M"), font=self.fonts['mono'], fill="white")
        except Exception as e:
            print(f"Startup display error: {e}")

    def start_time(self) -> None:
        """Start time display thread"""
        if not self.device:
            return
        
        self.running = True

        def time_thread() -> None:
            while self.running:
                self.draw_time_styled()
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

    def demo_fonts(self) -> None:
        """Demonstrate different font styles"""
        if not self.device:
            return
        
        demos = [
            ("Basic Layout", self.draw_custom1_basic),
            ("Styled Layout", self.draw_custom1_styled),
            ("Mixed Layout", self.draw_mixed_layout),
            ("Time Display", self.draw_time_styled)
        ]
        
        for name, draw_func in demos:
            print(f"📺 Showing: {name}")
            draw_func()
            time.sleep(3)
            self.clear()
            time.sleep(1)

# Test functions
def main():
    """Test the enhanced OLED display"""
    print("🧪 Testing Enhanced OLED Display with Fonts...")
    
    display = EnhancedOLEDDisplay()
    
    if not display.is_available():
        print("❌ Display not available - check I2C connection")
        return
    
    print("✅ Display available, starting font demo...")
    
    # Setup test data
    display.update_custom1_data(
        wifi_ip="192.168.1.100", 
        battery_percent=85, 
        message_count=7
    )
    
    # Demo different font layouts
    display.demo_fonts()
    
    print("✅ Font demo completed")

if __name__ == "__main__":
    main()