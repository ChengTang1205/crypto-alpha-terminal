"""
Native Asset Tracker - BTC/ETH 原生资产追踪模块
==============================================
追踪 BTC 和 ETH 原生资产的鲸鱼持仓、大额转账等

数据来源:
- BTC: Blockchain.com API, BitInfoCharts
- ETH: Etherscan API, beaconcha.in

注意: BTC/ETH 不是 ERC-20 代币，需要不同的追踪方法
"""

import requests
import pandas as pd
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from termcolor import cprint

# ============================================================================
# 配置
# ============================================================================

# API Keys
ETHERSCAN_API_KEY = "QG8HRJJNIE7GZ72Y7PK8KK2695KQVWFS5T"

# API 端点
BLOCKCHAIN_API = "https://blockchain.info"
ETHERSCAN_API = "https://api.etherscan.io/v2/api"  # V2 API endpoint
BITINFOCHARTS_RICH = "https://bitinfocharts.com/top-100-richest-bitcoin-addresses.html"

# 已知的鲸鱼/交易所地址
# 已知的鲸鱼/交易所地址
KNOWN_BTC_WHALES = {
    # 交易所冷钱包 (Top 3)
    "34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo": "Binance Cold Wallet",
    "bc1qgdjqv0av3q56jvd82tkdjpy7gdp9ut8tlqmgrpmv24sq90ecnvqqjwvw97": "Bitfinex Cold Wallet",
    "3M219KR5vEneNb47ewrPfWyb5jQ2DjxRP6": "Binance Wallet",
    
    # 新兴巨鲸
    "37XuVSEpWW4pKfmNrW3jiQi7fGaamtauLi": "Robinhood Cold Wallet",
    "bc1qa5wkgaew2dkv56kfc68f4ks5ejp6thnv6yy7pf": "Mt.Gox / Trustee",
    
    # 远古巨鲸 (沉睡中)
    "1FeexV6bAHb8ybZjqQMjJrcCrHGW9sb6uF": "Old Whale (2011)",
    "1LdRcdxfbSnmCYYNdeYpUnztiYzVfBEQeC": "Old Whale (2014)",
    
    # 政府没收
    "bc1qf2yvj48mzkj7uf8lc2a9sa7w983qe256l5c8fs": "US Gov (Silk Road)",
}

KNOWN_ETH_WHALES = {
    # 交易所
    "0x28c6c06298d514db089934071355e5743bf21d60": "Binance 14",
    "0x21a31ee1afc51d94c2efccaa2092ad1028285549": "Binance 15",
    "0xdfd5293d8e347dfe59e90efd55b2956a1343963d": "Binance 16",
    "0x5a52e96bacdabb82fd05763e25335261b270efcb": "Binance 21",
    "0xf977814e90da44bfa03b6295a0616a897441acec": "Binance 8",
    "0xbe0eb53f46cd790cd13851d5eff43d12404d33e8": "Binance 7",
    "0x8103683202aa8da10536036edef04cdd865c225e": "Kraken 13",
    # Vitalik
    "0xd8da6bf26964af9d7eed9e03e53415d37aa96045": "vitalik.eth",
    # Lido
    "0xae7ab96520de3a18e5e111b5eaab095312d7fe84": "Lido stETH",
}


# ============================================================================
# 数据类
# ============================================================================

@dataclass
class WhaleTransaction:
    """大额转账记录"""
    tx_hash: str
    from_address: str
    to_address: str
    amount: float
    usd_value: float
    timestamp: datetime
    from_label: str = ""
    to_label: str = ""


@dataclass
class NativeAssetStats:
    """原生资产统计"""
    asset: str  # BTC or ETH
    total_supply: float
    circulating_supply: float
    top_10_pct: float
    top_100_pct: float
    exchange_reserve_pct: float
    recent_whale_txs: List[WhaleTransaction]


# ============================================================================
# BTC 追踪器
# ============================================================================

class BTCTracker:
    """Bitcoin 原生资产追踪"""
    
    def __init__(self):
        self.known_whales = KNOWN_BTC_WHALES
    
    def get_address_balance(self, address: str) -> Optional[float]:
        """获取 BTC 地址余额"""
        try:
            url = f"{BLOCKCHAIN_API}/balance?active={address}"
            resp = requests.get(url, timeout=10)
            data = resp.json()
            
            if address in data:
                satoshis = data[address]["final_balance"]
                return satoshis / 100_000_000  # Convert to BTC
            return None
        except Exception as e:
            cprint(f"[Error] BTC balance query: {e}", "red")
            return None
    
    def get_recent_large_txs(self, min_btc: float = 100) -> List[Dict]:
        """
        获取最近的大额 BTC 交易
        使用 Blockchain.com Latest Blocks API
        """
        large_txs = []
        
        try:
            # 获取最新区块
            url = f"{BLOCKCHAIN_API}/latestblock"
            resp = requests.get(url, timeout=10)
            latest = resp.json()
            block_height = latest["height"]
            
            # 获取区块详情
            for i in range(3):  # 最近 3 个区块
                block_url = f"{BLOCKCHAIN_API}/rawblock/{block_height - i}"
                block_resp = requests.get(block_url, timeout=15)
                block = block_resp.json()
                
                for tx in block.get("tx", [])[:50]:  # 每个区块检查前 50 笔
                    total_out = sum(out.get("value", 0) for out in tx.get("out", []))
                    btc_value = total_out / 100_000_000
                    
                    if btc_value >= min_btc:
                        large_txs.append({
                            "hash": tx["hash"],
                            "btc": btc_value,
                            "time": datetime.fromtimestamp(tx["time"]),
                            "inputs": len(tx.get("inputs", [])),
                            "outputs": len(tx.get("out", []))
                        })
                
                if len(large_txs) >= 10:
                    break
                    
        except Exception as e:
            cprint(f"[Error] Fetching BTC large txs: {e}", "red")
        
        return large_txs[:10]
    
    def get_whale_balances(self) -> List[Dict]:
        """获取已知鲸鱼地址的当前余额"""
        results = []
        
        for address, label in self.known_whales.items():
            balance = self.get_address_balance(address)
            if balance is not None and balance > 1.0:  # 过滤掉余额过小的地址
                results.append({
                    "address": address[:20] + "...",
                    "label": label,
                    "balance_btc": balance
                })
        
        return sorted(results, key=lambda x: x["balance_btc"], reverse=True)
    
    def get_stats_from_api(self) -> Dict:
        """获取 BTC 统计数据 (使用 CoinGecko API)"""
        try:
            # 使用 CoinGecko API 获取 BTC 数据
            url = "https://api.coingecko.com/api/v3/coins/bitcoin"
            headers = {"accept": "application/json"}
            resp = requests.get(url, headers=headers, timeout=15)
            data = resp.json()
            
            market_data = data.get("market_data", {})
            
            return {
                "market_price_usd": market_data.get("current_price", {}).get("usd", 0),
                "total_btc": market_data.get("circulating_supply", 19_500_000),
                "n_tx_24h": market_data.get("total_volume", {}).get("usd", 0),  # 用交易量代替
                "market_cap": market_data.get("market_cap", {}).get("usd", 0),
                "price_change_24h": market_data.get("price_change_percentage_24h", 0),
                "ath": market_data.get("ath", {}).get("usd", 0)
            }
        except Exception as e:
            cprint(f"[Error] BTC stats: {e}", "red")
            return {}


# ============================================================================
# ETH 追踪器
# ============================================================================

class ETHTracker:
    """Ethereum 原生资产追踪"""
    
    def __init__(self, api_key: str = ETHERSCAN_API_KEY):
        self.api_key = api_key
        self.known_whales = KNOWN_ETH_WHALES
    
    def get_address_balance(self, address: str) -> Optional[float]:
        """获取 ETH 地址余额"""
        try:
            params = {
                "chainid": 1,
                "module": "account",
                "action": "balance",
                "address": address,
                "tag": "latest",
                "apikey": self.api_key
            }
            resp = requests.get(ETHERSCAN_API, params=params, timeout=10)
            data = resp.json()
            
            if data.get("status") == "1":
                wei = int(data["result"])
                return wei / 10**18  # Convert to ETH
            return None
        except Exception as e:
            cprint(f"[Error] ETH balance query: {e}", "red")
            return None
    
    def get_recent_large_txs(self, min_eth: float = 100, limit: int = 20) -> List[Dict]:
        """
        获取最近的大额 ETH 交易
        通过查询已知鲸鱼地址的最近交易
        """
        large_txs = []
        
        try:
            # 查询几个大鲸鱼地址的最近交易
            sample_whales = list(self.known_whales.keys())[:3]
            
            for whale_addr in sample_whales:
                params = {
                    "chainid": 1,
                    "module": "account",
                    "action": "txlist",
                    "address": whale_addr,
                    "startblock": 0,
                    "endblock": 99999999,
                    "page": 1,
                    "offset": 10,
                    "sort": "desc",
                    "apikey": self.api_key
                }
                resp = requests.get(ETHERSCAN_API, params=params, timeout=10)
                data = resp.json()
                
                if data.get("status") == "1":
                    for tx in data.get("result", []):
                        eth_value = int(tx.get("value", 0)) / 10**18
                        if eth_value >= min_eth:
                            from_label = self.known_whales.get(tx["from"].lower(), "")
                            to_label = self.known_whales.get(tx["to"].lower(), "") if tx.get("to") else ""
                            
                            large_txs.append({
                                "hash": tx["hash"][:20] + "...",
                                "from": tx["from"][:15] + "...",
                                "to": tx["to"][:15] + "..." if tx.get("to") else "Contract",
                                "eth": eth_value,
                                "from_label": from_label,
                                "to_label": to_label,
                                "time": datetime.fromtimestamp(int(tx["timeStamp"]))
                            })
                
                if len(large_txs) >= limit:
                    break
                    
        except Exception as e:
            cprint(f"[Error] Fetching ETH large txs: {e}", "red")
        
        # 去重并排序
        seen = set()
        unique_txs = []
        for tx in large_txs:
            if tx["hash"] not in seen:
                seen.add(tx["hash"])
                unique_txs.append(tx)
        
        return sorted(unique_txs, key=lambda x: x["eth"], reverse=True)[:limit]
    
    def get_whale_balances(self) -> List[Dict]:
        """获取已知鲸鱼地址的当前余额"""
        results = []
        
        for address, label in list(self.known_whales.items())[:10]:  # 限制 API 调用
            balance = self.get_address_balance(address)
            if balance is not None and balance > 1.0:  # 过滤掉余额过小的地址
                results.append({
                    "address": address[:20] + "...",
                    "label": label,
                    "balance_eth": balance
                })
        
        return sorted(results, key=lambda x: x["balance_eth"], reverse=True)
    
    def get_eth_supply(self) -> Dict:
        """获取 ETH 供应量数据"""
        try:
            params = {
                "chainid": 1,
                "module": "stats",
                "action": "ethsupply2",
                "apikey": self.api_key
            }
            resp = requests.get(ETHERSCAN_API, params=params, timeout=10)
            data = resp.json()
            
            if data.get("status") == "1":
                result = data["result"]
                return {
                    "total_supply": int(result.get("EthSupply", 0)) / 10**18,
                    "staked_supply": int(result.get("Eth2Staking", 0)) / 10**18,
                    "burnt_fees": int(result.get("BurntFees", 0)) / 10**18
                }
        except Exception as e:
            cprint(f"[Error] ETH supply: {e}", "red")
        return {}
    
    def get_gas_price(self) -> Dict:
        """获取当前 Gas 价格"""
        try:
            params = {
                "chainid": 1,
                "module": "gastracker",
                "action": "gasoracle",
                "apikey": self.api_key
            }
            resp = requests.get(ETHERSCAN_API, params=params, timeout=10)
            data = resp.json()
            
            if data.get("status") == "1":
                result = data["result"]
                return {
                    "safe": float(result.get("SafeGasPrice", 0)),
                    "propose": float(result.get("ProposeGasPrice", 0)),
                    "fast": float(result.get("FastGasPrice", 0))
                }
        except Exception:
            pass
        return {}


# ============================================================================
# 统一接口
# ============================================================================

def track_native_asset(asset: str = "ETH") -> Dict[str, Any]:
    """
    追踪原生资产 (BTC 或 ETH)
    """
    asset = asset.upper()
    
    if asset == "BTC":
        tracker = BTCTracker()
        
        cprint("\n🔍 追踪 BTC 原生资产...", "cyan")
        
        # 获取统计
        stats = tracker.get_stats_from_api()
        
        # 获取大额交易
        cprint("  📊 获取大额交易...", "white")
        large_txs = tracker.get_recent_large_txs(min_btc=100)
        
        # 获取鲸鱼余额
        cprint("  🐋 获取鲸鱼余额...", "white")
        whale_balances = tracker.get_whale_balances()
        
        return {
            "asset": "BTC",
            "stats": stats,
            "large_transactions": large_txs,
            "whale_balances": whale_balances,
            "price_usd": stats.get("market_price_usd", 0),
            "total_supply": stats.get("total_btc", 21_000_000),
            "known_whales": list(KNOWN_BTC_WHALES.values())
        }
    
    elif asset == "ETH":
        tracker = ETHTracker()
        
        cprint("\n🔍 追踪 ETH 原生资产...", "cyan")
        
        # 获取供应量
        supply = tracker.get_eth_supply()
        
        # 获取 Gas
        gas = tracker.get_gas_price()
        
        # 获取大额交易
        cprint("  📊 获取大额交易...", "white")
        large_txs = tracker.get_recent_large_txs(min_eth=100)
        
        # 获取鲸鱼余额
        cprint("  🐋 获取鲸鱼余额...", "white")
        whale_balances = tracker.get_whale_balances()
        
        return {
            "asset": "ETH",
            "supply": supply,
            "gas_prices": gas,
            "large_transactions": large_txs,
            "whale_balances": whale_balances,
            "known_whales": list(KNOWN_ETH_WHALES.values())
        }
    
    else:
        return {"error": f"不支持的资产: {asset}"}


# ============================================================================
# 主程序
# ============================================================================

if __name__ == "__main__":
    import sys
    
    asset = sys.argv[1].upper() if len(sys.argv) > 1 else "ETH"
    
    print("\n" + "="*60)
    print(f"🔍 Native Asset Tracker - {asset} 原生资产追踪")
    print("="*60)
    
    result = track_native_asset(asset)
    
    if "error" in result:
        print(f"\n❌ {result['error']}")
    else:
        print(f"\n📊 {asset} 数据:")
        
        if asset == "BTC":
            stats = result.get("stats", {})
            print(f"  价格: ${stats.get('market_price_usd', 0):,.2f}")
            print(f"  总供应: {stats.get('total_btc', 0):,.2f} BTC")
            print(f"  24H 交易数: {stats.get('n_tx_24h', 0):,}")
        
        elif asset == "ETH":
            supply = result.get("supply", {})
            gas = result.get("gas_prices", {})
            print(f"  总供应: {supply.get('total_supply', 0):,.2f} ETH")
            print(f"  质押量: {supply.get('staked_supply', 0):,.2f} ETH")
            print(f"  Gas: {gas.get('safe', 0):.1f} / {gas.get('propose', 0):.1f} / {gas.get('fast', 0):.1f} Gwei")
            
            print(f"  Gas: {gas.get('safe', 0):.1f} / {gas.get('propose', 0):.1f} / {gas.get('fast', 0):.1f} Gwei")
            
        # 鲸鱼余额 (通用)
        whales = result.get("whale_balances", [])
        if whales:
            print(f"\n🐋 Top 鲸鱼余额:")
            for w in whales[:5]:
                unit = "BTC" if asset == "BTC" else "ETH"
                balance_key = "balance_btc" if asset == "BTC" else "balance_eth"
                print(f"  {w['label']}: {w[balance_key]:,.2f} {unit}")
        
        # 大额交易
        txs = result.get("large_transactions", [])
        if txs:
            print(f"\n💰 最近大额交易 ({len(txs)} 笔):")
            for tx in txs[:5]:
                if asset == "BTC":
                    print(f"  {tx['btc']:,.2f} BTC - {tx['time']}")
                else:
                    label = f" ({tx['from_label']}→{tx['to_label']})" if tx.get('from_label') or tx.get('to_label') else ""
                    print(f"  {tx['eth']:,.2f} ETH{label}")
    
    print("\n" + "="*60)
