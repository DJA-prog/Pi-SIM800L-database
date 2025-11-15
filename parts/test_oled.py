from oled_display import OLEDDisplay
import time

def main():
    """Main function to test the OLED display"""
    print("🧪 Testing OLED Display...")
    
    display = OLEDDisplay()
    
    if not display.is_available():
        print("❌ Display not available - check I2C connection")
        return
    
    print("✅ Display available, starting test...")
    
    # Test 1: Show startup message
    print("📍 Test 1: Startup message")
    display.display_startup_message()
    time.sleep(3)

    # Test 2: Clear display
    print("📍 Test 2: Clear display")
    display.clear()
    time.sleep(2)
    
    # Test 3: Show custom data
    print("📍 Test 3: Custom data display")
    display.update_custom1_data(wifi_ip="192.168.1.100", battery_percent=75, message_count=5)
    display.draw_custom1()
    time.sleep(5)

    # Test 4: Time display
    print("📍 Test 4: Time display (10 seconds)")
    display.start_time()
    time.sleep(10)
    display.stop_time()
    
    # Test 5: Updated custom data
    print("📍 Test 5: Updated custom data")
    for i in range(51):
        display.update_custom1_data(wifi_ip="10.0.0.5", battery_percent=i*2, message_count=12)
        display.draw_custom1()
        time.sleep(0.5)

    try:
        print("🕐 Display will run for 15 more seconds... Press Ctrl+C to stop early")
        time.sleep(15)
    except KeyboardInterrupt:
        print("\n⏹️ Test stopped by user")
    finally:
        display.stop_time()  # Ensure time thread is stopped
        display.clear()  # Clear display at end
        print("✅ Test completed")

if __name__ == "__main__":
    main()