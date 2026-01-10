"""
Ethereum Chain Monitor - 链上风险监控模块
============================================
监控内容:
1. 网络拥堵与 Gas 监控
2. MEV 活动异常检测
3. 链上异常活动分析
4. 验证者状态监控
"""

import time
import requests
import numpy as np
from web3 import Web3
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from termcolor import cprint

# ============================================================================
# 配置
# ============================================================================

# 公共 RPC (生产环境建议使用 Alchemy/Infura 私有节点)
RPC_URL = "https://eth.llamarpc.com"

# API 端点
FLASHBOTS_API = "https://blocks.flashbots.net/v1/blocks"
BEACON_API = "https://beaconcha.in/api/v1"
ETHERSCAN_API = "https://api.etherscan.io/api"

# Etherscan API Key (可选，用于更丰富的数据)
ETHERSCAN_API_KEY = "QG8HRJJNIE7GZ72Y7PK8KK2695KQVWFS5T"

# ============================================================================
# 阈值配置 (可根据实际情况调整)
# ============================================================================

# Gas 相关
GAS_SPIKE_THRESHOLD = 2.0      # Gas 价格是过去 10 个区块均值的 2 倍即报警
GAS_EXTREME_THRESHOLD = 100    # Gas > 100 Gwei 直接报警
GAS_LOW_THRESHOLD = 10         # Gas < 10 Gwei 为低位

# 区块利用率
HIGH_UTILIZATION = 95          # 区块利用率 > 95% 为高拥堵

# MEV 相关
MEV_BUNDLE_THRESHOLD = 10      # 单个区块包含超过 10 个 MEV bundles

# 异常检测
HIGH_FAIL_RATE = 0.3           # 区块内交易失败率超过 30%
SUSPICIOUS_GAS_THRESHOLD = 25000000  # 可疑高 Gas 消耗阈值
MIN_TX_FOR_SUSPICION = 50      # 低交易数阈值

# ============================================================================
# 数据类
# ============================================================================

@dataclass
class BlockMetrics:
    """区块指标"""
    block_number: int
    timestamp: datetime
    base_fee_gwei: float
    gas_used: int
    gas_limit: int
    utilization_pct: float
    tx_count: int
    mev_bundles: int = 0
    alerts: List[str] = None
    
    def __post_init__(self):
        if self.alerts is None:
            self.alerts = []


@dataclass
class NetworkStatus:
    """网络状态"""
    is_congested: bool
    gas_level: str  # "low", "normal", "high", "extreme"
    current_gas_gwei: float
    avg_gas_gwei: float
    utilization_pct: float
    mev_activity: str  # "normal", "elevated", "high"
    alerts: List[str]


# ============================================================================
# 链上监控器
# ============================================================================

class ChainMonitor:
    """以太坊链上风险监控器"""
    
    def __init__(self, rpc_url: str = RPC_URL):
        self.rpc_url = rpc_url
        self.w3 = None
        self.gas_history: List[float] = []
        self.block_history: List[BlockMetrics] = []
        self.connected = False
        
    def connect(self) -> bool:
        """连接到 RPC 节点"""
        try:
            self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
            self.connected = self.w3.is_connected()
            if self.connected:
                cprint(f"[{datetime.now()}] ✓ 已连接到 Ethereum Mainnet", "green")
            return self.connected
        except Exception as e:
            cprint(f"[ERROR] 连接失败: {e}", "red")
            return False
    
    def get_current_gas_price(self) -> Optional[float]:
        """获取当前 Gas 价格 (Gwei)"""
        if not self.connected:
            return None
        try:
            gas_price = self.w3.eth.gas_price
            return gas_price / 10**9  # Wei to Gwei
        except Exception:
            return None
    
    def check_network_congestion(self, block: Dict) -> tuple:
        """
        监控 Gas 突增 (Gas Spike) 和 区块拥堵 (Congestion)
        返回: (base_fee_gwei, utilization_pct, alerts)
        """
        alerts = []
        
        base_fee = block.get('baseFeePerGas', 0) / 10**9  # Gwei
        gas_used = block['gasUsed']
        gas_limit = block['gasLimit']
        utilization = (gas_used / gas_limit) * 100 if gas_limit > 0 else 0
        
        # 更新 Gas 历史
        self.gas_history.append(base_fee)
        if len(self.gas_history) > 10:
            self.gas_history.pop(0)
        
        # 检测 Gas 突增
        if len(self.gas_history) >= 5:
            avg_gas = np.mean(self.gas_history[:-1])  # 不包含当前值
            if base_fee > avg_gas * GAS_SPIKE_THRESHOLD and avg_gas > 5:
                alerts.append(f"⚠️ Gas 突增: {base_fee:.1f} Gwei (均值: {avg_gas:.1f})")
        
        # 检测极端 Gas
        if base_fee > GAS_EXTREME_THRESHOLD:
            alerts.append(f"🔴 Gas 极高: {base_fee:.1f} Gwei")
        
        # 检测高拥堵
        if utilization > HIGH_UTILIZATION:
            alerts.append(f"🔥 网络拥堵: 区块利用率 {utilization:.1f}%")
        
        return base_fee, utilization, alerts
    
    def check_mev_activity(self, block_number: int) -> tuple:
        """
        通过 Flashbots 公共 API 检测 MEV 异常
        返回: (bundle_count, alerts)
        """
        alerts = []
        bundle_count = 0
        
        try:
            params = {'block_number': block_number}
            resp = requests.get(FLASHBOTS_API, params=params, timeout=3)
            
            if resp.status_code == 200:
                data = resp.json()
                if data.get('blocks'):
                    block_data = data['blocks'][0]
                    bundle_count = int(block_data.get('transactions_count', 0))
                    
                    if bundle_count > MEV_BUNDLE_THRESHOLD:
                        alerts.append(f"⚠️ MEV 活动激增: 区块 {block_number} 包含 {bundle_count} 个 bundles")
        except requests.exceptions.Timeout:
            pass  # 忽略超时
        except Exception:
            pass  # 忽略其他错误
        
        return bundle_count, alerts
    
    def check_block_anomalies(self, block: Dict) -> List[str]:
        """
        检测区块级别的潜在攻击指征
        (高失败率通常意味着被攻击或大规模抢跑失败)
        """
        alerts = []
        
        txs = block.get('transactions', [])
        tx_count = len(txs)
        gas_used = block['gasUsed']
        
        # 启发式检测：高 Gas 消耗但交易数极少（可能的大型合约调用/攻击）
        if gas_used > SUSPICIOUS_GAS_THRESHOLD and tx_count < MIN_TX_FOR_SUSPICION:
            alerts.append(
                f"🚨 可疑区块结构: 高 Gas ({gas_used:,}) 但交易数少 ({tx_count})，可能存在复杂操作或攻击"
            )
        
        return alerts
    
    def get_validator_status(self) -> Optional[Dict]:
        """
        获取验证者状态 (使用 Beaconcha.in API)
        """
        try:
            resp = requests.get(f"{BEACON_API}/epoch/latest", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('status') == 'OK':
                    epoch_data = data.get('data', {})
                    return {
                        'epoch': epoch_data.get('epoch'),
                        'validators_count': epoch_data.get('validatorscount'),
                        'participation_rate': epoch_data.get('globalparticipationrate'),
                        'finalized': epoch_data.get('finalized', False)
                    }
        except Exception:
            pass
        return None
    
    def get_etherscan_gas_oracle(self) -> Optional[Dict]:
        """
        从 Etherscan 获取 Gas 预言机数据
        """
        try:
            params = {
                'module': 'gastracker',
                'action': 'gasoracle',
                'apikey': ETHERSCAN_API_KEY
            }
            resp = requests.get(ETHERSCAN_API, params=params, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('status') == '1':
                    result = data.get('result', {})
                    return {
                        'safe_gas': float(result.get('SafeGasPrice', 0)),
                        'propose_gas': float(result.get('ProposeGasPrice', 0)),
                        'fast_gas': float(result.get('FastGasPrice', 0)),
                        'base_fee': float(result.get('suggestBaseFee', 0))
                    }
        except Exception:
            pass
        return None
    
    def analyze_block(self, block_number: Optional[int] = None) -> Optional[BlockMetrics]:
        """
        分析指定区块（默认为最新区块）
        """
        if not self.connected:
            if not self.connect():
                return None
        
        try:
            if block_number is None:
                block_number = self.w3.eth.block_number
            
            block = self.w3.eth.get_block(block_number, full_transactions=False)
            
            # 检查网络拥堵
            base_fee, utilization, congestion_alerts = self.check_network_congestion(block)
            
            # 检查 MEV 活动 (检查前 2 个区块以应对延迟)
            mev_bundles, mev_alerts = self.check_mev_activity(block_number - 2)
            
            # 检查区块异常
            anomaly_alerts = self.check_block_anomalies(block)
            
            # 合并所有告警
            all_alerts = congestion_alerts + mev_alerts + anomaly_alerts
            
            # 创建指标对象
            metrics = BlockMetrics(
                block_number=block_number,
                timestamp=datetime.fromtimestamp(block['timestamp']),
                base_fee_gwei=base_fee,
                gas_used=block['gasUsed'],
                gas_limit=block['gasLimit'],
                utilization_pct=utilization,
                tx_count=len(block.get('transactions', [])),
                mev_bundles=mev_bundles,
                alerts=all_alerts
            )
            
            # 保存到历史
            self.block_history.append(metrics)
            if len(self.block_history) > 100:
                self.block_history.pop(0)
            
            return metrics
            
        except Exception as e:
            cprint(f"[ERROR] 分析区块失败: {e}", "red")
            return None
    
    def get_network_status(self) -> NetworkStatus:
        """
        获取当前网络状态摘要
        """
        alerts = []
        
        # 分析最新区块
        metrics = self.analyze_block()
        
        if metrics is None:
            return NetworkStatus(
                is_congested=False,
                gas_level="unknown",
                current_gas_gwei=0,
                avg_gas_gwei=0,
                utilization_pct=0,
                mev_activity="unknown",
                alerts=["⚠️ 无法获取网络状态"]
            )
        
        # 计算平均 Gas
        avg_gas = np.mean(self.gas_history) if self.gas_history else metrics.base_fee_gwei
        
        # 判断 Gas 水平
        current_gas = metrics.base_fee_gwei
        if current_gas < GAS_LOW_THRESHOLD:
            gas_level = "low"
        elif current_gas < 30:
            gas_level = "normal"
        elif current_gas < GAS_EXTREME_THRESHOLD:
            gas_level = "high"
        else:
            gas_level = "extreme"
        
        # 判断 MEV 活动水平
        if metrics.mev_bundles < 5:
            mev_activity = "normal"
        elif metrics.mev_bundles < MEV_BUNDLE_THRESHOLD:
            mev_activity = "elevated"
        else:
            mev_activity = "high"
        
        # 判断是否拥堵
        is_congested = metrics.utilization_pct > HIGH_UTILIZATION or gas_level in ["high", "extreme"]
        
        # 收集告警
        alerts = metrics.alerts.copy()
        
        return NetworkStatus(
            is_congested=is_congested,
            gas_level=gas_level,
            current_gas_gwei=current_gas,
            avg_gas_gwei=avg_gas,
            utilization_pct=metrics.utilization_pct,
            mev_activity=mev_activity,
            alerts=alerts
        )
    
    def run_continuous(self, interval: int = 12):
        """
        持续监控模式（每个区块约 12 秒）
        """
        if not self.connect():
            return
        
        last_block = 0
        cprint(f"\n🔍 开始持续监控 (间隔: {interval}秒)...\n", "cyan")
        
        while True:
            try:
                current_block = self.w3.eth.block_number
                
                if current_block > last_block:
                    metrics = self.analyze_block(current_block)
                    
                    if metrics:
                        # 打印状态
                        status_line = (
                            f"Block {metrics.block_number} | "
                            f"Gas: {metrics.base_fee_gwei:.1f} Gwei | "
                            f"Util: {metrics.utilization_pct:.1f}% | "
                            f"Txs: {metrics.tx_count}"
                        )
                        
                        if metrics.mev_bundles > 0:
                            status_line += f" | MEV: {metrics.mev_bundles}"
                        
                        cprint(status_line, "white")
                        
                        # 打印告警
                        for alert in metrics.alerts:
                            cprint(f"  {alert}", "yellow")
                    
                    last_block = current_block
                
                time.sleep(interval)
                
            except KeyboardInterrupt:
                cprint("\n⏹️ 监控已停止", "cyan")
                break
            except Exception as e:
                cprint(f"[ERROR] {e}", "red")
                time.sleep(5)


# ============================================================================
# 单次检查函数（供外部调用）
# ============================================================================

def check_chain_health() -> Dict[str, Any]:
    """
    快速检查链上健康状态（供其他模块调用）
    """
    monitor = ChainMonitor()
    if not monitor.connect():
        return {
            "success": False,
            "error": "无法连接到 RPC"
        }
    
    status = monitor.get_network_status()
    gas_oracle = monitor.get_etherscan_gas_oracle()
    
    return {
        "success": True,
        "timestamp": datetime.now().isoformat(),
        "network_status": {
            "is_congested": status.is_congested,
            "gas_level": status.gas_level,
            "current_gas_gwei": status.current_gas_gwei,
            "avg_gas_gwei": status.avg_gas_gwei,
            "utilization_pct": status.utilization_pct,
            "mev_activity": status.mev_activity
        },
        "gas_oracle": gas_oracle,
        "alerts": status.alerts,
        "recent_blocks": [
            {
                "block": m.block_number,
                "gas": m.base_fee_gwei,
                "util": m.utilization_pct,
                "txs": m.tx_count
            }
            for m in monitor.block_history[-5:]
        ]
    }


# ============================================================================
# 主程序入口
# ============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Ethereum Chain Monitor")
    parser.add_argument("--continuous", "-c", action="store_true", help="持续监控模式")
    parser.add_argument("--interval", "-i", type=int, default=12, help="监控间隔(秒)")
    args = parser.parse_args()
    
    monitor = ChainMonitor()
    
    if args.continuous:
        monitor.run_continuous(interval=args.interval)
    else:
        # 单次检查
        result = check_chain_health()
        
        print("\n" + "="*60)
        print("📊 Ethereum 链上健康检查")
        print("="*60)
        
        if result["success"]:
            ns = result["network_status"]
            print(f"\n🔹 网络状态: {'⚠️ 拥堵' if ns['is_congested'] else '✅ 正常'}")
            print(f"🔹 Gas 水平: {ns['gas_level'].upper()} ({ns['current_gas_gwei']:.1f} Gwei)")
            print(f"🔹 区块利用率: {ns['utilization_pct']:.1f}%")
            print(f"🔹 MEV 活动: {ns['mev_activity'].upper()}")
            
            if result["gas_oracle"]:
                go = result["gas_oracle"]
                print(f"\n💰 Gas 预言机 (Etherscan):")
                print(f"   Safe: {go['safe_gas']:.1f} | Standard: {go['propose_gas']:.1f} | Fast: {go['fast_gas']:.1f}")
            
            if result["alerts"]:
                print(f"\n⚠️ 告警:")
                for alert in result["alerts"]:
                    print(f"   {alert}")
            else:
                print(f"\n✅ 无告警")
        else:
            print(f"\n❌ 检查失败: {result.get('error')}")
        
        print("\n" + "="*60)
