import requests

def test_bybit():
    symbol = "BTCUSDT"
    base_url = "https://api.bybit.com"
    
    print("--- Testing Bybit L/S Ratio ---")
    url = f"{base_url}/v5/market/account-ratio"
    params = {
        "category": "linear",
        "symbol": symbol,
        "period": "5min",
        "limit": 1
    }
    try:
        resp = requests.get(url, params=params).json()
        print(f"Bybit L/S: {resp}")
    except Exception as e:
        print(f"Bybit Error: {e}")

if __name__ == "__main__":
    test_bybit()
