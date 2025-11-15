#!/usr/bin/env python3
"""
SMS Manager API Test Client
Test script to demonstrate API functionality
"""

import requests
import time
import json

# Configuration
API_BASE_URL = "http://localhost:8000"

def test_api():
    """Test the SMS Manager API"""
    print("🧪 Testing SMS Manager API")
    print("="*50)
    
    try:
        # Test status endpoint
        print("1. Getting API status...")
        response = requests.get(f"{API_BASE_URL}/status")
        if response.status_code == 200:
            status = response.json()
            print(f"   ✓ Status: {status}")
        else:
            print(f"   ❌ Status check failed: {response.status_code}")
            return
        
        # Test send SMS
        print("\n2. Testing SMS sending...")
        test_phone = input("Enter test phone number (or press Enter to skip): ").strip()
        if test_phone:
            sms_data = {
                "phone_number": test_phone,
                "message": f"Test SMS from API - {time.strftime('%Y-%m-%d %H:%M:%S')}"
            }
            
            response = requests.post(f"{API_BASE_URL}/send", json=sms_data)
            if response.status_code == 200:
                result = response.json()
                print(f"   ✓ SMS Send: {result}")
            else:
                print(f"   ❌ SMS send failed: {response.status_code} - {response.text}")
        else:
            print("   ⏭️  SMS sending test skipped")
        
        # Test message retrieval
        print("\n3. Testing message retrieval...")
        response = requests.get(f"{API_BASE_URL}/messages")
        if response.status_code == 200:
            messages = response.json()
            print(f"   ✓ Retrieved {len(messages)} messages")
            for i, msg in enumerate(messages, 1):
                print(f"      [{i}] From: {msg['sender']}")
                print(f"          Message: {msg['message']}")
                print(f"          Received: {msg['received_at']}")
        else:
            print(f"   ❌ Message retrieval failed: {response.status_code}")
        
        # Test listening control
        print("\n4. Testing listening control...")
        
        # Stop listening
        response = requests.post(f"{API_BASE_URL}/stop-listening")
        if response.status_code == 200:
            print(f"   ✓ Stop listening: {response.json()}")
        
        time.sleep(1)
        
        # Start listening
        response = requests.post(f"{API_BASE_URL}/start-listening")
        if response.status_code == 200:
            print(f"   ✓ Start listening: {response.json()}")
        
        print("\n✅ API test completed!")
        print("\n📱 Try sending an SMS to test real-time reception")
        print("   Check received messages: GET /messages")
        
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to SMS Manager API")
        print("   Make sure the API is running: python3 sms_manager_api.py")
    except Exception as e:
        print(f"❌ Test failed: {e}")

def monitor_messages(interval=5):
    """Monitor for new messages continuously"""
    print(f"🔄 Monitoring messages every {interval} seconds...")
    print("Press Ctrl+C to stop")
    
    try:
        while True:
            response = requests.get(f"{API_BASE_URL}/messages")
            if response.status_code == 200:
                messages = response.json()
                if messages:
                    print(f"\n📱 {len(messages)} new message(s):")
                    for msg in messages:
                        print(f"   From: {msg['sender']}")
                        print(f"   Message: {msg['message']}")
                        print(f"   Time: {msg['received_at']}")
                        print("-" * 40)
                else:
                    print(".", end="", flush=True)
            time.sleep(interval)
            
    except KeyboardInterrupt:
        print("\n✋ Monitoring stopped")
    except Exception as e:
        print(f"\n❌ Monitoring error: {e}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "monitor":
        monitor_messages()
    else:
        test_api()
        
        # Ask if user wants to monitor
        monitor_choice = input("\nMonitor for incoming messages? (y/N): ").strip().lower()
        if monitor_choice == 'y':
            monitor_messages()