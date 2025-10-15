#!/usr/bin/env python3
"""
Test script to debug OLED battery percentage issue
"""

import requests
import json

def test_battery_api():
    """Test the battery API endpoint"""
    print("🔋 Testing Battery API...")
    
    try:
        response = requests.get("http://localhost:5000/api/battery", timeout=5)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("✅ API Response:")
            print(json.dumps(data, indent=2))
            
            if 'status' in data and data['status'] == 'success' and 'data' in data:
                battery_data = data['data']
                if 'charge_level' in battery_data:
                    battery_percent = int(battery_data['charge_level'])
                    print(f"✅ Battery Percentage: {battery_percent}%")
                    return battery_percent
                else:
                    print("❌ No 'charge_level' in battery data")
            else:
                print("❌ API response format issue")
        else:
            print(f"❌ API Error: {response.status_code}")
            print(f"Response: {response.text}")
            
    except requests.exceptions.ConnectionError:
        print("❌ Connection Error: Server not running on localhost:5000")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    return 0

def test_oled_display():
    """Test OLED display data update"""
    print("\n🖥️ Testing OLED Display...")
    
    try:
        from oled_display import OLEDDisplay
        
        # Create OLED instance (don't start the thread)
        oled = OLEDDisplay()
        
        print("Testing individual methods:")
        
        # Test WiFi IP
        wifi_ip = oled.get_wifi_ip()
        print(f"WiFi IP: {wifi_ip}")
        
        # Test battery percentage
        battery_percent = oled.get_battery_percent()
        print(f"Battery Percent: {battery_percent}%")
        
        # Test message count
        message_count = oled.get_message_count()
        print(f"Message Count: {message_count}")
        
        if oled.is_available():
            print("✅ OLED display is available")
        else:
            print("❌ OLED display not available")
            
    except ImportError as e:
        print(f"❌ Import Error: {e}")
        print("Make sure luma.oled is installed: pip install luma.oled")
    except Exception as e:
        print(f"❌ OLED Test Error: {e}")

def test_oled_status_api():
    """Test the OLED status API endpoint"""
    print("\n📡 Testing OLED Status API...")
    
    try:
        response = requests.get("http://localhost:5000/api/system/oled-status", timeout=5)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("✅ OLED Status Response:")
            print(json.dumps(data, indent=2))
        else:
            print(f"❌ API Error: {response.status_code}")
            print(f"Response: {response.text}")
            
    except requests.exceptions.ConnectionError:
        print("❌ Connection Error: Server not running on localhost:5000")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    print("🧪 OLED Battery Debug Test")
    print("=" * 40)
    
    # Test battery API
    battery_percent = test_battery_api()
    
    # Test OLED display
    test_oled_display()
    
    # Test OLED status API
    test_oled_status_api()
    
    print("\n" + "=" * 40)
    print("🔍 Debug Summary:")
    print(f"Battery API returned: {battery_percent}%")
    print("\nIf battery percentage is 0, check:")
    print("1. Is the SIM800L server running?")
    print("2. Is the SIM800L responding to AT+CBC commands?")
    print("3. Check server logs for battery monitoring errors")
    print("\nTo test manually:")
    print("curl http://localhost:5000/api/battery")
    print("curl http://localhost:5000/api/system/oled-status")