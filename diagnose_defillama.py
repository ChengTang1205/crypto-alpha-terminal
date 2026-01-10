import requests
import socket
import subprocess
import sys

def check_dns():
    print("\n--- 1. DNS Resolution ---")
    try:
        ip = socket.gethostbyname("api.llama.fi")
        print(f"✅ Resolved api.llama.fi to {ip}")
    except Exception as e:
        print(f"❌ DNS Resolution Failed: {e}")

def check_curl():
    print("\n--- 2. Curl Test ---")
    try:
        # Try with 5s timeout
        cmd = ["curl", "-v", "--max-time", "5", "https://api.llama.fi/protocol/uniswap-v3"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ Curl Success!")
            print(f"Response snippet: {result.stdout[:100]}...")
        else:
            print(f"❌ Curl Failed (Code {result.returncode})")
            print(f"Error: {result.stderr}")
    except Exception as e:
        print(f"❌ Curl Execution Error: {e}")

def check_python_requests(use_proxy=False):
    label = "With Proxy" if use_proxy else "No Proxy"
    print(f"\n--- 3. Python Requests ({label}) ---")
    url = "https://api.llama.fi/protocol/uniswap-v3"
    proxies = {} if use_proxy else {"http": None, "https": None}
    
    try:
        resp = requests.get(url, proxies=proxies, timeout=5)
        print(f"✅ Status Code: {resp.status_code}")
        print(f"Response snippet: {resp.text[:100]}...")
    except Exception as e:
        print(f"❌ Request Failed: {e}")

if __name__ == "__main__":
    print("Starting DefiLlama Diagnostics...")
    check_dns()
    check_curl()
    check_python_requests(use_proxy=False)
    # check_python_requests(use_proxy=True) # Uncomment if you want to test system proxy
