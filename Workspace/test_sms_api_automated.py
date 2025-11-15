#!/usr/bin/env python3
"""
Automated SMS Manager API Test Suite
Comprehensive testing script for the SMS Manager API
"""

import requests
import time
import json
import sys
from datetime import datetime
from typing import List, Dict, Any

# Configuration
API_BASE_URL = "http://localhost:8000"
TEST_PHONE_NUMBER = "+264816828893"  # Replace with your test number

class SMSAPITester:
    """Automated test suite for SMS Manager API"""
    
    def __init__(self, base_url: str = API_BASE_URL, test_phone: str = TEST_PHONE_NUMBER):
        self.base_url = base_url
        self.test_phone = test_phone
        self.session = requests.Session()
        self.test_results = []
        self.failed_tests = []
        
    def log_test(self, test_name: str, success: bool, details: str = ""):
        """Log test result"""
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}")
        if details:
            print(f"    {details}")
        
        self.test_results.append({
            "test": test_name,
            "success": success,
            "details": details,
            "timestamp": datetime.now().isoformat()
        })
        
        if not success:
            self.failed_tests.append(test_name)
    
    def test_api_status(self) -> bool:
        """Test API status endpoint"""
        try:
            response = self.session.get(f"{self.base_url}/status", timeout=10)
            if response.status_code == 200:
                data = response.json()
                connected = data.get('connected', False)
                listening = data.get('listening', False)
                self.log_test("API Status", True, f"Connected: {connected}, Listening: {listening}")
                return connected
            else:
                self.log_test("API Status", False, f"HTTP {response.status_code}")
                return False
        except Exception as e:
            self.log_test("API Status", False, f"Connection error: {e}")
            return False
    
    def test_send_sms(self, phone: str, message: str, test_name: str = "Send SMS") -> bool:
        """Test SMS sending"""
        try:
            data = {"phone_number": phone, "message": message}
            response = self.session.post(f"{self.base_url}/send", json=data, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                success = result.get('success', False)
                self.log_test(test_name, success, f"Response: {result.get('message', '')}")
                return success
            else:
                self.log_test(test_name, False, f"HTTP {response.status_code}: {response.text}")
                return False
        except Exception as e:
            self.log_test(test_name, False, f"Error: {e}")
            return False
    
    def test_get_messages(self) -> List[Dict]:
        """Test message retrieval"""
        try:
            response = self.session.get(f"{self.base_url}/messages", timeout=10)
            if response.status_code == 200:
                messages = response.json()
                self.log_test("Get Messages", True, f"Retrieved {len(messages)} messages")
                return messages
            else:
                self.log_test("Get Messages", False, f"HTTP {response.status_code}")
                return []
        except Exception as e:
            self.log_test("Get Messages", False, f"Error: {e}")
            return []
    
    def test_listening_control(self) -> bool:
        """Test start/stop listening functionality"""
        try:
            # Stop listening
            response = self.session.post(f"{self.base_url}/stop-listening", timeout=10)
            stop_success = response.status_code == 200
            
            time.sleep(1)
            
            # Check status
            response = self.session.get(f"{self.base_url}/status", timeout=10)
            if response.status_code == 200:
                status = response.json()
                stopped = not status.get('listening', True)
            else:
                stopped = False
            
            # Start listening
            response = self.session.post(f"{self.base_url}/start-listening", timeout=10)
            start_success = response.status_code == 200
            
            time.sleep(1)
            
            # Check status again
            response = self.session.get(f"{self.base_url}/status", timeout=10)
            if response.status_code == 200:
                status = response.json()
                started = status.get('listening', False)
            else:
                started = False
            
            success = stop_success and stopped and start_success and started
            self.log_test("Listening Control", success, 
                         f"Stop: {stop_success}, Stopped: {stopped}, Start: {start_success}, Started: {started}")
            return success
            
        except Exception as e:
            self.log_test("Listening Control", False, f"Error: {e}")
            return False
    
    def test_error_handling(self):
        """Test API error handling"""
        test_cases = [
            {
                "name": "Invalid Phone Number",
                "data": {"phone_number": "invalid", "message": "test"},
                "expect_error": True
            },
            {
                "name": "Empty Message",
                "data": {"phone_number": self.test_phone, "message": ""},
                "expect_error": True
            },
            {
                "name": "Missing Phone Number",
                "data": {"message": "test"},
                "expect_error": True
            },
            {
                "name": "Missing Message",
                "data": {"phone_number": self.test_phone},
                "expect_error": True
            }
        ]
        
        for case in test_cases:
            try:
                response = self.session.post(f"{self.base_url}/send", json=case["data"], timeout=10)
                
                if case["expect_error"]:
                    success = response.status_code >= 400
                    self.log_test(f"Error Test: {case['name']}", success, 
                                 f"Expected error, got HTTP {response.status_code}")
                else:
                    success = response.status_code == 200
                    self.log_test(f"Error Test: {case['name']}", success, 
                                 f"Expected success, got HTTP {response.status_code}")
                    
            except Exception as e:
                self.log_test(f"Error Test: {case['name']}", False, f"Exception: {e}")
    
    def test_special_characters(self):
        """Test SMS with special characters"""
        test_messages = [
            "📱 Emoji test 🚀",
            "Special chars: áéíóú ñç",
            "JSON chars: \"quotes\" \\backslash\\ {brackets}",
            "Multi-line\nMessage\nTest",
            "Long message: " + "A" * 150  # Test near SMS limit
        ]
        
        for i, message in enumerate(test_messages, 1):
            success = self.test_send_sms(self.test_phone, message, f"Special Chars Test {i}")
            time.sleep(2)  # Wait between sends
    
    def test_documentation_endpoints(self):
        """Test documentation endpoints"""
        endpoints = [
            ("/", "Root Documentation"),
            ("/docs", "Swagger UI"),
            ("/redoc", "ReDoc"),
            ("/openapi.json", "OpenAPI Schema")
        ]
        
        for endpoint, name in endpoints:
            try:
                response = self.session.get(f"{self.base_url}{endpoint}", timeout=10)
                success = response.status_code == 200
                self.log_test(f"Documentation: {name}", success, f"HTTP {response.status_code}")
            except Exception as e:
                self.log_test(f"Documentation: {name}", False, f"Error: {e}")
    
    def run_full_test_suite(self):
        """Run the complete test suite"""
        print("🧪 SMS Manager API - Full Test Suite")
        print("=" * 60)
        print(f"Target API: {self.base_url}")
        print(f"Test Phone: {self.test_phone}")
        print("=" * 60)
        
        # Test 1: API Status
        print("\n1. Testing API Status...")
        if not self.test_api_status():
            print("❌ API not available - stopping tests")
            return False
        
        # Test 2: Documentation Endpoints
        print("\n2. Testing Documentation Endpoints...")
        self.test_documentation_endpoints()
        
        # Test 3: Listening Control
        print("\n3. Testing Listening Control...")
        self.test_listening_control()
        
        # Test 4: Basic SMS Sending
        print("\n4. Testing Basic SMS Sending...")
        self.test_send_sms(self.test_phone, f"Basic test - {datetime.now().strftime('%H:%M:%S')}")
        time.sleep(3)
        
        # Test 5: Special Characters
        print("\n5. Testing Special Characters...")
        self.test_special_characters()
        
        # Test 6: Error Handling
        print("\n6. Testing Error Handling...")
        self.test_error_handling()
        
        # Test 7: Message Retrieval
        print("\n7. Testing Message Retrieval...")
        messages = self.test_get_messages()
        if messages:
            print("   📥 Received messages:")
            for msg in messages[-3:]:  # Show last 3
                print(f"      From: {msg['sender']} - {msg['message'][:50]}...")
        
        # Test 8: Performance Test
        print("\n8. Testing Performance (3 quick messages)...")
        for i in range(3):
            self.test_send_sms(self.test_phone, f"Performance test {i+1}/3", f"Performance Test {i+1}")
            time.sleep(1)
        
        # Final status check
        print("\n9. Final Status Check...")
        self.test_api_status()
        
        # Test Summary
        self.print_summary()
        return len(self.failed_tests) == 0
    
    def print_summary(self):
        """Print test results summary"""
        total_tests = len(self.test_results)
        passed_tests = total_tests - len(self.failed_tests)
        
        print("\n" + "=" * 60)
        print("📊 TEST SUMMARY")
        print("=" * 60)
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {len(self.failed_tests)}")
        print(f"Success Rate: {(passed_tests/total_tests*100):.1f}%")
        
        if self.failed_tests:
            print("\n❌ Failed Tests:")
            for test in self.failed_tests:
                print(f"   - {test}")
        
        print("\n💾 Detailed results saved to test_results.json")
        
        # Save detailed results
        with open("test_results.json", "w") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "summary": {
                    "total": total_tests,
                    "passed": passed_tests,
                    "failed": len(self.failed_tests),
                    "success_rate": passed_tests/total_tests*100
                },
                "results": self.test_results,
                "failed_tests": self.failed_tests
            }, f, indent=2)

def main():
    """Main test execution"""
    if len(sys.argv) > 1:
        if sys.argv[1] == "quick":
            # Quick test mode
            tester = SMSAPITester()
            print("🏃‍♂️ Quick Test Mode")
            print("-" * 30)
            tester.test_api_status()
            tester.test_send_sms(tester.test_phone, "Quick test message")
            tester.test_get_messages()
            tester.print_summary()
        elif sys.argv[1] == "monitor":
            # Monitor mode - check for new messages
            print("👁️  Message Monitor Mode")
            print("Press Ctrl+C to stop")
            tester = SMSAPITester()
            try:
                while True:
                    messages = tester.test_get_messages()
                    if messages:
                        print(f"\n📱 Found {len(messages)} messages:")
                        for msg in messages:
                            print(f"   {msg['sender']}: {msg['message']}")
                    else:
                        print(".", end="", flush=True)
                    time.sleep(5)
            except KeyboardInterrupt:
                print("\n✋ Monitoring stopped")
    else:
        # Full test suite
        tester = SMSAPITester()
        success = tester.run_full_test_suite()
        sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()