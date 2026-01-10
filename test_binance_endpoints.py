import requests
import ccxt

def test_endpoints():
    symbol = "BTCUSDT"
    base_url = "https://fapi.binance.com"
    headers = {"User-Agent": "Mozilla/5.0"}

    print("--- Testing L/S Ratio ---")
    # 1. Global L/S (Current implementation)
    url_global = f"{base_url}/fapi/v1/globalLongShortAccountRatio"
    params = {"symbol": symbol, "period": "5m", "limit": 1}
    try:
        resp = requests.get(url_global, params=params, headers=headers).json()
        print(f"Global L/S: {resp}")
    except Exception as e:
        print(f"Global L/S Error: {e}")

    # 2. Top Traders L/S (Alternative)
    url_top = f"{base_url}/fapi/v1/topLongShortAccountRatio"
    try:
        resp = requests.get(url_top, params=params, headers=headers).json()
        print(f"Top Traders L/S: {resp}")
    except Exception as e:
        print(f"Top Traders L/S Error: {e}")

    # 3. Top Traders Position L/S
    url_top_pos = f"{base_url}/fapi/v1/topLongShortPositionRatio"
    try:
        resp = requests.get(url_top_pos, params=params, headers=headers).json()
        print(f"Top Traders Position L/S: {resp}")
    except Exception as e:
        print(f"Top Traders Position L/S Error: {e}")

    print("\n--- Testing Liquidations ---")
    # 1. Force Orders (Current implementation)
    url_force = f"{base_url}/fapi/v1/forceOrders"
    params_liq = {"symbol": symbol, "limit": 5}
    try:
        resp = requests.get(url_force, params=params_liq, headers=headers).json()
        print(f"Force Orders: {resp}")
    except Exception as e:
        print(f"Force Orders Error: {e}")

    # 2. Ticker 24h (Might have liquidation info? Unlikely but checking)
    url_ticker = f"{base_url}/fapi/v1/ticker/24hr"
    try:
        resp = requests.get(url_ticker, params={"symbol": symbol}, headers=headers).json()
        print(f"Ticker 24h keys: {resp.keys() if isinstance(resp, dict) else 'List'}")
    except Exception as e:
        print(f"Ticker Error: {e}")

if __name__ == "__main__":
    test_endpoints()
