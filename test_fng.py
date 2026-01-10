import requests
import json
from datetime import datetime

def test_fng():
    url = "https://api.alternative.me/fng/?limit=1"
    print(f"Fetching {url}...")
    try:
        response = requests.get(url, timeout=10)
        print(f"Status Code: {response.status_code}")
        data = response.json()
        print(json.dumps(data, indent=2))
        
        if data['data']:
            item = data['data'][0]
            print(f"Value: {item['value']}")
            print(f"Status: {item['value_classification']}")
            print(f"Time: {datetime.fromtimestamp(int(item['timestamp']))}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_fng()
