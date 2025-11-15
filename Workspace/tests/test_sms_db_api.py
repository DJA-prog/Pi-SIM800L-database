#!/usr/bin/env python3
"""
Comprehensive Automated Test Suite for SIM800L SMS Manager API with Database
Tests all endpoints including database operations, filtering, and hardware monitoring
"""

import requests
import json
import time
import sys
from datetime import datetime, timedelta
from typing import Dict, Any, List

class SMSManagerDatabaseTester:
    """Comprehensive test suite for SMS Manager API with database features"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session = requests.Session()
        self.test_results = {
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "errors": [],
            "timestamp": datetime.now().isoformat()
        }
        
    def log_result(self, test_name: str, success: bool, details: str = ""):
        """Log test result"""
        self.test_results["total_tests"] += 1
        if success:
            self.test_results["passed"] += 1
            print(f"✓ {test_name}")
        else:
            self.test_results["failed"] += 1
            self.test_results["errors"].append({
                "test": test_name,
                "details": details,
                "timestamp": datetime.now().isoformat()
            })
            print(f"✗ {test_name} - {details}")
    
    def test_api_availability(self) -> bool:
        """Test if API is available"""
        try:
            response = self.session.get(f"{self.base_url}/")
            success = response.status_code == 200
            self.log_result("API Availability", success, 
                          f"Status code: {response.status_code}" if not success else "")
            return success
        except Exception as e:
            self.log_result("API Availability", False, str(e))
            return False
    
    def test_status_endpoint(self) -> Dict[str, Any]:
        """Test status endpoint with hardware monitoring"""
        try:
            response = self.session.get(f"{self.base_url}/status")
            if response.status_code == 200:
                status_data = response.json()
                
                # Check required fields
                required_fields = ["connected", "listening", "timestamp"]
                hardware_fields = ["battery_voltage", "signal_strength", "message_counts"]
                
                for field in required_fields:
                    if field not in status_data:
                        self.log_result("Status Endpoint - Required Fields", False, f"Missing field: {field}")
                        return status_data
                
                # Check hardware fields (can be None)
                has_hardware = all(field in status_data for field in hardware_fields)
                self.log_result("Status Endpoint - Hardware Fields", has_hardware)
                
                # Check message counts structure
                if "message_counts" in status_data and isinstance(status_data["message_counts"], dict):
                    counts = status_data["message_counts"]
                    has_counts = "sms_messages" in counts and "system_messages" in counts
                    self.log_result("Status Endpoint - Message Counts", has_counts)
                
                self.log_result("Status Endpoint", True)
                return status_data
            else:
                self.log_result("Status Endpoint", False, f"Status code: {response.status_code}")
                return {}
        except Exception as e:
            self.log_result("Status Endpoint", False, str(e))
            return {}
    
    def test_send_sms(self, test_message: str = "Automated test SMS with database") -> bool:
        """Test sending SMS"""
        try:
            payload = {
                "phone_number": "+1234567890",
                "message": test_message
            }
            
            response = self.session.post(f"{self.base_url}/send", json=payload)
            success = response.status_code == 200
            
            if success:
                data = response.json()
                success = data.get("success", False)
            
            self.log_result("Send SMS", success, 
                          f"Response: {response.text}" if not success else "")
            return success
        except Exception as e:
            self.log_result("Send SMS", False, str(e))
            return False
    
    def test_database_sms_operations(self) -> bool:
        """Test database SMS operations"""
        try:
            # Test getting all SMS messages
            response = self.session.get(f"{self.base_url}/db/sms")
            if response.status_code != 200:
                self.log_result("Database SMS - Get All", False, f"Status: {response.status_code}")
                return False
            
            sms_data = response.json()
            has_structure = "messages" in sms_data and "count" in sms_data
            self.log_result("Database SMS - Get All", has_structure)
            
            # Test with filters
            yesterday = (datetime.now() - timedelta(days=1)).isoformat()
            
            # Date filter test
            response = self.session.get(f"{self.base_url}/db/sms", 
                                      params={"start_date": yesterday, "limit": 10})
            success = response.status_code == 200
            self.log_result("Database SMS - Date Filter", success)
            
            # Sender filter test
            response = self.session.get(f"{self.base_url}/db/sms", 
                                      params={"sender": "+123", "limit": 5})
            success = response.status_code == 200
            self.log_result("Database SMS - Sender Filter", success)
            
            # Keyword filter test
            response = self.session.get(f"{self.base_url}/db/sms", 
                                      params={"keyword": "test", "limit": 5})
            success = response.status_code == 200
            self.log_result("Database SMS - Keyword Filter", success)
            
            return True
        except Exception as e:
            self.log_result("Database SMS Operations", False, str(e))
            return False
    
    def test_database_system_operations(self) -> bool:
        """Test database system message operations"""
        try:
            # Test getting all system messages
            response = self.session.get(f"{self.base_url}/db/system")
            if response.status_code != 200:
                self.log_result("Database System - Get All", False, f"Status: {response.status_code}")
                return False
            
            system_data = response.json()
            has_structure = "messages" in system_data and "count" in system_data
            self.log_result("Database System - Get All", has_structure)
            
            # Test with filters
            yesterday = (datetime.now() - timedelta(days=1)).isoformat()
            
            # Date filter test
            response = self.session.get(f"{self.base_url}/db/system", 
                                      params={"start_date": yesterday, "limit": 10})
            success = response.status_code == 200
            self.log_result("Database System - Date Filter", success)
            
            # Keyword filter test
            response = self.session.get(f"{self.base_url}/db/system", 
                                      params={"keyword": "SMSManager", "limit": 5})
            success = response.status_code == 200
            self.log_result("Database System - Keyword Filter", success)
            
            return True
        except Exception as e:
            self.log_result("Database System Operations", False, str(e))
            return False
    
    def test_database_stats(self) -> bool:
        """Test database statistics endpoint"""
        try:
            response = self.session.get(f"{self.base_url}/db/stats")
            if response.status_code != 200:
                self.log_result("Database Statistics", False, f"Status: {response.status_code}")
                return False
            
            stats_data = response.json()
            required_fields = ["total_counts", "recent_24h", "database_path"]
            
            for field in required_fields:
                if field not in stats_data:
                    self.log_result("Database Statistics", False, f"Missing field: {field}")
                    return False
            
            # Check structure of counts
            if "sms_messages" not in stats_data["total_counts"]:
                self.log_result("Database Statistics", False, "Missing SMS count")
                return False
            
            self.log_result("Database Statistics", True)
            return True
        except Exception as e:
            self.log_result("Database Statistics", False, str(e))
            return False
    
    def test_deletion_operations(self) -> bool:
        """Test message deletion operations (non-destructive tests)"""
        try:
            # Test deleting non-existent SMS message (should return 404)
            response = self.session.delete(f"{self.base_url}/db/sms/99999")
            expected_404 = response.status_code == 404
            self.log_result("Delete SMS - Non-existent", expected_404)
            
            # Test deleting non-existent system message (should return 404)
            response = self.session.delete(f"{self.base_url}/db/system/99999")
            expected_404 = response.status_code == 404
            self.log_result("Delete System - Non-existent", expected_404)
            
            # Test bulk delete with empty array
            response = self.session.delete(f"{self.base_url}/db/sms/bulk", 
                                         json={"message_ids": []})
            success = response.status_code == 200
            self.log_result("Bulk Delete SMS - Empty Array", success)
            
            # Test bulk delete system messages with empty array
            response = self.session.delete(f"{self.base_url}/db/system/bulk", 
                                         json={"message_ids": []})
            success = response.status_code == 200
            self.log_result("Bulk Delete System - Empty Array", success)
            
            return True
        except Exception as e:
            self.log_result("Deletion Operations", False, str(e))
            return False
    
    def test_control_endpoints(self) -> bool:
        """Test control endpoints"""
        try:
            # Test start listening
            response = self.session.post(f"{self.base_url}/start-listening")
            success = response.status_code == 200
            self.log_result("Start Listening", success)
            
            time.sleep(1)  # Brief pause
            
            # Test stop listening
            response = self.session.post(f"{self.base_url}/stop-listening")
            success = response.status_code == 200
            self.log_result("Stop Listening", success)
            
            return True
        except Exception as e:
            self.log_result("Control Endpoints", False, str(e))
            return False
    
    def test_error_handling(self) -> bool:
        """Test error handling for invalid requests"""
        try:
            # Test invalid SMS request
            invalid_payload = {"phone_number": "", "message": ""}
            response = self.session.post(f"{self.base_url}/send", json=invalid_payload)
            # Should either reject or handle gracefully
            handled = response.status_code in [400, 422, 500, 200]
            self.log_result("Error Handling - Invalid SMS", handled)
            
            # Test invalid filter parameters
            response = self.session.get(f"{self.base_url}/db/sms", 
                                      params={"start_date": "invalid-date"})
            # Should handle gracefully
            handled = response.status_code in [400, 422, 200]
            self.log_result("Error Handling - Invalid Date", handled)
            
            return True
        except Exception as e:
            self.log_result("Error Handling", False, str(e))
            return False
    
    def test_unicode_support(self) -> bool:
        """Test Unicode and special character support"""
        try:
            # Test SMS with special characters
            unicode_message = "Test with émojis 🚀📱💾 and spëcial chars"
            payload = {
                "phone_number": "+1234567890",
                "message": unicode_message
            }
            
            response = self.session.post(f"{self.base_url}/send", json=payload)
            success = response.status_code == 200
            self.log_result("Unicode Support - SMS", success)
            
            # Test keyword search with special characters
            response = self.session.get(f"{self.base_url}/db/sms", 
                                      params={"keyword": "émojis", "limit": 5})
            success = response.status_code == 200
            self.log_result("Unicode Support - Search", success)
            
            return True
        except Exception as e:
            self.log_result("Unicode Support", False, str(e))
            return False
    
    def run_quick_test(self) -> Dict[str, Any]:
        """Run essential tests only"""
        print("🧪 Running Quick Test Suite for SMS Manager API with Database")
        print("="*70)
        
        if not self.test_api_availability():
            print("❌ API not available, stopping tests")
            return self.test_results
        
        # Essential tests
        self.test_status_endpoint()
        self.test_database_sms_operations()
        self.test_database_system_operations()
        self.test_database_stats()
        
        self.print_summary()
        return self.test_results
    
    def run_full_test(self) -> Dict[str, Any]:
        """Run comprehensive test suite"""
        print("🧪 Running Full Test Suite for SMS Manager API with Database")
        print("="*70)
        
        if not self.test_api_availability():
            print("❌ API not available, stopping tests")
            return self.test_results
        
        # Core functionality tests
        status_data = self.test_status_endpoint()
        self.test_send_sms()
        
        # Database operation tests
        self.test_database_sms_operations()
        self.test_database_system_operations()
        self.test_database_stats()
        
        # Advanced feature tests
        self.test_deletion_operations()
        self.test_control_endpoints()
        self.test_error_handling()
        self.test_unicode_support()
        
        self.print_summary()
        return self.test_results
    
    def run_monitor_test(self) -> Dict[str, Any]:
        """Run monitoring tests (hardware status, signal, battery)"""
        print("📊 Running Hardware Monitor Test Suite")
        print("="*50)
        
        if not self.test_api_availability():
            print("❌ API not available, stopping tests")
            return self.test_results
        
        # Monitor hardware status multiple times
        for i in range(3):
            print(f"📡 Hardware Status Check {i+1}/3")
            status_data = self.test_status_endpoint()
            
            if status_data:
                print(f"   Battery: {status_data.get('battery_voltage', 'N/A')}V")
                print(f"   Signal:  {status_data.get('signal_strength', 'N/A')}%")
                print(f"   Connected: {status_data.get('connected', False)}")
                print(f"   Listening: {status_data.get('listening', False)}")
                
                if status_data.get('message_counts'):
                    counts = status_data['message_counts']
                    print(f"   SMS Messages: {counts.get('sms_messages', 0)}")
                    print(f"   System Messages: {counts.get('system_messages', 0)}")
                
            if i < 2:  # Don't sleep after last iteration
                time.sleep(2)
        
        # Test database statistics
        self.test_database_stats()
        
        self.print_summary()
        return self.test_results
    
    def print_summary(self):
        """Print test summary"""
        total = self.test_results["total_tests"]
        passed = self.test_results["passed"]
        failed = self.test_results["failed"]
        
        print("\n" + "="*50)
        print("📋 Test Summary")
        print("="*50)
        print(f"Total Tests: {total}")
        print(f"Passed: ✓ {passed}")
        print(f"Failed: ✗ {failed}")
        
        if failed > 0:
            print(f"Success Rate: {(passed/total)*100:.1f}%")
            print("\n🚨 Failed Tests:")
            for error in self.test_results["errors"]:
                print(f"   • {error['test']}: {error['details']}")
        else:
            print("Success Rate: 100% 🎉")
        
        print("="*50)

def main():
    """Main function with command line interface"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Test SMS Manager API with Database')
    parser.add_argument('--url', default='http://localhost:8000', 
                       help='Base URL of the API (default: http://localhost:8000)')
    parser.add_argument('--mode', choices=['quick', 'full', 'monitor'], default='full',
                       help='Test mode: quick, full, or monitor (default: full)')
    parser.add_argument('--output', help='Output file for results (JSON format)')
    
    args = parser.parse_args()
    
    # Create tester instance
    tester = SMSManagerDatabaseTester(args.url)
    
    # Run tests based on mode
    if args.mode == 'quick':
        results = tester.run_quick_test()
    elif args.mode == 'monitor':
        results = tester.run_monitor_test()
    else:
        results = tester.run_full_test()
    
    # Save results if output file specified
    if args.output:
        try:
            with open(args.output, 'w') as f:
                json.dump(results, f, indent=2)
            print(f"\n💾 Results saved to: {args.output}")
        except Exception as e:
            print(f"\n❌ Failed to save results: {e}")
    
    # Exit with appropriate code
    sys.exit(0 if results["failed"] == 0 else 1)

if __name__ == "__main__":
    main()