#!/usr/bin/env python3
"""
SMS Manager API Load Testing Script
Performance and stress testing for the SMS API
"""

import requests
import time
import threading
import statistics
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import json

# Configuration
API_BASE_URL = "http://localhost:8000"
TEST_PHONE_NUMBER = "+264816828893"

class LoadTester:
    """Load testing for SMS Manager API"""
    
    def __init__(self, base_url: str = API_BASE_URL, test_phone: str = TEST_PHONE_NUMBER):
        self.base_url = base_url
        self.test_phone = test_phone
        self.results = []
        
    def send_single_sms(self, message_id: int) -> dict:
        """Send a single SMS and measure response time"""
        start_time = time.time()
        
        try:
            data = {
                "phone_number": self.test_phone,
                "message": f"Load test message #{message_id} - {datetime.now().strftime('%H:%M:%S')}"
            }
            
            response = requests.post(f"{self.base_url}/send", json=data, timeout=30)
            end_time = time.time()
            
            return {
                "message_id": message_id,
                "success": response.status_code == 200,
                "response_time": end_time - start_time,
                "status_code": response.status_code,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            end_time = time.time()
            return {
                "message_id": message_id,
                "success": False,
                "response_time": end_time - start_time,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    def sequential_load_test(self, num_messages: int = 10, delay: float = 1.0):
        """Send messages sequentially with delay"""
        print(f"📤 Sequential Load Test: {num_messages} messages, {delay}s delay")
        print("-" * 50)
        
        results = []
        start_time = time.time()
        
        for i in range(1, num_messages + 1):
            print(f"Sending message {i}/{num_messages}...")
            result = self.send_single_sms(i)
            results.append(result)
            
            status = "✅" if result["success"] else "❌"
            print(f"  {status} Message {i}: {result['response_time']:.2f}s")
            
            if i < num_messages:
                time.sleep(delay)
        
        total_time = time.time() - start_time
        self.analyze_results("Sequential Test", results, total_time)
        return results
    
    def concurrent_load_test(self, num_messages: int = 5, max_workers: int = 3):
        """Send messages concurrently using thread pool"""
        print(f"🚀 Concurrent Load Test: {num_messages} messages, {max_workers} workers")
        print("-" * 50)
        
        results = []
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_id = {
                executor.submit(self.send_single_sms, i): i 
                for i in range(1, num_messages + 1)
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_id):
                message_id = future_to_id[future]
                try:
                    result = future.result()
                    results.append(result)
                    
                    status = "✅" if result["success"] else "❌"
                    print(f"  {status} Message {message_id}: {result['response_time']:.2f}s")
                    
                except Exception as e:
                    print(f"  ❌ Message {message_id}: Exception {e}")
                    results.append({
                        "message_id": message_id,
                        "success": False,
                        "error": str(e),
                        "response_time": 0,
                        "timestamp": datetime.now().isoformat()
                    })
        
        total_time = time.time() - start_time
        self.analyze_results("Concurrent Test", results, total_time)
        return results
    
    def stress_test(self, duration: int = 30, interval: float = 0.5):
        """Send messages continuously for specified duration"""
        print(f"⚡ Stress Test: {duration} seconds, {interval}s interval")
        print("-" * 50)
        
        results = []
        start_time = time.time()
        message_count = 0
        
        while time.time() - start_time < duration:
            message_count += 1
            print(f"Sending message {message_count}...")
            
            result = self.send_single_sms(message_count)
            results.append(result)
            
            status = "✅" if result["success"] else "❌"
            print(f"  {status} {result['response_time']:.2f}s")
            
            time.sleep(interval)
        
        total_time = time.time() - start_time
        self.analyze_results("Stress Test", results, total_time)
        return results
    
    def api_health_test(self, num_requests: int = 20):
        """Test API health endpoints under load"""
        print(f"🏥 API Health Test: {num_requests} status requests")
        print("-" * 50)
        
        results = []
        start_time = time.time()
        
        for i in range(1, num_requests + 1):
            request_start = time.time()
            try:
                response = requests.get(f"{self.base_url}/status", timeout=10)
                request_time = time.time() - request_start
                
                result = {
                    "request_id": i,
                    "success": response.status_code == 200,
                    "response_time": request_time,
                    "status_code": response.status_code
                }
                
                if response.status_code == 200:
                    data = response.json()
                    result["connected"] = data.get("connected", False)
                    result["listening"] = data.get("listening", False)
                
            except Exception as e:
                request_time = time.time() - request_start
                result = {
                    "request_id": i,
                    "success": False,
                    "response_time": request_time,
                    "error": str(e)
                }
            
            results.append(result)
            status = "✅" if result["success"] else "❌"
            print(f"  {status} Request {i}: {result['response_time']:.3f}s")
        
        total_time = time.time() - start_time
        self.analyze_health_results("Health Test", results, total_time)
        return results
    
    def analyze_results(self, test_name: str, results: list, total_time: float):
        """Analyze and display test results"""
        if not results:
            print("No results to analyze")
            return
        
        successful = [r for r in results if r.get("success", False)]
        failed = [r for r in results if not r.get("success", False)]
        response_times = [r["response_time"] for r in successful]
        
        print(f"\n📊 {test_name} Results:")
        print("-" * 30)
        print(f"Total Messages: {len(results)}")
        print(f"Successful: {len(successful)}")
        print(f"Failed: {len(failed)}")
        print(f"Success Rate: {len(successful)/len(results)*100:.1f}%")
        print(f"Total Time: {total_time:.2f}s")
        print(f"Messages/Second: {len(results)/total_time:.2f}")
        
        if response_times:
            print(f"\nResponse Time Stats:")
            print(f"  Average: {statistics.mean(response_times):.2f}s")
            print(f"  Median: {statistics.median(response_times):.2f}s")
            print(f"  Min: {min(response_times):.2f}s")
            print(f"  Max: {max(response_times):.2f}s")
            if len(response_times) > 1:
                print(f"  Std Dev: {statistics.stdev(response_times):.2f}s")
        
        if failed:
            print(f"\nFailed Requests:")
            for failure in failed[:5]:  # Show first 5 failures
                error = failure.get("error", f"HTTP {failure.get('status_code', 'Unknown')}")
                print(f"  Message {failure['message_id']}: {error}")
    
    def analyze_health_results(self, test_name: str, results: list, total_time: float):
        """Analyze health test results"""
        if not results:
            print("No results to analyze")
            return
        
        successful = [r for r in results if r.get("success", False)]
        response_times = [r["response_time"] for r in successful]
        
        print(f"\n📊 {test_name} Results:")
        print("-" * 30)
        print(f"Total Requests: {len(results)}")
        print(f"Successful: {len(successful)}")
        print(f"Success Rate: {len(successful)/len(results)*100:.1f}%")
        print(f"Average Response Time: {statistics.mean(response_times):.3f}s" if response_times else "N/A")
        print(f"Requests/Second: {len(results)/total_time:.2f}")
    
    def run_full_load_test_suite(self):
        """Run complete load testing suite"""
        print("🔥 SMS Manager API - Load Test Suite")
        print("=" * 60)
        print(f"Target API: {self.base_url}")
        print(f"Test Phone: {self.test_phone}")
        print("=" * 60)
        
        all_results = {}
        
        # Test 1: API Health Check
        print("\n1. API Health Test")
        all_results["health"] = self.api_health_test(10)
        
        # Test 2: Sequential Load Test  
        print("\n2. Sequential Load Test")
        all_results["sequential"] = self.sequential_load_test(5, 2.0)
        
        # Test 3: Concurrent Load Test
        print("\n3. Concurrent Load Test")
        all_results["concurrent"] = self.concurrent_load_test(3, 2)
        
        # Test 4: Stress Test (shorter for demo)
        print("\n4. Stress Test")
        all_results["stress"] = self.stress_test(15, 1.0)
        
        # Save results
        self.save_results(all_results)
        print(f"\n💾 Results saved to load_test_results.json")
    
    def save_results(self, all_results: dict):
        """Save test results to JSON file"""
        output = {
            "timestamp": datetime.now().isoformat(),
            "configuration": {
                "api_url": self.base_url,
                "test_phone": self.test_phone
            },
            "results": all_results
        }
        
        with open("load_test_results.json", "w") as f:
            json.dump(output, f, indent=2)

def main():
    """Main execution"""
    import sys
    
    tester = LoadTester()
    
    if len(sys.argv) > 1:
        test_type = sys.argv[1].lower()
        
        if test_type == "sequential":
            count = int(sys.argv[2]) if len(sys.argv) > 2 else 5
            delay = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
            tester.sequential_load_test(count, delay)
            
        elif test_type == "concurrent":
            count = int(sys.argv[2]) if len(sys.argv) > 2 else 3
            workers = int(sys.argv[3]) if len(sys.argv) > 3 else 2
            tester.concurrent_load_test(count, workers)
            
        elif test_type == "stress":
            duration = int(sys.argv[2]) if len(sys.argv) > 2 else 30
            interval = float(sys.argv[3]) if len(sys.argv) > 3 else 0.5
            tester.stress_test(duration, interval)
            
        elif test_type == "health":
            count = int(sys.argv[2]) if len(sys.argv) > 2 else 20
            tester.api_health_test(count)
            
        else:
            print("Usage:")
            print("  python3 load_test_sms_api.py sequential [count] [delay]")
            print("  python3 load_test_sms_api.py concurrent [count] [workers]") 
            print("  python3 load_test_sms_api.py stress [duration] [interval]")
            print("  python3 load_test_sms_api.py health [requests]")
            print("  python3 load_test_sms_api.py  # Full suite")
    else:
        # Run full test suite
        tester.run_full_load_test_suite()

if __name__ == "__main__":
    main()