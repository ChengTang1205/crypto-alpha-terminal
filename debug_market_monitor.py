import requests
import ccxt
import pandas as pd
import numpy as np

def debug_deribit():
    print("\n--- Debugging Deribit ---")
    url = "https://www.deribit.com/api/v2/public/get_volatility_index_data"
    params = {"currency": "BTC", "resolution": "1D"}
    try:
        resp = requests.get(url, params=params).json()
        print(f"Response Keys: {resp.keys()}")
        if 'result' in resp:
            print(f"Result Keys: {resp['result'].keys()}")
            if 'data' in resp['result']:
                data = resp['result']['data']
                print(f"Data Length: {len(data)}")
                if data:
                    print(f"Latest Data Point: {data[-1]}")
            else:
                print("No 'data' in result")
        else:
            print("No 'result' in response")
    except Exception as e:
        print(f"Error: {e}")

def debug_defillama():
    print("\n--- Debugging DefiLlama ---")
    url = "https://api.llama.fi/protocol/uniswap-v3"
    try:
        resp = requests.get(url).json()
        print(f"Response Keys: {resp.keys()}")
        
        if 'tvl' in resp:
            tvl_data = resp['tvl']
            print(f"TVL Data Length: {len(tvl_data)}")
            if tvl_data:
                print(f"Latest TVL Point: {tvl_data[-1]}")
                print(f"Previous TVL Point: {tvl_data[-2]}")
        elif 'chainTvls' in resp:
             print(f"chainTvls Keys: {resp['chainTvls'].keys()}")
             if 'Ethereum' in resp['chainTvls']:
                 eth_tvl = resp['chainTvls']['Ethereum']['tvl']
                 print(f"Ethereum TVL Length: {len(eth_tvl)}")
                 if eth_tvl:
                     print(f"Latest ETH TVL: {eth_tvl[-1]}")
        else:
            print("No 'tvl' or 'chainTvls' found")
            
    except Exception as e:
        print(f"Error: {e}")

def debug_binance_slippage():
    print("\n--- Debugging Binance Slippage ---")
    exchange = ccxt.binance({'enableRateLimit': True})
    symbol = 'BTC/USDT'
    try:
        book = exchange.fetch_order_book(symbol, limit=500)
        mid_price = (book['bids'][0][0] + book['asks'][0][0]) / 2
        print(f"Mid Price: {mid_price}")
        
        target_amount = 100000
        cost = 0
        filled_qty = 0
        
        print("Simulating Buy...")
        for i, (price, qty) in enumerate(book['asks']):
            if cost + (price * qty) >= target_amount:
                needed = (target_amount - cost) / price
                filled_qty += needed
                cost += needed * price
                print(f"Order {i}: Price {price}, Taken {needed:.4f} (Partial), Total Cost {cost:.2f}")
                break
            else:
                cost += price * qty
                filled_qty += qty
                # print(f"Order {i}: Price {price}, Taken {qty:.4f}, Total Cost {cost:.2f}")
        
        avg_price = cost / filled_qty
        slippage = (avg_price - mid_price) / mid_price * 100
        print(f"Avg Price: {avg_price}")
        print(f"Slippage: {slippage:.6f}%")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_deribit()
    debug_defillama()
    debug_binance_slippage()
