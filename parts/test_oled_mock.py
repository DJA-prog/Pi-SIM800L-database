#!/usr/bin/env python3
"""
Mock OLED Display Test - Tests OLED functionality without hardware
"""

import time
from datetime import datetime

class MockOLEDDisplay:
    """Mock OLED Display for testing without hardware"""
    
    def __init__(self, i2c_address=0x3c) -> None:
        """Initialize mock OLED display"""
        self.device = True  # Simulate device present
        self.running = False
        
        # Data placeholders
        self.wifi_ip = "N/A"
        self.battery_percent = 0
        self.message_count = 0
        
        print(f"✅ Mock OLED initialized (0x{i2c_address:02x})")

    def draw_custom1(self) -> None:
        """Mock display custom1 data"""
        print(f"📺 DISPLAY: IP: {self.wifi_ip} | Bat: {self.battery_percent}% | SMS: {self.message_count}")

    def draw_time(self) -> None:
        """Mock display current time"""
        current_time = datetime.now().strftime("%H:%M:%S")
        print(f"🕐 TIME: {current_time}")

    def update_custom1_data(self, wifi_ip="N/A", battery_percent=0, message_count=0) -> None:
        """Update display data"""
        self.wifi_ip = wifi_ip
        self.battery_percent = battery_percent
        self.message_count = message_count

    def display_startup_message(self) -> None:
        """Mock startup message"""
        print("🚀 STARTUP: SIM800L Starting - Please wait...")
        print(f"⏰ TIME: {datetime.now().strftime('%H:%M')}")
        
    def start_time(self) -> None:
        """Mock start time display"""
        print("⏰ Started time display")
        self.running = True

    def stop_time(self) -> None:
        """Mock stop time display"""
        print("⏹️ Stopped time display")
        self.running = False

    def is_available(self) -> bool:
        """Check if display is available"""
        return self.device is not None

    def clear(self) -> None:
        """Mock clear the display"""
        print("🧹 Display cleared")

def main():
    """Main function to test the mock OLED display"""
    print("🧪 Testing Mock OLED Display...")
    
    display = MockOLEDDisplay()
    
    if not display.is_available():
        print("❌ Display not available")
        return
    
    print("✅ Display available, starting test...\n")
    
    # Test 1: Show startup message
    print("📍 Test 1: Startup message")
    display.display_startup_message()
    time.sleep(2)
    print()

    # Test 2: Clear display
    print("📍 Test 2: Clear display")
    display.clear()
    time.sleep(1)
    print()
    
    # Test 3: Show custom data
    print("📍 Test 3: Custom data display")
    display.update_custom1_data(wifi_ip="192.168.1.100", battery_percent=75, message_count=5)
    display.draw_custom1()
    time.sleep(2)
    print()

    # Test 4: Time display simulation
    print("📍 Test 4: Time display (5 seconds)")
    display.start_time()
    for i in range(5):
        display.draw_time()
        time.sleep(1)
    display.stop_time()
    print()
    
    # Test 5: Updated custom data
    print("📍 Test 5: Updated custom data")
    display.update_custom1_data(wifi_ip="10.0.0.5", battery_percent=42, message_count=12)
    display.draw_custom1()
    time.sleep(2)
    print()

    # Test 6: Low battery warning
    print("📍 Test 6: Low battery simulation")
    display.update_custom1_data(wifi_ip="192.168.0.1", battery_percent=15, message_count=25)
    display.draw_custom1()
    time.sleep(2)
    print()

    display.clear()
    print("✅ Mock test completed successfully!")

if __name__ == "__main__":
    main()