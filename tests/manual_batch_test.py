#!/usr/bin/env python
"""Manual test script for batch logging and graceful shutdown.

This script demonstrates:
1. Batch logging with high batch_size
2. Graceful shutdown that flushes pending logs
3. Verification that all logs are written

Usage:
    1. Start middleware with high batch settings in config.yaml:
       logging:
         batch_size: 50
         batch_timeout: 10.0
    
    2. Run this script: python tests/manual_batch_test.py
    
    3. Send Ctrl+C after a few requests to test graceful shutdown
    
    4. Check logs directory for written entries
"""

import time
import sys
from pathlib import Path

import httpx


def test_batch_logging_and_graceful_shutdown():
    """Test batch logging with graceful shutdown."""
    
    # Configuration
    middleware_url = "http://localhost:8000"
    api_key = "test-local-key-12345"  # Update with your key
    deployment = "gpt-4.1-nano"  # Update with your deployment
    
    print("=" * 70)
    print("Batch Logging and Graceful Shutdown Test")
    print("=" * 70)
    print(f"\nMiddleware URL: {middleware_url}")
    print(f"Deployment: {deployment}")
    print(f"\nThis test will:")
    print("1. Send several API requests (< batch_size)")
    print("2. Wait briefly (< batch_timeout)")
    print("3. Press Ctrl+C to test graceful shutdown")
    print("4. Verify all logs were flushed to disk")
    print("\n" + "=" * 70 + "\n")
    
    # Check server is running
    try:
        response = httpx.get(f"{middleware_url}/health", timeout=5.0)
        if response.status_code != 200:
            print(f"ERROR: Server not healthy (status {response.status_code})")
            return 1
        print("✓ Server is running and healthy")
    except httpx.ConnectError:
        print(f"ERROR: Cannot connect to {middleware_url}")
        print("Please start the middleware server first:")
        print("  python -m azure_middleware")
        return 1
    
    # Get initial log count
    logs_dir = Path("logs")
    initial_log_count = count_log_entries(logs_dir)
    print(f"✓ Initial log entries: {initial_log_count}")
    
    # Send requests
    num_requests = 5  # Less than typical batch_size
    print(f"\nSending {num_requests} requests...")
    
    client = httpx.Client(
        base_url=middleware_url,
        headers={"api-key": api_key},
        timeout=30.0,
    )
    
    request_ids = []
    for i in range(num_requests):
        try:
            response = client.post(
                f"/openai/deployments/{deployment}/chat/completions",
                json={
                    "messages": [
                        {"role": "user", "content": f"Test message {i+1}"}
                    ],
                    "max_tokens": 10,
                    "stream": False,
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                request_id = data.get("id", f"request-{i+1}")
                request_ids.append(request_id)
                print(f"  ✓ Request {i+1}/{num_requests} completed: {request_id}")
            else:
                print(f"  ✗ Request {i+1} failed: {response.status_code}")
                print(f"    {response.text}")
        
        except Exception as e:
            print(f"  ✗ Request {i+1} error: {e}")
    
    client.close()
    
    print(f"\n✓ Sent {len(request_ids)} successful requests")
    print(f"\nNow testing graceful shutdown...")
    print(f"The logs are in memory (not yet written to disk).")
    print(f"\nPress Ctrl+C to trigger graceful shutdown.")
    print(f"The server should flush all {len(request_ids)} logs before exiting.\n")
    
    # Wait for user to press Ctrl+C
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\nCtrl+C received! Server should be shutting down gracefully...")
        print("Waiting 3 seconds for shutdown to complete...")
        time.sleep(3)
    
    # Verify logs were written
    print("\nVerifying logs were flushed...")
    final_log_count = count_log_entries(logs_dir)
    new_entries = final_log_count - initial_log_count
    
    print(f"  Initial log entries: {initial_log_count}")
    print(f"  Final log entries:   {final_log_count}")
    print(f"  New entries:         {new_entries}")
    print(f"  Expected:            {len(request_ids)}")
    
    if new_entries >= len(request_ids):
        print("\n✓ SUCCESS: All logs were flushed on graceful shutdown!")
        return 0
    else:
        print(f"\n✗ FAILURE: Only {new_entries}/{len(request_ids)} logs were written")
        print("  This suggests the graceful shutdown did not complete properly.")
        return 1


def count_log_entries(logs_dir: Path) -> int:
    """Count total log entries in all JSONL files."""
    if not logs_dir.exists():
        return 0
    
    total = 0
    for log_file in logs_dir.rglob("*.jsonl"):
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                total += sum(1 for line in f if line.strip())
        except Exception:
            pass
    
    return total


def test_forced_termination():
    """Test that forced termination loses logs (for comparison)."""
    print("\n" + "=" * 70)
    print("Forced Termination Test (for comparison)")
    print("=" * 70)
    print("\nThis test demonstrates that forced termination (kill -9, taskkill)")
    print("will lose in-memory logs, unlike graceful shutdown.")
    print("\nNOTE: This test requires manually killing the server process.")
    print("      Not recommended for automated testing.")
    print("\n" + "=" * 70)


if __name__ == "__main__":
    print("\nBatch Logging and Graceful Shutdown Test")
    print("=" * 70)
    print("\nPrerequisites:")
    print("1. Start middleware with HIGH batch settings:")
    print("   logging:")
    print("     batch_size: 50")
    print("     batch_timeout: 10.0")
    print("2. Ensure server is running: python -m azure_middleware")
    print("3. Update api_key and deployment in this script")
    print()
    
    input("Press Enter when ready to start test (or Ctrl+C to exit)...")
    
    exit_code = test_batch_logging_and_graceful_shutdown()
    
    print("\n" + "=" * 70)
    print("Test Complete!")
    print("=" * 70)
    
    sys.exit(exit_code)
