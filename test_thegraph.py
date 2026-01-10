import requests
import json

def test_thegraph():
    url = "https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v3"
    query = """
    {
      factories(first: 1) {
        totalValueLockedUSD
      }
      uniswapDayDatas(first: 8, orderBy: date, orderDirection: desc) {
        date
        tvlUSD
      }
    }
    """
    
    print(f"Querying {url}...")
    try:
        resp = requests.post(url, json={'query': query}, timeout=10)
        data = resp.json()
        
        if 'data' in data:
            print("Success!")
            print(json.dumps(data, indent=2))
            
            # Parse data
            day_datas = data['data']['uniswapDayDatas']
            if len(day_datas) >= 2:
                current_tvl = float(day_datas[0]['tvlUSD'])
                prev_tvl = float(day_datas[1]['tvlUSD'])
                change_24h = (current_tvl - prev_tvl) / prev_tvl * 100
                print(f"Current TVL: ${current_tvl:,.2f}")
                print(f"24H Change: {change_24h:.2f}%")
        else:
            print("Error in response:", data)
            
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    test_thegraph()
