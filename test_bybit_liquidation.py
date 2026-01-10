import requests

def test_bybit_liq():
    symbol = "BTCUSDT"
    base_url = "https://api.bybit.com"
    
    print("--- Testing Bybit Liquidation ---")
    url = f"{base_url}/v5/market/liquidation"
    params = {
        "category": "linear",
        "symbol": symbol,
        "limit": 20
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=5).json()
        print(f"Bybit Liquidation: {resp}")
    except Exception as e:
        print(f"Bybit Error: {e}")

if __name__ == "__main__":
    test_bybit_liq()
