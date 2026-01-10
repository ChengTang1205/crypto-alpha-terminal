"""
Token Risk Agent - 代币风险分析模块
=====================================
功能:
1. 鲸鱼/HHI 持仓集中度分析 (Ethplorer API)
2. 活动集中性分析 (Etherscan API)
3. OFAC 黑名单检查
"""

import requests
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Set
from termcolor import cprint

# ============================================================================
# 配置
# ============================================================================

# Etherscan API Key
ETHERSCAN_API_KEY = "QG8HRJJNIE7GZ72Y7PK8KK2695KQVWFS5T"

# API 端点
ETHPLORER_API = "https://api.ethplorer.io"
ETHERSCAN_API = "https://api.etherscan.io/api"

# 常用代币地址
KNOWN_TOKENS = {
    "USDT": "0xdac17f958d2ee523a2206206994597c13d831ec7",
    "USDC": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
    "WETH": "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
    "UNI": "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984",
    "LINK": "0x514910771af9ca656af840dff83e8264ecf986ca",
    "AAVE": "0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9",
    "MKR": "0x9f8f72aa9304c8b593d555f12ef6589cc3a579a2",
    "CRV": "0xd533a949740bb3306d119cc777fa900ba034cd52",
    "LDO": "0x5a98fcbea516cf06857215779fd812ca3bef1b32",
    "SHIB": "0x95ad61b0a150d79219dcf64e1e6cc01f0b64c4ce",
    "PEPE": "0x6982508145454ce325ddbe47a25d4ec3d2311933",
}

# 代币精度 (decimals)
TOKEN_DECIMALS = {
    "0xdac17f958d2ee523a2206206994597c13d831ec7": 6,   # USDT
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": 6,   # USDC
    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": 18,  # WETH
    "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984": 18,  # UNI
    "0x514910771af9ca656af840dff83e8264ecf986ca": 18,  # LINK
}

# OFAC 制裁黑名单 (示例，实际生产需定期更新)
OFAC_BLACKLIST: Set[str] = {
    # Tornado Cash 相关
    "0x8589427373d6d84e98730d7795d8f6f8731fda16",
    "0x722122df12d4e14e13ac3b6895a86e84145b6967",
    "0xdd4c48c0b24039969fc16d1cdf626eab821d3384",
    "0xd90e2f925da726b50c4ed8d0fb90ad053324f31b",
    "0xd96f2b1c14db8458374d9aca76e26c3d18364307",
    # Ronin Bridge Hacker
    "0x098b716b8aaf21512996dc57eb0615e2383e2f96",
    # 其他已知制裁地址
    "0x7f367cc41522ce07553e823bf3be79a889debe1b",
    "0x1da5821544e25c636c1417ba96ade4cf6d2f9b5a",
    "0x7db418b5d567a4e0e8c59ad71be1fce48f3e6107",
    "0x72a5843cc08275c8171e582972aa4fda8c397b2a",
    "0x7f19720a857f834887fc9a7bc0a0fbe7fc7f8102",
    "0xa7e5d5a720f06526557c513402f2e6b5fa20b008",
}

# ============================================================================
# 数据类
# ============================================================================

@dataclass
class HHIResult:
    """HHI 分析结果"""
    hhi_score: float
    top_10_concentration: float
    top_holder_share: float
    total_holders_analyzed: int
    risk_level: str  # LOW, MEDIUM, HIGH


@dataclass
class ActivityResult:
    """活动分析结果"""
    volume_24h: float
    whale_activity_ratio: float
    activity_change_rate: float
    total_transactions: int
    whale_transactions: int


@dataclass
class TokenRiskReport:
    """完整风险报告"""
    token_address: str
    token_symbol: str
    hhi_analysis: Optional[HHIResult]
    activity_analysis: Optional[ActivityResult]
    blacklist_hits: List[str]
    overall_risk: str  # LOW, MEDIUM, HIGH, CRITICAL
    risk_factors: List[str]
    timestamp: datetime


# ============================================================================
# Token Risk Agent
# ============================================================================

class TokenRiskAgent:
    """代币风险分析代理"""
    
    def __init__(self, etherscan_api_key: str = ETHERSCAN_API_KEY):
        self.etherscan_key = etherscan_api_key
        self.blacklist = OFAC_BLACKLIST
        
    def get_token_decimals(self, token_address: str) -> int:
        """获取代币精度"""
        token_lower = token_address.lower()
        
        # 先查本地缓存
        if token_lower in TOKEN_DECIMALS:
            return TOKEN_DECIMALS[token_lower]
        
        # 调用 Etherscan 获取
        try:
            params = {
                'module': 'token',
                'action': 'tokeninfo',
                'contractaddress': token_address,
                'apikey': self.etherscan_key
            }
            resp = requests.get(ETHERSCAN_API, params=params, timeout=10)
            data = resp.json()
            if data.get('status') == '1' and data.get('result'):
                decimals = int(data['result'][0].get('divisor', '18'))
                return len(str(decimals)) - 1 if decimals > 1 else 18
        except Exception:
            pass
        
        return 18  # 默认 18
    
    def fetch_top_holders(self, token_address: str, limit: int = 100) -> List[Dict]:
        """
        使用 Ethplorer 获取 Top Holders
        """
        url = f"{ETHPLORER_API}/getTopTokenHolders/{token_address}"
        params = {'apiKey': 'freekey', 'limit': min(limit, 100)}
        
        try:
            resp = requests.get(url, params=params, timeout=15)
            data = resp.json()
            
            if 'holders' in data:
                return data['holders']
            else:
                cprint(f"[Warning] Ethplorer response: {data.get('error', 'No holders')}", "yellow")
                return []
        except Exception as e:
            cprint(f"[Error] Fetching holders: {e}", "red")
            return []
    
    def calculate_hhi(self, holders_data: List[Dict]) -> Optional[HHIResult]:
        """
        计算 HHI 指数 (赫芬达尔—赫希曼指数)
        范围: 0 (完全分散) - 10000 (完全垄断)
        
        风险等级:
        - < 1500: LOW (竞争性市场)
        - 1500-2500: MEDIUM (中等集中)
        - > 2500: HIGH (高度集中)
        """
        if not holders_data:
            return None
        
        df = pd.DataFrame(holders_data)
        df['share'] = pd.to_numeric(df['share'], errors='coerce')
        df = df.dropna(subset=['share'])
        
        if df.empty:
            return None
        
        # HHI = sum(share^2)
        hhi = (df['share'] ** 2).sum()
        top_10_share = df.head(10)['share'].sum()
        top_holder_share = df.iloc[0]['share'] if len(df) > 0 else 0
        
        # 判断风险等级
        if hhi < 1500:
            risk_level = "LOW"
        elif hhi < 2500:
            risk_level = "MEDIUM"
        else:
            risk_level = "HIGH"
        
        return HHIResult(
            hhi_score=round(hhi, 2),
            top_10_concentration=round(top_10_share, 2),
            top_holder_share=round(top_holder_share, 2),
            total_holders_analyzed=len(df),
            risk_level=risk_level
        )
    
    def check_blacklist(self, addresses: List[str]) -> List[str]:
        """检查地址是否在 OFAC 黑名单中"""
        hits = []
        for addr in addresses:
            if addr.lower() in self.blacklist:
                hits.append(addr)
        return hits
    
    def fetch_token_transactions(self, token_address: str, limit: int = 1000) -> List[Dict]:
        """获取代币最近交易记录"""
        params = {
            'module': 'account',
            'action': 'tokentx',
            'contractaddress': token_address,
            'page': 1,
            'offset': min(limit, 10000),
            'sort': 'desc',
            'apikey': self.etherscan_key
        }
        
        try:
            resp = requests.get(ETHERSCAN_API, params=params, timeout=15)
            data = resp.json()
            
            if data.get('status') == '1':
                return data.get('result', [])
            return []
        except Exception as e:
            cprint(f"[Error] Fetching transactions: {e}", "red")
            return []
    
    def analyze_activity(self, txs: List[Dict], decimals: int = 18) -> Optional[ActivityResult]:
        """
        分析近 24 小时活动集中性
        鲸鱼定义: 交易额超过平均值的 3 倍
        """
        if not txs:
            return None
        
        df = pd.DataFrame(txs)
        df['timeStamp'] = pd.to_numeric(df['timeStamp'], errors='coerce')
        df['value'] = pd.to_numeric(df['value'], errors='coerce') / (10 ** decimals)
        df = df.dropna(subset=['timeStamp', 'value'])
        
        if df.empty:
            return None
        
        now = time.time()
        curr_24h_start = now - 86400
        prev_24h_start = now - 172800
        
        # 切片
        df_curr = df[df['timeStamp'] >= curr_24h_start]
        df_prev = df[(df['timeStamp'] >= prev_24h_start) & (df['timeStamp'] < curr_24h_start)]
        
        if df_curr.empty:
            return ActivityResult(
                volume_24h=0,
                whale_activity_ratio=0,
                activity_change_rate=0,
                total_transactions=0,
                whale_transactions=0
            )
        
        # 鲸鱼阈值 (基于整体样本)
        mean_vol = df['value'].mean()
        whale_threshold = mean_vol * 3
        
        def calc_metrics(subset):
            if subset.empty:
                return 0, 0, 0, 0
            whale_txs = subset[subset['value'] > whale_threshold]
            total_vol = subset['value'].sum()
            whale_vol = whale_txs['value'].sum()
            ratio = (whale_vol / total_vol) if total_vol > 0 else 0
            return total_vol, ratio, len(subset), len(whale_txs)
        
        curr_vol, curr_ratio, curr_count, curr_whale_count = calc_metrics(df_curr)
        prev_vol, prev_ratio, _, _ = calc_metrics(df_prev)
        
        ratio_change = curr_ratio - prev_ratio
        
        return ActivityResult(
            volume_24h=round(curr_vol, 2),
            whale_activity_ratio=round(curr_ratio, 4),
            activity_change_rate=round(ratio_change, 4),
            total_transactions=curr_count,
            whale_transactions=curr_whale_count
        )
    
    def analyze_token(self, token_address: str, token_symbol: str = "") -> TokenRiskReport:
        """
        执行完整的代币风险分析
        """
        token_address = token_address.lower()
        risk_factors = []
        overall_risk = "LOW"
        
        cprint(f"\n--- 分析代币: {token_symbol or token_address[:10]}... ---", "cyan")
        
        # 1. 获取代币精度
        decimals = self.get_token_decimals(token_address)
        cprint(f"  📊 代币精度: {decimals}", "white")
        
        # 2. HHI 分析
        cprint("  🔍 获取持仓分布...", "white")
        holders = self.fetch_top_holders(token_address)
        hhi_result = self.calculate_hhi(holders)
        
        if hhi_result:
            cprint(f"  📈 HHI: {hhi_result.hhi_score} | Top10: {hhi_result.top_10_concentration}%", "white")
            
            if hhi_result.risk_level == "HIGH":
                risk_factors.append(f"高度集中: HHI={hhi_result.hhi_score}")
                overall_risk = "HIGH"
            elif hhi_result.risk_level == "MEDIUM":
                risk_factors.append(f"中度集中: HHI={hhi_result.hhi_score}")
                if overall_risk == "LOW":
                    overall_risk = "MEDIUM"
            
            if hhi_result.top_holder_share > 50:
                risk_factors.append(f"最大持仓者占 {hhi_result.top_holder_share}%")
                overall_risk = "HIGH"
        
        # 3. 黑名单检查 (检查 Top Holders)
        holder_addresses = [h.get('address', '') for h in holders]
        blacklist_hits = self.check_blacklist(holder_addresses)
        
        if blacklist_hits:
            risk_factors.append(f"发现 {len(blacklist_hits)} 个制裁地址持仓")
            overall_risk = "CRITICAL"
            cprint(f"  ⚠️ 黑名单命中: {len(blacklist_hits)} 个地址", "red")
        else:
            cprint("  ✅ 黑名单检查: 无命中", "green")
        
        # 4. 活动分析
        cprint("  🔍 分析交易活动...", "white")
        txs = self.fetch_token_transactions(token_address)
        activity_result = self.analyze_activity(txs, decimals)
        
        if activity_result:
            cprint(f"  📊 24H交易: {activity_result.total_transactions} 笔 | 鲸鱼占比: {activity_result.whale_activity_ratio:.2%}", "white")
            
            if activity_result.whale_activity_ratio > 0.5:
                risk_factors.append(f"鲸鱼活动占比 {activity_result.whale_activity_ratio:.1%}")
                if overall_risk in ["LOW", "MEDIUM"]:
                    overall_risk = "MEDIUM"
            
            if activity_result.activity_change_rate > 0.2:
                risk_factors.append(f"鲸鱼活动激增 {activity_result.activity_change_rate:+.1%}")
        
        # 5. 生成报告
        report = TokenRiskReport(
            token_address=token_address,
            token_symbol=token_symbol,
            hhi_analysis=hhi_result,
            activity_analysis=activity_result,
            blacklist_hits=blacklist_hits,
            overall_risk=overall_risk,
            risk_factors=risk_factors,
            timestamp=datetime.now()
        )
        
        # 打印结果
        risk_color = {"LOW": "green", "MEDIUM": "yellow", "HIGH": "red", "CRITICAL": "red"}
        cprint(f"\n  📋 风险评级: {overall_risk}", risk_color.get(overall_risk, "white"))
        if risk_factors:
            for factor in risk_factors:
                cprint(f"     - {factor}", "yellow")
        
        return report


# ============================================================================
# 快速检查函数
# ============================================================================

def analyze_token_risk(token_address: str, token_symbol: str = "") -> Dict[str, Any]:
    """
    快速分析代币风险 (供外部调用)
    """
    agent = TokenRiskAgent()
    report = agent.analyze_token(token_address, token_symbol)
    
    return {
        "success": True,
        "token": {
            "address": report.token_address,
            "symbol": report.token_symbol
        },
        "hhi": {
            "score": report.hhi_analysis.hhi_score if report.hhi_analysis else None,
            "top_10_pct": report.hhi_analysis.top_10_concentration if report.hhi_analysis else None,
            "top_holder_pct": report.hhi_analysis.top_holder_share if report.hhi_analysis else None,
            "risk_level": report.hhi_analysis.risk_level if report.hhi_analysis else "UNKNOWN"
        },
        "activity": {
            "volume_24h": report.activity_analysis.volume_24h if report.activity_analysis else None,
            "whale_ratio": report.activity_analysis.whale_activity_ratio if report.activity_analysis else None,
            "whale_change": report.activity_analysis.activity_change_rate if report.activity_analysis else None,
            "tx_count": report.activity_analysis.total_transactions if report.activity_analysis else 0
        },
        "blacklist_hits": len(report.blacklist_hits),
        "overall_risk": report.overall_risk,
        "risk_factors": report.risk_factors,
        "timestamp": report.timestamp.isoformat()
    }


def check_wallet_blacklist(wallet_address: str) -> Dict[str, Any]:
    """
    检查钱包是否在 OFAC 黑名单
    """
    is_blacklisted = wallet_address.lower() in OFAC_BLACKLIST
    
    return {
        "address": wallet_address,
        "is_sanctioned": is_blacklisted,
        "status": "🔴 SANCTIONED" if is_blacklisted else "🟢 CLEAN",
        "source": "OFAC SDN List"
    }


# ============================================================================
# 主程序入口
# ============================================================================

if __name__ == "__main__":
    import sys
    
    # 默认分析 USDT
    token = KNOWN_TOKENS.get("USDT")
    symbol = "USDT"
    
    if len(sys.argv) > 1:
        arg = sys.argv[1].upper()
        if arg in KNOWN_TOKENS:
            token = KNOWN_TOKENS[arg]
            symbol = arg
        else:
            token = sys.argv[1]
            symbol = ""
    
    print("\n" + "="*60)
    print("🔍 Token Risk Agent - 代币风险分析")
    print("="*60)
    
    result = analyze_token_risk(token, symbol)
    
    print("\n" + "-"*60)
    print("📊 分析结果摘要")
    print("-"*60)
    print(f"代币: {result['token']['symbol'] or result['token']['address'][:20]}")
    print(f"HHI 指数: {result['hhi']['score']} ({result['hhi']['risk_level']})")
    print(f"Top 10 持仓: {result['hhi']['top_10_pct']}%")
    print(f"24H 交易量: {result['activity']['volume_24h']}")
    print(f"鲸鱼占比: {result['activity']['whale_ratio']:.2%}" if result['activity']['whale_ratio'] else "N/A")
    print(f"黑名单命中: {result['blacklist_hits']}")
    print(f"\n🎯 综合风险: {result['overall_risk']}")
    
    if result['risk_factors']:
        print("\n⚠️ 风险因素:")
        for f in result['risk_factors']:
            print(f"   - {f}")
    
    print("\n" + "="*60)
