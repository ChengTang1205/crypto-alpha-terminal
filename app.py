import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go # [新增] 用于画双轴图
from plotly.subplots import make_subplots # [新增]
import yfinance as yf # [新增]
import time
import os  # [NEW] For file path operations
from datetime import datetime, timedelta
from streamlit_echarts import st_echarts


# --- 导入模块 ---
try:
    from stablecoin_monitor import StablecoinSupplyMonitor
    from bridge_monitor import BridgeFlowMonitor
    from exchange_monitor import CEXReserveMonitor
    from depeg_monitor import DepegMonitor
    from market_sentiment import MarketSentimentMonitor # <--- 新增这行
    from quant_agent import CryptoQuantAgent # <--- 新增这行
    from agents.launcher import run_multi_agent_analysis # [NEW] Multi-Agent Launcher
    from sentiment.reddit_sentiment import RedditSentimentAnalyzer # [NEW] Reddit Sentiment
except ImportError as e:
    st.error(f"❌ 导入脚本失败: {e}")
    st.stop()

# --- 页面配置 ---
st.set_page_config(page_title="Crypto Alpha Terminal", page_icon="⚡️", layout="wide", initial_sidebar_state="expanded")

# --- 侧边栏 ---
st.sidebar.title("🚀 控制台")
if st.sidebar.button("🔄 刷新数据"):
    st.cache_data.clear()
    st.rerun()

st.title("Crypto Alpha Terminal ⚡️")

# --- 数据加载函数 ---

@st.cache_data(ttl=3600)
def load_stablecoin_summary():
    # 获取汇总表格
    monitor = StablecoinSupplyMonitor()
    df = monitor.analyze_shifts()
    if not df.empty:
        total_cap = df['Total Supply'].sum()
        df['Share'] = (df['Total Supply'] / total_cap) * 100 
        df['Total Supply (B)'] = df['Total Supply'] / 1e9
        df['Flow 24h (M)'] = df['Net Flow (24h)'] / 1e6
        df['Flow 7d (M)'] = df['Net Flow (7d)'] / 1e6
        def get_trend(val):
            if val > 5_000_000: return "🟢 Mint"
            if val < -5_000_000: return "🔴 Burn"
            return "⚪ Flat"
        df['Trend (7d)'] = df['Net Flow (7d)'].apply(get_trend)
    return df

@st.cache_data(ttl=3600)
def load_usdt_btc_chart_data():
    # [新增] 专门用于画 USDT vs BTC 对比图的数据
    
    # 1. 获取 USDT 历史市值
    monitor = StablecoinSupplyMonitor()
    df_usdt = monitor.get_asset_history('USDT') 
    
    # 2. 获取 BTC 历史价格 (使用 yfinance)
    btc = yf.Ticker("BTC-USD")
    
    # 🔥 核心修改点：将 period 改为 "6mo" (6个月)，确保和 USDT 长度一致
    df_btc = btc.history(period="6mo").reset_index()
    
    # 统一时区问题 (去除时区信息以便合并)
    if not df_btc.empty and 'Date' in df_btc.columns:
        df_btc['Date'] = df_btc['Date'].dt.tz_localize(None)
    
    return df_usdt, df_btc

@st.cache_data(ttl=3600)
def load_bridge_data():
    monitor = BridgeFlowMonitor()
    return monitor.analyze_bridges()

@st.cache_data(ttl=3600)
def load_exchange_data():
    monitor = CEXReserveMonitor()
    return monitor.run_monitor()

@st.cache_data(ttl=300)
def load_depeg_data():
    monitor = DepegMonitor()
    return monitor.analyze_pegs()


@st.cache_data(ttl=600)
def load_sentiment_data():
    """Tab 5: 市场情绪数据"""
    monitor = MarketSentimentMonitor()
    fng = monitor.get_fear_and_greed()
    df_deriv, is_fallback = monitor.get_all_data() # 接收两个返回值
    return fng, df_deriv, is_fallback


# --- Tabs ---
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10, tab11 = st.tabs([
    "💵 宏观资金", 
    "🌉 跨链热点", 
    "🏦 CEX 储备", 
    "🚨 风险监控", 
    "🎭 情绪与合约", 
    "🧠 多智能体实验室",
    "📱 Reddit 舆情",
    "🛠️ Backtest",
    "🐦 Twitter 舆情",
    "🛡️ 合规风险",
    "🧠 AI Alpha Lab"
])


# ==============================================================================
# Tab 1: 宏观资金 (重构版 - 含 BTC 对比)
# ==============================================================================
with tab1:
    st.subheader("全球稳定币流动性 vs BTC 价格")
    
    col_chart, col_pie = st.columns([2.5, 1.5])
    
    with col_chart:
        with st.spinner('正在加载 BTC 与 USDT 历史数据...'):
            try:
                # 1. 这里定义的是 df_usdt
                df_usdt, df_btc = load_usdt_btc_chart_data()
                
                if not df_usdt.empty and not df_btc.empty:
                    # 创建双轴图
                    fig = make_subplots(specs=[[{"secondary_y": True}]])

                    # 左轴: USDT 市值 (区域图)
                    fig.add_trace(
                        go.Scatter(
                            x=df_usdt['Date'], y=df_usdt['Supply'], 
                            name="USDT 市值",
                            fill='tozeroy', 
                            line=dict(color='rgba(0, 128, 0, 0.5)', width=1),
                            fillcolor='rgba(0, 128, 0, 0.1)'
                        ),
                        secondary_y=False,
                    )

                    # 右轴: BTC 价格 (线图)
                    fig.add_trace(
                        go.Scatter(
                            x=df_btc['Date'], y=df_btc['Close'], 
                            name="BTC 价格",
                            line=dict(color='orange', width=3)
                        ),
                        secondary_y=True,
                    )
                    
                    # --- 新增：动态计算 Y 轴范围 ---
                    # 🔴 修复点：这里必须使用 df_usdt，而不是 df_usdt_hist
                    usdt_min = df_usdt['Supply'].min()
                    usdt_max = df_usdt['Supply'].max()
                    
                    # 给上下留 2% 的缓冲空间
                    y_range_min = usdt_min * 0.98 
                    y_range_max = usdt_max * 1.02
                    
                    fig.update_layout(
                        title_text="<b>USDT 铸造量 (绿) vs BTC 趋势 (橙)</b>",
                        hovermode="x unified",
                        height=450,
                        legend=dict(orientation="h", y=1.1, x=0),
                        margin=dict(l=20, r=20, t=60, b=20)
                    )
                    
                    # --- 关键修改：设置 range 不从 0 开始 ---
                    fig.update_yaxes(
                        title_text="USDT Supply ($)", 
                        secondary_y=False, 
                        showgrid=False,
                        range=[y_range_min, y_range_max] # 强制聚焦波动区间
                    )
            
                    fig.update_yaxes(title_text="BTC Price ($)", secondary_y=True, showgrid=True)
                    st.plotly_chart(fig, use_container_width=True)
                    
                else:
                    st.warning("暂无历史数据。")
            except Exception as e:
                st.error(f"图表加载失败: {e} (请检查 stablecoin_monitor.py 是否添加了 get_asset_history 方法)")

    with col_pie:
        df_stable = load_stablecoin_summary()
        if not df_stable.empty:
            # 1. 简单的数据清洗：太小的份额归类为 "Others" 以免标签太乱
            # (可选，如果不介意小切片可跳过，但建议保留以获得最佳视觉效果)
            df_viz = df_stable.copy()
            total_supply = df_viz['Total Supply'].sum()
            # 过滤掉小于 1% 的币种，防止线条乱飞
            df_viz.loc[df_viz['Total Supply'] / total_supply < 0.01, 'Asset'] = 'Others'
            
            # 2. 绘图
            fig_share = px.pie(
                df_viz, 
                values='Total Supply', 
                names='Asset', 
                title='稳定币市占率', 
                hole=0.5, # 甜甜圈图
                color_discrete_sequence=px.colors.sequential.Teal_r # 颜色主题
            )
            
            # 3. 关键视觉优化
            fig_share.update_traces(
                textposition='inside',   # 强制标签在内部
                textinfo='percent+label' # 显示 名字+百分比
            )
            
            fig_share.update_layout(
                showlegend=False,       # 隐藏图例，省空间
                height=300,             # 高度
                margin=dict(l=10, r=10, t=40, b=10), # 🔥 核心：去得死死的边距
                
                # (可选) 在甜甜圈中间显示总金额，显得很专业
                annotations=[dict(text=f"${total_supply/1e9:.1f}B", x=0.5, y=0.5, font_size=20, showarrow=False)]
            )
            
            st.plotly_chart(fig_share, use_container_width=True)
            
            # 显示关键指标
            total_cap = df_stable['Total Supply'].sum()
            st.metric("稳定币总市值", f"${total_cap/1e9:.2f}B")

    # 下方详细表格
    if not df_stable.empty:
        st.markdown("### 📊 详细资金流向")
        st.dataframe(
            df_stable,
            column_order=("Asset", "Total Supply (B)", "Share", "Flow 24h (M)", "Flow 7d (M)", "Trend (7d)"),
            column_config={
                "Asset": st.column_config.TextColumn("资产"),
                "Total Supply (B)": st.column_config.ProgressColumn("总市值 (Billions)", format="$%.2fB", min_value=0, max_value=int(df_stable['Total Supply (B)'].max())),
                "Share": st.column_config.NumberColumn("市占率", format="%.2f%%"),
                "Flow 24h (M)": st.column_config.NumberColumn("24h 资金流", format="$%.2fM"),
                "Flow 7d (M)": st.column_config.NumberColumn("7d 资金流", format="$%.2fM"),
                "Trend (7d)": st.column_config.TextColumn("趋势"),
            },
            hide_index=True,
            use_container_width=True
        )
# ==============================================================================
# Tab 2: 跨链桥监控
# ==============================================================================
with tab2:
    st.subheader("链上资金热点追踪")
    with st.spinner('正在获取跨链数据...'):
        df_bridge = load_bridge_data()
    
    if not df_bridge.empty:
        df_bridge = df_bridge.sort_values('Volume (24h)', ascending=False).head(20)
        
        # 爆量检测
        surge = df_bridge[df_bridge['Vol Change (24h)'] > 50]
        if not surge.empty:
            st.error(f"🔥 爆量异动: {', '.join(surge['Bridge'].tolist())}")
        
        # 图表
        fig_bridge = px.bar(
            df_bridge, x='Volume (24h)', y='Bridge', orientation='h', text='Chains',
            title='Top 20 跨链桥 24h 交易量', color='Vol Change (24h)', color_continuous_scale='Viridis'
        )
        fig_bridge.update_layout(yaxis={'categoryorder':'total ascending'})
        st.plotly_chart(fig_bridge, use_container_width=True)
        
        # 表格配置
        st.dataframe(
            df_bridge,
            column_config={
                "Volume (24h)": st.column_config.NumberColumn("24h 交易量", format="$%.2f"),
                "Vol Change (24h)": st.column_config.NumberColumn("24h 变化率", format="%.2f%%"),
            },
            hide_index=True,
            use_container_width=True
        )
    else:
        st.warning("暂无数据。")

# ==============================================================================
# Tab 3: 交易所储备
# ==============================================================================
with tab3:
    st.subheader("CEX 资产储备透视")
    with st.spinner('正在扫描交易所钱包...'):
        df_cex = load_exchange_data()
        
    if not df_cex.empty:
        c1, c2 = st.columns([1, 1])
        with c1:
            if 'Total_Reserves_USD' in df_cex.columns:
                fig_cex = px.pie(df_cex, values='Total_Reserves_USD', names='Exchange', title='交易所总资产分布', hole=0.4)
                st.plotly_chart(fig_cex, use_container_width=True)
        
        with c2:
            # 堆叠图看 BTC/ETH
            st.markdown("##### 主流币库存对比")
            if 'BTC' in df_cex.columns and 'ETH' in df_cex.columns:
                # 简单清洗数据（如果是数值则无需清洗）
                st.bar_chart(df_cex.set_index('Exchange')[['BTC', 'ETH']])

        st.dataframe(
            df_cex,
            column_config={
                "Total_Reserves_USD": st.column_config.NumberColumn("总资产 (USD)", format="$%.2f"),
                # 这里假设 BTC/ETH 是浮点数，如果是字符串可能无法格式化，需注意
            },
            hide_index=True,
            use_container_width=True
        )
    else:
        st.warning("暂无数据。")

# ==============================================================================
# Tab 4: 脱钩监控
# ==============================================================================
with tab4:
    st.subheader("稳定币汇率风险扫描")
    with st.spinner('正在检查锚定情况...'):
        df_depeg = load_depeg_data()
        
    if not df_depeg.empty:
        critical = df_depeg[df_depeg['risk_score'] >= 2]
        warning = df_depeg[df_depeg['risk_score'] == 1]
        
        c1, c2 = st.columns(2)
        with c1:
            if not critical.empty:
                st.error(f"🔴 严重脱钩: {', '.join(critical['Asset'].tolist())}")
            else:
                st.success("✅ 无严重脱钩")
        with c2:
            if not warning.empty:
                st.warning(f"🟡 风险警告: {', '.join(warning['Asset'].tolist())}")
            else:
                st.success("✅ 无潜在风险")
        
        # 散点图
        fig_peg = px.scatter(
            df_depeg, x='Asset', y='Price', color='Status',
            color_discrete_map={"✅ Stable": "green", "🟡 Warning": "orange", "🔴 DEPEG CRITICAL": "red"},
            title='价格偏离分布 (Peg $1.00)'
        )
        fig_peg.add_hline(y=1.0, line_dash="dot")
        fig_peg.update_yaxes(range=[0.98, 1.02])
        st.plotly_chart(fig_peg, use_container_width=True)
        
        # 表格配置
        st.dataframe(
            df_depeg,
            column_config={
                "Price": st.column_config.NumberColumn("当前价格", format="$%.4f"),
                "Deviation %": st.column_config.NumberColumn("偏离度", format="%.3f%%"),
            },
            hide_index=True,
            use_container_width=True
        )
    else:
        st.warning("暂无数据。")
    
    # --- 以太坊链上健康监控 ---
    st.markdown("---")
    st.subheader("⛓️ 以太坊链上健康监控")
    
    if st.button("🔄 刷新链上状态", key="refresh_chain") or 'chain_data' not in st.session_state:
        with st.spinner("正在连接以太坊主网..."):
            try:
                from chain_monitor import check_chain_health
                st.session_state['chain_data'] = check_chain_health()
            except ImportError:
                st.info("💡 链上监控模块未安装。请运行: `pip install web3`")
                st.session_state['chain_data'] = None
            except Exception as e:
                st.error(f"❌ 链上监控错误: {e}")
                st.session_state['chain_data'] = None

    if st.session_state.get('chain_data'):
        chain_data = st.session_state['chain_data']
        if chain_data.get("success"):
            ns = chain_data["network_status"]
            
            # 状态指示器
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                status_icon = "🔴" if ns["is_congested"] else "🟢"
                st.metric("网络状态", f"{status_icon} {'拥堵' if ns['is_congested'] else '正常'}")
            with col2:
                gas_icon = {"low": "🟢", "normal": "🟡", "high": "🟠", "extreme": "🔴"}.get(ns["gas_level"], "⚪")
                st.metric("Gas 水平", f"{gas_icon} {ns['current_gas_gwei']:.1f} Gwei")
            with col3:
                util_icon = "🔴" if ns["utilization_pct"] > 95 else "🟡" if ns["utilization_pct"] > 80 else "🟢"
                st.metric("区块利用率", f"{util_icon} {ns['utilization_pct']:.1f}%")
            with col4:
                mev_icon = {"normal": "🟢", "elevated": "🟡", "high": "🔴"}.get(ns["mev_activity"], "⚪")
                st.metric("MEV 活动", f"{mev_icon} {ns['mev_activity'].upper()}")
            
            # Gas 预言机
            if chain_data.get("gas_oracle"):
                go = chain_data["gas_oracle"]
                st.caption(f"💰 **Gas 预言机**: Safe {go['safe_gas']:.1f} | Standard {go['propose_gas']:.1f} | Fast {go['fast_gas']:.1f} Gwei")
            
            # 告警
            if chain_data.get("alerts"):
                for alert in chain_data["alerts"]:
                    st.warning(alert)
            else:
                st.success("✅ 链上无异常告警")
                
        else:
            st.error(f"❌ 无法获取链上数据: {chain_data.get('error')}")
    
    # --- BTC/ETH 原生资产鲸鱼追踪 ---
    st.markdown("---")
    st.subheader("🐋 BTC/ETH 原生资产鲸鱼追踪")
    st.caption("追踪 BTC 和 ETH 原生资产的鲸鱼持仓和大额转账")
    
    col1, col2 = st.columns(2)
    with col1:
        native_asset = st.selectbox("选择资产", ["ETH", "BTC"], key="native_asset_select")
    with col2:
        track_btn = st.button("🔍 追踪鲸鱼", key="track_whale")
    
    if track_btn:
        with st.spinner(f"正在追踪 {native_asset} 鲸鱼..."):
            try:
                from native_asset_tracker import track_native_asset
                st.session_state['native_asset_result'] = track_native_asset(native_asset)
                st.session_state['native_asset_type'] = native_asset
            except ImportError:
                st.info("💡 请确保 native_asset_tracker.py 模块可用")
            except Exception as e:
                st.error(f"❌ 追踪错误: {e}")

    if st.session_state.get('native_asset_result') and st.session_state.get('native_asset_type') == native_asset:
        result = st.session_state['native_asset_result']
        if "error" not in result:
            if native_asset == "ETH":
                supply = result.get("supply", {})
                gas = result.get("gas_prices", {})
                whales = result.get("whale_balances", [])
                
                # 统计指标
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("总供应", f"{supply.get('total_supply', 0)/1e6:.2f}M ETH")
                with col2:
                    st.metric("质押量", f"{supply.get('staked_supply', 0)/1e6:.2f}M ETH")
                with col3:
                    st.metric("Gas", f"{gas.get('propose', 0):.1f} Gwei")
                with col4:
                    st.metric("销毁", f"{supply.get('burnt_fees', 0)/1e6:.2f}M ETH")
                
                # 鲸鱼余额
                if whales:
                    st.markdown("##### 🐋 Top 鲸鱼持仓")
                    whale_df = pd.DataFrame(whales)
                    whale_df.columns = ["地址", "标签", "余额 (ETH)"]
                    whale_df["余额 (ETH)"] = whale_df["余额 (ETH)"].apply(lambda x: f"{x:,.2f}")
                    st.dataframe(whale_df, hide_index=True, use_container_width=True)
            
            elif native_asset == "BTC":
                stats = result.get("stats", {})
                large_txs = result.get("large_transactions", [])
                
                # 统计指标
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("BTC 价格", f"${stats.get('market_price_usd', 0):,.0f}")
                with col2:
                    st.metric("流通供应", f"{stats.get('total_btc', 0)/1e6:.2f}M BTC")
                with col3:
                    st.metric("市值", f"${stats.get('market_cap', 0)/1e9:.0f}B")
                with col4:
                    change = stats.get('price_change_24h', 0)
                    st.metric("24H 涨跌", f"{change:+.2f}%")
                
                # 鲸鱼余额
                whales = result.get("whale_balances", [])
                if whales:
                    st.markdown("##### 🐋 Top 鲸鱼持仓")
                    whale_df = pd.DataFrame(whales)
                    whale_df.columns = ["地址", "标签", "余额 (BTC)"]
                    whale_df["余额 (BTC)"] = whale_df["余额 (BTC)"].apply(lambda x: f"{x:,.2f}")
                    st.dataframe(whale_df, hide_index=True, use_container_width=True)

                # 大额交易
                if large_txs:
                    st.markdown("##### 💰 最近大额交易")
                    for tx in large_txs[:5]:
                        st.info(f"**{tx['btc']:,.2f} BTC** - {tx['time']}")

        else:
            st.error(f"❌ {result.get('error')}")

    # --- Token Concentration Analysis Section ---
    st.markdown("---")
    st.subheader("🐋 代币持仓集中度分析")
    st.caption("分析 ERC-20 代币的鲸鱼持仓、HHI 指数和 OFAC 黑名单风险")
    
    col1, col2 = st.columns([2, 1])
    with col1:
        token_options = {
            "USDT": "0xdac17f958d2ee523a2206206994597c13d831ec7",
            "USDC": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
            "UNI": "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984",
            "LINK": "0x514910771af9ca656af840dff83e8264ecf986ca",
            "AAVE": "0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9",
            "LDO": "0x5a98fcbea516cf06857215779fd812ca3bef1b32",
            "SHIB": "0x95ad61b0a150d79219dcf64e1e6cc01f0b64c4ce",
            "PEPE": "0x6982508145454ce325ddbe47a25d4ec3d2311933",
            "自定义地址": "custom"
        }
        selected_token = st.selectbox("选择代币", list(token_options.keys()))
    
    with col2:
        if selected_token == "自定义地址":
            custom_address = st.text_input("输入 ERC-20 合约地址", "")
        else:
            custom_address = ""
    
    if st.button("🔍 分析代币持仓", key="analyze_token_risk"):
        token_address = custom_address if selected_token == "自定义地址" else token_options[selected_token]
        token_symbol = "" if selected_token == "自定义地址" else selected_token
        
        if not token_address or token_address == "custom":
            st.error("请输入有效的代币合约地址")
        else:
            with st.spinner(f"正在分析 {token_symbol or '代币'} 持仓分布..."):
                try:
                    from token_risk_agent import analyze_token_risk
                    st.session_state['token_risk_result'] = analyze_token_risk(token_address, token_symbol)
                except ImportError:
                    st.info("💡 请安装依赖: `pip install pandas numpy`")
                except Exception as e:
                    st.error(f"❌ 分析错误: {e}")

    if st.session_state.get('token_risk_result'):
        result = st.session_state['token_risk_result']
        if result.get("success"):
            # HHI 分析结果
            hhi = result["hhi"]
            activity = result["activity"]
            
            # 风险等级颜色
            risk_colors = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🔴", "CRITICAL": "🔴"}
            
            # 显示结果
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("HHI 指数", f"{hhi['score'] or 'N/A'}", 
                            help="0-1500=低集中, 1500-2500=中等, >2500=高集中")
            with col2:
                st.metric("Top 10 持仓", f"{hhi['top_10_pct'] or 0:.1f}%")
            with col3:
                st.metric("最大持仓者", f"{hhi['top_holder_pct'] or 0:.1f}%")
            with col4:
                risk_icon = risk_colors.get(result["overall_risk"], "⚪")
                st.metric("综合风险", f"{risk_icon} {result['overall_risk']}")
            
            # 活动分析
            if activity.get("tx_count"):
                st.caption(f"📊 24H 交易: {activity['tx_count']} 笔 | 鲸鱼占比: {activity['whale_ratio']:.1%}" if activity['whale_ratio'] else "")
            
            # 黑名单检查
            if result["blacklist_hits"] > 0:
                st.error(f"⚠️ 发现 {result['blacklist_hits']} 个 OFAC 制裁地址持仓！")
            else:
                st.success("✅ 黑名单检查: 无制裁地址持仓")
            
            # 风险因素
            if result["risk_factors"]:
                st.warning("⚠️ **风险因素**:")
                for factor in result["risk_factors"]:
                    st.markdown(f"  - {factor}")
        else:
            st.error("分析失败，请检查代币地址是否正确")

    # --- Market & Liquidity Risk Section ---
    st.markdown("---")
    st.subheader("📊 市场与流动性风险 (Market & Liquidity Risk)")
    st.caption("监测市场波动、流动性枯竭和价格操纵风险 (Source: Binance, Deribit, DefiLlama)")

    if st.button("🔍 分析市场风险", key="analyze_market_risk"):
        with st.spinner("正在分析市场数据 (Binance/Deribit/DefiLlama)..."):
            try:
                import importlib
                import market_liquidity_monitor
                import derivatives_risk_monitor
                importlib.reload(market_liquidity_monitor)
                importlib.reload(derivatives_risk_monitor)
                from market_liquidity_monitor import CryptoRiskMonitor
                from derivatives_risk_monitor import DerivativesRiskMonitor
                
                monitor = CryptoRiskMonitor()
                deriv_monitor = DerivativesRiskMonitor()
                
                # Fetch all data
                results = {
                    "market": monitor.get_market_volatility_and_volume(),
                    "depth": monitor.get_order_book_depth(),
                    "iv": monitor.get_implied_volatility(),
                    "defi": monitor.get_defi_tvl_risk(),
                    "deriv": {
                        "basic": deriv_monitor.get_basic_metrics(),
                        "ls": deriv_monitor.get_long_short_ratio(),
                        "liq": deriv_monitor.get_recent_liquidations()
                    }
                }
                st.session_state['market_risk_result'] = results
            except ImportError:
                st.info("💡 请安装依赖: `pip install ccxt`")
            except Exception as e:
                st.error(f"❌ 分析错误: {e}")

    # Global Asset & Config Selector for Tab 4
    st.markdown("##### ⚙️ 监控配置 (Configuration)")
    col_sel, col_key = st.columns([2, 1])
    with col_sel:
        deriv_asset = st.selectbox(
            "选择资产 (Select Asset)", 
            ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE"],
            index=0,
            key="deriv_asset_select_global",
            help="切换不同资产以查看其衍生品风险数据"
        )
    with col_key:
        binance_api_key = st.text_input(
            "Binance API Key (Optional)",
            type="password",
            help="输入 API Key 以解锁实时爆仓数据 (Force Orders)",
            key="binance_api_key_input_global"
        )
    
    st.markdown("---")
    if st.session_state.get('market_risk_result'):
        res = st.session_state['market_risk_result']
        
        # 1. 市场波动与交易量
        st.markdown("##### 📉 市场波动与交易量 (BTC/USDT)")
        mkt = res.get("market", {})
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("已实现波动率 (30d)", f"{mkt.get('realized_vol_30d_annualized', 0)}%")
        with col2:
            st.metric("交易量异常倍数", f"{mkt.get('volume_spike_ratio', 0)}x", 
                     delta="High Volume" if mkt.get('volume_spike_ratio', 0) > 1.5 else "Normal")
        with col3:
            st.metric("24H 交易量", f"{mkt.get('volume_24h', 0):,.0f}")
        with col4:
            st.metric("30D 均量", f"{mkt.get('avg_volume_30d', 0):,.0f}")

        # 2. 订单簿深度与滑点
        st.markdown("##### 💧 订单簿深度与滑点")
        depth = res.get("depth", {})
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("深度 (+/- 2%)", f"{depth.get('total_depth_2pct', 0):,.2f} BTC")
        with col2:
            slippage = depth.get('slippage_sim_100k_usdt', 0)
            st.metric("滑点 (1M Buy)", f"{slippage:.4f}%", 
                     delta="-High Slippage" if slippage > 0.5 else "Low Slippage", delta_color="inverse")
        with col3:
            iv = res.get("iv", {})
            st.metric("Deribit DVOL", f"{iv.get('implied_volatility_index') or 'N/A'}")

        # 3. DeFi 流动性风险
        st.markdown("##### 🏦 DeFi 流动性撤出监控 (Uniswap V3)")
        defi = res.get("defi", {})
        
        if "error" in defi:
            st.error(f"⚠️ DeFi 数据获取失败: {defi['error']}")
        else:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("TVL 变动 (24h)", f"{defi.get('tvl_change_24h_pct', 0)}%", 
                        delta="Risk" if defi.get('tvl_change_24h_pct', 0) < -5 else "Stable")
            with col2:
                st.metric("当前 TVL", f"{defi.get('current_tvl', 'N/A')}")
                risk_status = defi.get('risk_alert', 'NORMAL')
                st.metric("风险状态", risk_status, 
                        delta="-ALERT" if risk_status == "HIGH" else "Safe", delta_color="inverse")

        # 4. 衍生品与杠杆风险
        st.markdown("##### 🎰 衍生品与杠杆风险 (Derivatives & Leverage)")
        

        
        # Initialize monitor for dynamic fetching
        from derivatives_risk_monitor import DerivativesRiskMonitor
        deriv_monitor = DerivativesRiskMonitor(api_key=binance_api_key if binance_api_key else None)
        
        # Initialize Real-time Monitor (Singleton)
        @st.cache_resource
        def get_liquidation_monitor():
            from liquidation_monitor import LiquidationMonitor
            return LiquidationMonitor()
            
        liq_monitor = get_liquidation_monitor()
        
        # Start/Switch monitor if needed
        if not binance_api_key:
            liq_monitor.start(deriv_asset)
        
        # Fetch data for selected asset
        with st.spinner(f"正在获取 {deriv_asset} 合约数据..."):
            # ... (fetch basic metrics) ...
            basic = deriv_monitor.get_basic_metrics(deriv_asset)
            ls = deriv_monitor.get_long_short_ratio(deriv_asset)
            
            # Fetch Liquidations (API or WS)
            if binance_api_key:
                liq = deriv_monitor.get_recent_liquidations(deriv_asset)
            else:
                # Use WS stats
                stats = liq_monitor.get_stats()
                liq = {
                    "recent_liquidation_count": stats['count'],
                    "total_liquidation_vol_base": 0, # Not calculated in base yet
                    "long_liquidations_vol": stats['long_vol'], # USD Value
                    "short_liquidations_vol": stats['short_vol'], # USD Value
                    "source": "WebSocket (Session)"
                }

            deriv_data = {
                "basic": basic,
                "ls": ls,
                "liq": liq
            }
            
        # Display Metrics
        if deriv_data:
            basic = deriv_data['basic']
            ls = deriv_data['ls']
            liq = deriv_data['liq']
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("年化持仓成本 (Funding Cost)", f"{basic.get('funding_rate_annualized', 0):.2f}%", 
                         delta="High Risk" if basic.get('funding_rate_annualized', 0) > 50 else "Normal",
                         delta_color="inverse",
                         help="年化后的资金费率。正值代表多头需支付的持仓成本，过高意味着多头拥挤。")
            with col2:
                st.metric("未平仓合约 (OI)", f"${basic.get('open_interest_usd', 0)/1e9:.2f}B")
            with col3:
                # L/S Ratio
                if "error" in ls:
                    source = ls.get('source', 'Unknown')
                    st.metric("多空比 (L/S)", "N/A", help=f"Source: {source}")
                else:
                    source = ls.get('source', 'Unknown')
                    st.metric("多空比 (L/S)", f"{ls.get('ls_ratio', 0):.2f}", help=f"数据来源: {source}")
            with col4:
                # Liquidations
                if "error" in liq and not liq.get('source') == 'WebSocket (Session)':
                    error_msg = liq['error']
                    help_text = f"Error: {error_msg}" if binance_api_key else "需 API Key (Force Orders)"
                    st.metric("爆仓 (最近)", "N/A", help=help_text)
                else:
                    count = liq.get('recent_liquidation_count', 0)
                    long_vol = liq.get('long_liquidations_vol', 0)
                    short_vol = liq.get('short_liquidations_vol', 0)
                    
                    if liq.get('source') == 'WebSocket (Session)':
                        # Show session stats
                        long_c = stats.get('long_count', 0)
                        short_c = stats.get('short_count', 0)
                        
                        tooltip = (
                            f"🟢 多头爆仓: {long_c} 笔 (${long_vol:,.0f})\n"
                            f"🔴 空头爆仓: {short_c} 笔 (${short_vol:,.0f})\n"
                            f"⏱️ 实时监听中..."
                        )
                        st.metric("爆仓 (本会话)", f"{count} 笔", help=tooltip)
                    else:
                        st.metric("爆仓 (最近)", f"{count} 笔", help=f"多头爆仓金额: ${long_vol:,.2f}\n空头爆仓金额: ${short_vol:,.2f}")

    # --- 🐋 巨鲸雷达 (Whale Radar) ---
    st.markdown("---")
    st.subheader("🐋 巨鲸雷达 (Whale Radar - Beta)")
    
    # Initialize Monitor in Session State
    # Always reload module to ensure latest code fixes are applied (Hot-fix for funding rate display)
    if 'whale_monitor' not in st.session_state or st.sidebar.button("🛠️ 重置雷达 (Reset Radar)"):
        import whale_alert_monitor
        import importlib
        importlib.reload(whale_alert_monitor)
        from whale_alert_monitor import WhaleAlertMonitor
        st.session_state['whale_monitor'] = WhaleAlertMonitor(window_size=20)
        st.session_state['whale_result'] = None # Clear cache
        if 'whale_monitor' in st.session_state:
             st.rerun()
    
    # Run Analysis (Only if not cached or refresh requested)
    if 'whale_result' not in st.session_state:
        st.session_state['whale_result'] = None
        
    # Refresh Button
    col_refresh, _ = st.columns([1, 5])
    with col_refresh:
        if st.button("🔄 刷新雷达 (Refresh)"):
            st.session_state['whale_result'] = None # Force refresh
            
    # Fetch Data if needed
    if st.session_state['whale_result'] is None:
        with st.spinner("正在扫描链上数据..."):
            st.session_state['whale_result'] = st.session_state['whale_monitor'].process_data(deriv_asset)
            
    whale_res = st.session_state['whale_result']
    
    if whale_res:
        w_col1, w_col2, w_col3 = st.columns([1, 2, 1])
        
        with w_col1:
            st.metric("Z-Score (OI)", f"{whale_res.get('z_score', 0):.2f}", 
                     delta="High Activity" if abs(whale_res.get('z_score', 0)) > 2.5 else "Normal",
                     help="Z-Score 衡量当前持仓量变化的异常程度。绝对值 > 2.5 视为巨鲸活动。")
            
        with w_col2:
            status = whale_res.get('description', 'Initializing...')
            if whale_res.get('severity') == 'HIGH':
                st.error(f"🚨 {status}")
            else:
                st.info(f"✅ {status}")
                
        with w_col3:
            st.caption(f"Last Update: {whale_res.get('timestamp', datetime.now()).strftime('%H:%M:%S')}")

    # AI Analysis Section
    # Always allow manual analysis or configuration
    is_high_severity = whale_res and whale_res.get('severity') == 'HIGH'
    
    with st.expander("🤖 AI 巨鲸行为分析 (AI Analysis)", expanded=is_high_severity):
            # Provider Selection
            ai_provider = st.radio("选择 AI 模型 (Select Model)", ["OpenAI (GPT-4o)", "DeepSeek-V3"], horizontal=True)
            
            col_ai_key, col_ai_btn = st.columns([3, 1])
            with col_ai_key:
                if "OpenAI" in ai_provider:
                    whale_api_key = st.text_input("OpenAI API Key", type="password", key="whale_ai_key_openai", help="输入 sk-开头的 Key")
                    base_url = None # Use default
                    model_name = "gpt-4o"
                else:
                    whale_api_key = st.text_input("DeepSeek API Key", type="password", key="whale_ai_key_deepseek", help="输入 DeepSeek Key")
                    base_url = "https://api.deepseek.com"
                    model_name = "deepseek-chat"
                    
            with col_ai_btn:
                st.write("") # Spacing
                st.write("") 
                analyze_btn = st.button("🧠 分析主力意图")
            
            if analyze_btn:
                if not whale_api_key:
                    st.warning("请先输入 API Key")
                else:
                    with st.spinner(f"正在调用 {ai_provider} 分析持仓量与资金费率..."):
                        ai_res = st.session_state['whale_monitor'].analyze_signal(
                            whale_res, 
                            api_key=whale_api_key,
                            base_url=base_url,
                            model=model_name
                        )
                        
                        if "error" in ai_res:
                            st.error(f"分析失败: {ai_res['error']}")
                        else:
                            sentiment = ai_res.get('sentiment', 'NEUTRAL').upper()
                            color = "green" if "BULL" in sentiment else "red" if "BEAR" in sentiment else "gray"
                            
                            st.markdown(f"### 🎯 结论: :{color}[{sentiment}]")
                            st.progress(ai_res.get('confidence', 0.5), text=f"置信度: {ai_res.get('confidence', 0)*100:.0f}%")
                            st.success(f"💡 **分析逻辑**: {ai_res.get('reason')}")

# ==============================================================================
# Tab 5: 市场情绪与合约 (Ultimate Edition)
# ==============================================================================
with tab5:
    st.subheader("⚔️ 主力 vs 散户：Binance & Bybit 双重验证")
    
    with st.spinner('正在同步两大交易所数据...'):
        # 接收三个返回值 (适配云端部署)
        fng_data, df_deriv, is_fallback = load_sentiment_data()

    # --- 0. 云端 IP 限制警告 (新增) ---
    if is_fallback:
        st.warning("⚠️ **检测到云端 IP 限制**：Binance/Bybit 数据无法访问，已切换至 CoinGecko 基础行情。\n\n"
                   "👉 **如需查看实时多空比与费率 Alpha，请在本地电脑运行此程序 (开启 VPN)。**")

    # --- 1. 顶部：贪婪指数 (ECharts 3D 动态版) ---
    col_fng, col_info = st.columns([1.5, 2.5]) 
    
    with col_fng:
        if fng_data:
            val = int(fng_data['value'])
            status = fng_data['status']
            
            # ECharts 仪表盘配置
            # ECharts 仪表盘配置
            option = {
                "series": [
                    {
                        "type": "gauge",
                        "startAngle": 180,
                        "endAngle": 0,
                        "min": 0,
                        "max": 100,
                        "splitNumber": 10,
                        "radius": "100%",
                        "center": ["50%", "70%"],
                        "axisLine": {
                            "lineStyle": {
                                "width": 10,
                                "color": [[0.25, "#FF4B4B"], [0.5, "#FFAA00"], [0.75, "#FCD535"], [1, "#00FFAA"]]
                            }
                        },
                        "pointer": {
                            "length": "50%", "width": 5, "offsetCenter": [0, "-10%"],
                            "itemStyle": {"color": "auto"}
                        },
                        "axisTick": {"length": 5, "lineStyle": {"color": "auto", "width": 1}},
                        "splitLine": {"length": 10, "lineStyle": {"color": "auto", "width": 2}},
                        "axisLabel": {"color": "#999", "fontSize": 10, "distance": -30, "formatter": "{value}"},
                        "detail": {
                            "fontSize": 30, "offsetCenter": [0, "-10%"], "valueAnimation": True,
                            "formatter": "{value}", "color": "inherit", "fontWeight": "bold"
                        },
                        "title": {"offsetCenter": [0, "20%"], "fontSize": 16, "color": "#ccc"},
                        "data": [{"value": val, "name": status}]
                    }
                ]
            }
            st_echarts(options=option, height="220px", key="fng_gauge_3d")
            st.caption(f"🕒 更新: {fng_data['update_time']}")
        else:
            st.warning("无法获取贪婪指数")
    
    with col_info:
        st.info("💡 **如何利用双交易所数据?**\n\n"
                "1. **共识信号**: 当两家交易所的多空比同时 > 3.0，表明市场极度拥挤，下跌风险极大。\n"
                "2. **背离信号**: 如果 Binance 费率为正，Bybit 为负，说明主力在某一家交易所定向爆破。\n"
                "3. **L/S Ratio**: 通常 Binance 数值 < Bybit，如果 Binance 反而更高，说明全球散户都在疯狂冲锋。")

    st.divider()

    if not df_deriv.empty:
        # --- 2. 可视化对比 (仅在非降级模式下显示图表) ---
        if not is_fallback:
            st.subheader("📊 核心指标对比")
            
            # 高对比度配色
            COLOR_BINANCE = '#FCD535' 
            COLOR_BYBIT = '#00D4FF'
            
            chart_c1, chart_c2 = st.columns(2)
            
            with chart_c1:
                ls_melt = df_deriv.melt(id_vars='Symbol', value_vars=['Binance LS', 'Bybit LS'], var_name='Exchange', value_name='Ratio')
                fig_ls = px.bar(
                    ls_melt, x='Symbol', y='Ratio', color='Exchange', barmode='group',
                    title='多空比 (L/S Ratio) 对比',
                    color_discrete_map={'Binance LS': COLOR_BINANCE, 'Bybit LS': COLOR_BYBIT}, 
                    height=350
                )
                fig_ls.add_hline(y=2.5, line_dash="dash", line_color="#FF4B4B", annotation_text="Danger Zone")
                fig_ls.update_layout(legend=dict(orientation="h", y=1.1, x=0), xaxis_title=None, plot_bgcolor='rgba(255,255,255,0.05)')
                st.plotly_chart(fig_ls, use_container_width=True)

            with chart_c2:
                fr_melt = df_deriv.melt(id_vars='Symbol', value_vars=['Binance Funding', 'Bybit Funding'], var_name='Exchange', value_name='Rate')
                fig_fr = px.bar(
                    fr_melt, x='Symbol', y='Rate', color='Exchange', barmode='group',
                    title='资金费率 (Funding Rate %) 对比',
                    color_discrete_map={'Binance Funding': COLOR_BINANCE, 'Bybit Funding': COLOR_BYBIT},
                    height=350
                )
                fig_fr.update_layout(legend=dict(orientation="h", y=1.1, x=0), xaxis_title=None, plot_bgcolor='rgba(255,255,255,0.05)')
                st.plotly_chart(fig_fr, use_container_width=True)

        # --- 3. 详细数据表格 ---
        st.subheader("📋 详细监控面板")
        
        # 动态调整列配置 (降级模式下不显示多空比进度条)
        if is_fallback:
             column_config_settings = {
                "Symbol": "资产",
                "Price": st.column_config.NumberColumn("价格 ($)", format="$%.2f"),
                "Note": "状态备注"
             }
        else:
             column_config_settings = {
                "Symbol": "资产",
                "Price": st.column_config.NumberColumn("价格 ($)", format="$%.2f"),
                "Binance Funding": st.column_config.NumberColumn("Binance 费率", format="%.4f%%"),
                "Binance LS": st.column_config.ProgressColumn("Binance 多空比", min_value=0, max_value=5, format="%.2f"),
                "Bybit Funding": st.column_config.NumberColumn("Bybit 费率", format="%.4f%%"),
                "Bybit LS": st.column_config.ProgressColumn("Bybit 多空比", min_value=0, max_value=5, format="%.2f"),
                "Note": "状态"
            }

        st.dataframe(
            df_deriv,
            column_config=column_config_settings,
            hide_index=True,
            use_container_width=True
        )

    else:
        st.error("数据加载失败，请检查网络连接。")
            
    st.markdown("---")
    st.subheader("🤖 AI 量化决策大脑 (Powered by LangGraph)")

    with st.expander("🔑 设置 OpenAI API Key (点击展开)", expanded=False):
        api_key = st.text_input("输入 sk-开头的 Key", type="password", key="openai_key")
        st.caption("提示: 你的 Key 仅用于当前会话，不会被保存。")

    if st.button("🧠 启动 AI 分析 (Generate Alpha)", type="primary"):
        if not api_key:
            st.warning("请先输入 OpenAI API Key！")
        elif df_deriv.empty:
            st.error("没有数据可供分析。")
        else:
            agent = CryptoQuantAgent(api_key)
            status_box = st.status("🤖 AI 正在读取链上数据...", expanded=True)
            try:
                status_box.write("🔍 正在对比 Binance vs Bybit 数据背离...")
                analysis_text = agent.run_analysis(df_deriv, fng_data)
                status_box.write("✅ 分析完成！")
                status_box.update(label="分析完成", state="complete", expanded=False)
                st.markdown("### 📝 机构级投资备忘录")
                st.markdown(analysis_text)
            except Exception as e:
                status_box.update(label="分析失败", state="error")
                st.error(f"AI 运行出错: {e}")

# ==============================================================================
# Tab 6: Multi-Agent Lab (New)
# ==============================================================================
with tab6:
    st.subheader("🧠 Multi-Agent Quant Lab")
    st.caption("Powered by LangGraph: Indicator, Pattern, Trend, Volume & Decision Agents")
    
    col_input, col_res = st.columns([1, 3])
    
    with col_input:
        st.markdown("### ⚙️ Configuration")
        ma_ticker = st.text_input("Ticker Symbol", value="BTC-USD", help="e.g. BTC-USD, ETH-USD, NVDA")
        ma_timeframe = st.selectbox("Timeframe", ["15m", "1h", "4h", "1d"], index=1)
        
        ma_api_key = st.text_input("OpenAI API Key", type="password", key="ma_openai_key")
        
        if st.button("🚀 Start Multi-Agent Analysis", type="primary"):
            if not ma_api_key:
                st.warning("Please enter OpenAI API Key.")
            else:
                with st.spinner("🤖 Agents are analyzing market data... (This may take 30-60s)"):
                    result = run_multi_agent_analysis(ma_api_key, ma_ticker, ma_timeframe)
                    
                    if "error" in result:
                        st.error(f"Analysis Failed: {result['error']}")
                    else:
                        st.session_state['ma_result'] = result
                        st.success("Analysis Complete!")

    with col_res:
        if 'ma_result' in st.session_state:
            res = st.session_state['ma_result']
            
            # Parse and display Final Decision beautifully
            decision_raw = res.get('final_trade_decision', 'N/A')
            st.markdown("### 🎯 Final Decision")
            
            # Try to parse JSON from the decision
            import json
            import re
            try:
                # Extract JSON from the response
                json_match = re.search(r'\{[^{}]*\}', decision_raw)
                if json_match:
                    decision_data = json.loads(json_match.group())
                    
                    # Display decision with color-coded badge
                    decision_type = decision_data.get('decision', 'N/A')
                    if decision_type == 'LONG':
                        st.success(f"🚀 **{decision_type}** Position Recommended")
                    elif decision_type == 'SHORT':
                        st.error(f"📉 **{decision_type}** Position Recommended")
                    else:
                        st.info(f"⚖️ **{decision_type}**")
                    
                    # Display details in columns
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("Forecast Horizon", decision_data.get('forecast_horizon', 'N/A'))
                    with col2:
                        st.metric("Risk/Reward Ratio", decision_data.get('risk_reward_ratio', 'N/A'))
                    
                    # Display justification
                    st.markdown("**📝 Justification:**")
                    st.markdown(decision_data.get('justification', 'No justification provided.'))
                else:
                    # Fallback: display raw text
                    st.info(decision_raw)
            except (json.JSONDecodeError, Exception) as e:
                # Fallback: display raw text
                st.info(decision_raw)
            
            with st.expander("📊 Technical Indicator Report", expanded=False):
                st.markdown(res.get('indicator_report', 'No report'))
                
            with st.expander("🕯️ Pattern Recognition Report", expanded=False):
                st.markdown(res.get('pattern_report', 'No report'))
                # Show image if available
                if os.path.exists("kline_chart.png"):
                    st.image("kline_chart.png", caption="Pattern Chart")

            with st.expander("📈 Trend Analysis Report", expanded=False):
                st.markdown(res.get('trend_report', 'No report'))
                if os.path.exists("trend_graph.png"):
                    st.image("trend_graph.png", caption="Trend Chart")

            with st.expander("📊 Volume Analysis Report", expanded=False): # [NEW]
                st.markdown(res.get('volume_report', 'No report'))# Tab 7 Content - to be appended to app.py
# ============================================================================== 
# Tab 7: Reddit Sentiment Analysis
# ==============================================================================
with tab7:
    st.subheader("📱 Reddit Sentiment Analysis - r/CryptoCurrency")
    st.markdown("*Analyze sentiment from Reddit posts using VADER (no API required)*")
    
    # Configuration Panel
    col_config1, col_config2, col_config3 = st.columns(3)
    
    with col_config1:
        filter_type = st.selectbox(
            "Filter",
            options=["hot", "new", "top"],
            index=0,
            help="Select post filter type"
        )
    
    with col_config2:
        post_limit = st.number_input(
            "Number of Posts",
            min_value=10,
            max_value=500,
            value=100,
            step=10,
            help="Number get posts to analyze"
        )
    
    with col_config3:
        if filter_type == "top":
            time_range = st.selectbox(
                "Time Range",
                options=["hour", "day", "week", "month", "year"],
                index=1
            )
        else:
            time_range = None
    
    # Fetch Button
    if st.button("🔍 Fetch & Analyze (Auto-Fallback)", type="primary"):
        with st.spinner("正在尝试多源抓取 (Mirrors + CURL)..."):
            try:
                # Initialize analyzer
                from sentiment.reddit_sentiment import RedditSentimentAnalyzer
                analyzer = RedditSentimentAnalyzer()
                
                st.info(f"📍 正在抓取 r/CryptoCurrency 的 {post_limit} 条 {filter_type} 帖子...")
                if filter_type == "top" and time_range:
                    st.info(f"⏰ 时间范围: {time_range}")
                
                # Scrape posts directly (now uses Selenium)
                posts = analyzer.scrape_reddit_posts(
                    subreddit='CryptoCurrency',
                    filter_type=filter_type,
                    count=post_limit,
                    time_range=time_range
                )
                
                if not posts:
                    st.warning("⚠️ 未能抓取到帖子 (Failed to fetch posts)")
                    st.error("Reddit 对云端服务器 IP (Streamlit Cloud) 有严格的封锁机制。")
                    st.info("💡 **解决方案**: 请在本地电脑运行此程序 (Localhost)，通常可以正常访问。\n\n"
                            "**To run locally:** `streamlit run app.py`")
                    st.caption("技术细节: Reddit API 返回 403 Forbidden 或 429 Too Many Requests，这是因为数据中心 IP 被列入了黑名单。")
                    st.warning("请检查网络连接，或稍后再试。")
                else:
                    # Analyze sentiments
                    posts = analyzer.analyze_posts(posts)
                    
                    # Store in session state
                    st.session_state['reddit_posts'] = posts
                    st.session_state['analyzer'] = analyzer
                    
                    st.success(f"✅ 成功分析 {len(posts)} 条帖子")
                    
            except Exception as e:
                st.error(f"❌ 错误: {str(e)}")
                import traceback
                with st.expander("查看错误堆栈"):
                    st.code(traceback.format_exc())
    
    # Display Results
    if 'reddit_posts' in st.session_state and st.session_state['reddit_posts']:
        posts = st.session_state['reddit_posts']
        analyzer = st.session_state.get('analyzer')
        
        # === Sentiment Overview ===
        st.markdown("---")
        st.markdown("### 📊 Sentiment Overview")
        
        # Calculate metrics
        distribution = analyzer.get_sentiment_distribution(posts)
        avg_compound = sum([p.sentiment_scores['compound'] for p in posts if p.sentiment_scores]) / len(posts)
        
        # Metric cards
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        
        with col_m1:
            st.metric("Total Posts", len(posts))
        
        with col_m2:
            st.metric("Avg Sentiment", f"{avg_compound:.3f}")
        
        with col_m3:
            positive_pct = distribution['positive'] / len(posts) * 100
            st.metric("Positive %", f"{positive_pct:.1f}%")
        
        with col_m4:
            negative_pct = distribution['negative'] / len(posts) * 100
            st.metric("Negative %", f"{negative_pct:.1f}%")
        
        # Sentiment Distribution Pie Chart
        col_chart1, col_chart2 = st.columns(2)
        
        with col_chart1:
            fig_pie = go.Figure(data=[go.Pie(
                labels=['Positive', 'Neutral', 'Negative'],
                values=[distribution['positive'], distribution['neutral'], distribution['negative']],
                marker_colors=['#00D26A', '#FFB800', '#FF3838']
            )])
            fig_pie.update_layout(title="Sentiment Distribution", height=350)
            st.plotly_chart(fig_pie, use_container_width=True)
        
        with col_chart2:
            # Sentiment by coin
            coin_agg = analyzer.aggregate_by_coin(posts)
            if coin_agg:
                df_coins = pd.DataFrame([
                    {
                        'Coin': coin,
                        'Avg Sentiment': data['avg_compound'],
                        'Posts': data['post_count']
                    }
                    for coin, data in coin_agg.items()
                ]).sort_values('Avg Sentiment', ascending=False).head(10)
                
                fig_bar = px.bar(
                    df_coins,
                    x='Coin',
                    y='Avg Sentiment',
                    color='Avg Sentiment',
                    color_continuous_scale='RdYlGn',
                    title="Top 10 Coins by Sentiment"
                )
                fig_bar.add_hline(y=0, line_dash="dash", line_color="gray")
                fig_bar.update_layout(height=350)
                st.plotly_chart(fig_bar, use_container_width=True)
        
        # === Coin Sentiment Table ===
        st.markdown("---")
        st.markdown("### 🪙 Cryptocurrency Sentiment")
        
        if coin_agg:
            df_table = pd.DataFrame([
                {
                    'Coin': coin,
                    'Avg Sentiment': f"{data['avg_compound']:.3f}",
                    'Positive': f"{data['avg_pos']:.2f}",
                    'Negative': f"{data['avg_neg']:.2f}",
                    'Neutral': f"{data['avg_neu']:.2f}",
                    'Mentions': data['post_count']
                }
                for coin, data in coin_agg.items()
            ]).sort_values('Avg Sentiment', ascending=False)
            
            st.dataframe(df_table, use_container_width=True, height=300)
        
        # === Top Posts ===
        st.markdown("---")
        st.markdown("### 📰 Top Posts by Sentiment")
        
        tab_neg, tab_pos = st.tabs(["Most Negative 😞", "Most Positive 😊"])
        
        with tab_neg:
            top_negative = analyzer.get_top_posts(posts, by='negative', limit=5)
            for i, post in enumerate(top_negative, 1):
                with st.expander(f"#{i} - Sentiment: {post.sentiment_scores['compound']:.3f}"):
                    st.markdown(f"**{post.title}**")
                    if post.selftext:
                        st.markdown(f"> {post.selftext[:200]}...")
                    col_p1, col_p2, col_p3 = st.columns(3)
                    with col_p1:
                        st.metric("Upvotes", post.upvotes)
                    with col_p2:
                        st.metric("Comments", post.num_comments)
                    with col_p3:
                        st.markdown(f"[View on Reddit]({post.url})")
        
        with tab_pos:
            top_positive = analyzer.get_top_posts(posts, by='positive', limit=5)
            for i, post in enumerate(top_positive, 1):
                with st.expander(f"#{i} - Sentiment: {post.sentiment_scores['compound']:.3f}"):
                    st.markdown(f"**{post.title}**")
                    if post.selftext:
                        st.markdown(f"> {post.selftext[:200]}...")
                    col_p1, col_p2, col_p3 = st.columns(3)
                    with col_p1:
                        st.metric("Upvotes", post.upvotes)
                    with col_p2:
                        st.metric("Comments", post.num_comments)
                    with col_p3:
                        st.markdown(f"[View on Reddit]({post.url})")

    # -----------------------------------------------------------------------------
    # Tab 8: Strategy Backtest
    # -----------------------------------------------------------------------------
    with tab8:
        st.header("🛠️ Technical Indicator Backtest (Beta)")
        st.caption("Verify the historical accuracy of technical indicators before trading.")
        
        col_b1, col_b2, col_b3 = st.columns(3)
        with col_b1:
            bt_symbol = st.selectbox("Symbol", ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"], key="bt_symbol")
        with col_b2:
            bt_timeframe = st.selectbox("Timeframe", ["15m", "1h", "4h", "1d"], index=1, key="bt_timeframe")
        with col_b3:
            bt_horizon = st.slider("Forecast Horizon (Candles)", min_value=1, max_value=10, value=3, key="bt_horizon", help="Predict price movement N candles into the future")
            bt_limit = st.select_slider("Data Limit (Candles)", options=[500, 1000, 2000, 3000, 5000], value=1000, key="bt_limit")
        
        st.markdown("##### 🛡️ Risk Management")
        col_r1, col_r2 = st.columns(2)
        with col_r1:
            bt_sl = st.slider("Stop Loss (%) (0 = Disable)", min_value=0.0, max_value=10.0, value=2.0, step=0.1, key="bt_sl") / 100
        with col_r2:
            bt_tp = st.slider("Take Profit (%) (0 = Disable)", min_value=0.0, max_value=20.0, value=4.0, step=0.1, key="bt_tp") / 100
        
        bt_ts = st.slider("Trailing Stop (%) (0 = Disable)", min_value=0.0, max_value=10.0, value=0.0, step=0.1, key="bt_ts") / 100
        
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            bt_trend_filter = st.checkbox("🌊 Trend Filter (EMA 200)", value=False, help="Only Buy when Price > EMA 200, Only Sell when Price < EMA 200")
        with col_f2:
            bt_adx = st.slider("🌪️ ADX Filter (0 = Disable)", min_value=0, max_value=50, value=0, step=1, help="Only trade when ADX > Threshold (Strong Trend)")
            
        if st.button("🚀 Run Backtest", type="primary"):
            with st.spinner(f"Backtesting {bt_symbol} on {bt_timeframe} data (Last {bt_limit} candles)..."):
                try:
                    import backtest_engine
                    import importlib
                    importlib.reload(backtest_engine)
                    from backtest_engine import BacktestEngine
                    
                    engine = BacktestEngine()
                    res = engine.run_backtest(symbol=bt_symbol, timeframe=bt_timeframe, horizon=bt_horizon, stop_loss=bt_sl, take_profit=bt_tp, limit=bt_limit, use_trend_filter=bt_trend_filter, trailing_stop=bt_ts, adx_threshold=bt_adx)
                    
                    if "error" in res:
                        st.error(res['error'])
                    else:
                        st.session_state['bt_results'] = res
                        st.success(f"Backtest Complete! Analyzed {res['data_points']} candles.")
                        
                except Exception as e:
                    st.error(f"Backtest failed: {str(e)}")

        # Check if results exist in session state and render
        if 'bt_results' in st.session_state:
            res = st.session_state['bt_results']
            
            # Validation: Check if the cached results have the new PnL keys AND the new MACD column
            # If not (stale data), clear session state and stop rendering
            first_key = list(res['results'].keys())[0]
            if ('Total Return' not in res['results'][first_key] or 
                'Total Signals' not in res['results'][first_key] or 
                'MACD_Signal_Line' not in res['df'].columns or
                'WillR_EMA' not in res['df'].columns):
                del st.session_state['bt_results']
                st.warning("⚠️ Backtest engine updated. Please click 'Run Backtest' again to generate new PnL metrics.")
                st.stop()

            # Re-instantiate engine for PnL calculation if needed (or make method static)
            # Ideally, we should import it again just in case
            from backtest_engine import BacktestEngine
            engine = BacktestEngine()

            # Process results for display
            results = res['results']
            rows = []
            for ind, metrics in results.items():
                rows.append({
                    "Indicator": ind,
                    "Total Return (PnL)": f"{metrics['Total Return']}%",
                    "Max Drawdown": f"{metrics['Max Drawdown']}%",
                    "Win Rate (Total)": f"{metrics['Win Rate']}%",
                    "Buy Win Rate": f"{metrics['Buy Win Rate']}%",
                    "Sell Win Rate": f"{metrics['Sell Win Rate']}%",
                    "Buy Signals": metrics['Buy Signals'],
                    "Sell Signals": metrics['Sell Signals'],
                    "Total Signals": metrics['Buy Signals'] + metrics['Sell Signals']
                })
            
            df_res = pd.DataFrame(rows)
            
            # Display Metrics
            # Select Best Performer based on Total Return
            best_ind = max(results.items(), key=lambda x: x[1]['Total Return'])
            
            col_m1, col_m2, col_m3 = st.columns(3)
            with col_m1:
                st.metric("🏆 Best Performer", f"{best_ind[0]}", f"{best_ind[1]['Total Return']}% Return")
            with col_m2:
                st.metric("🎯 Win Rate", f"{best_ind[1]['Win Rate']}%", f"{best_ind[1]['Total Signals']} Trades")
            with col_m3:
                st.metric("📉 Max Drawdown", f"{best_ind[1]['Max Drawdown']}%", "Risk Metric")

            
            # Display Table with highlighting
            st.markdown("### 📊 Indicator Performance Matrix")
            st.dataframe(
                df_res.style.applymap(
                    lambda x: 'color: green' if float(x.strip('%')) > 0 else 'color: red',
                    subset=['Total Return (PnL)']
                ).applymap(
                    lambda x: 'color: green' if float(x.strip('%')) > 50 else 'color: red',
                    subset=['Win Rate (Total)']
                ),
                use_container_width=True
            )
            
            # Insight
            st.info(f"💡 **Insight**: {best_ind[0]} is the most profitable indicator with a **{best_ind[1]['Total Return']}%** return (simulated) over the last {bt_limit} candles.")
            
            # --- Visualization Section ---
            st.markdown("---")
            st.subheader("📈 Strategy Visualization")
            
            # Selector for indicator to visualize
            viz_ind = st.selectbox("Select Indicator to Visualize", list(results.keys()), index=list(results.keys()).index(best_ind[0]))
            
            # Calculate PnL for visualization
            # Use the stored SL/TP from results if available, otherwise default (though results should have them)
            sl_val = res.get('stop_loss', 0.02)
            tp_val = res.get('take_profit', 0.04)
            ts_val = res.get('trailing_stop', 0.0)
            df_viz = engine.calculate_pnl_curve(res['df'], viz_ind, horizon=res['horizon'], stop_loss=sl_val, take_profit=tp_val, trailing_stop=ts_val)
            
            # 1. Candlestick Chart with Signals AND Indicator Subplot
            from plotly.subplots import make_subplots
            
            # Create subplots: Row 1 = Price, Row 2 = Indicator
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                                vertical_spacing=0.05, row_heights=[0.7, 0.3],
                                subplot_titles=(f"{res['symbol']} Price & Signals", f"{viz_ind} Indicator"))
            
            # --- Row 1: Price & Signals ---
            # Candlestick
            fig.add_trace(go.Candlestick(
                x=df_viz['timestamp'],
                open=df_viz['open'],
                high=df_viz['high'],
                low=df_viz['low'],
                close=df_viz['close'],
                name='Price'
            ), row=1, col=1)

            # Add EMA 200 if available
            if 'EMA_200' in df_viz.columns:
                fig.add_trace(go.Scatter(
                    x=df_viz['timestamp'],
                    y=df_viz['EMA_200'],
                    mode='lines',
                    line=dict(color='yellow', width=1),
                    name='EMA 200 (Trend)'
                ), row=1, col=1)
            
            # Buy Signals
            buy_signals = df_viz[df_viz[f'{viz_ind}_Signal'] == 1]
            fig.add_trace(go.Scatter(
                x=buy_signals['timestamp'],
                y=buy_signals['low'] * 0.99, # Slightly below candle
                mode='markers',
                marker=dict(symbol='triangle-up', size=10, color='green'),
                name='Buy Signal'
            ), row=1, col=1)
            
            # Sell Signals
            sell_signals = df_viz[df_viz[f'{viz_ind}_Signal'] == -1]
            fig.add_trace(go.Scatter(
                x=sell_signals['timestamp'],
                y=sell_signals['high'] * 1.01, # Slightly above candle
                mode='markers',
                marker=dict(symbol='triangle-down', size=10, color='red'),
                name='Sell Signal'
            ), row=1, col=1)
            
            # --- Row 2: Indicator Values ---
            # Plot the main indicator line
            # Handle different indicators (some have multiple lines like MACD/Stoch)
            if viz_ind == 'MACD':
                fig.add_trace(go.Scatter(x=df_viz['timestamp'], y=df_viz['MACD'], name='MACD', line=dict(color='cyan')), row=2, col=1)
                fig.add_trace(go.Scatter(x=df_viz['timestamp'], y=df_viz['MACD_Signal_Line'], name='Signal', line=dict(color='orange')), row=2, col=1)
                fig.add_trace(go.Bar(x=df_viz['timestamp'], y=df_viz['MACD_Hist'], name='Hist'), row=2, col=1)
            elif viz_ind == 'Stoch':
                fig.add_trace(go.Scatter(x=df_viz['timestamp'], y=df_viz['Stoch_K'], name='%K', line=dict(color='cyan')), row=2, col=1)
                fig.add_trace(go.Scatter(x=df_viz['timestamp'], y=df_viz['Stoch_D'], name='%D', line=dict(color='orange')), row=2, col=1)
                fig.add_hline(y=20, line_dash="dash", line_color="gray", row=2, col=1)
                fig.add_hline(y=80, line_dash="dash", line_color="gray", row=2, col=1)
            elif viz_ind == 'RSI':
                fig.add_trace(go.Scatter(x=df_viz['timestamp'], y=df_viz['RSI'], name='RSI', line=dict(color='purple')), row=2, col=1)
                fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)
                fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
            elif viz_ind == 'WillR':
                fig.add_trace(go.Scatter(x=df_viz['timestamp'], y=df_viz['WillR_EMA'], name='WillR (Smoothed)', line=dict(color='blue')), row=2, col=1)
                fig.add_hline(y=-20, line_dash="dash", line_color="red", row=2, col=1)
                fig.add_hline(y=-80, line_dash="dash", line_color="green", row=2, col=1)
            elif viz_ind == 'ROC':
                fig.add_trace(go.Scatter(x=df_viz['timestamp'], y=df_viz['ROC'], name='ROC', line=dict(color='yellow')), row=2, col=1)
                fig.add_hline(y=0, line_dash="dash", line_color="white", row=2, col=1)

            fig.update_layout(
                height=800,
                template="plotly_dark",
                xaxis_rangeslider_visible=False
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # 2. Equity Curve
            st.subheader("💰 Equity Curve (Simulated)")
            st.caption(f"Simulation: Start with $1000, Enter on Signal, Exit after {res['horizon']} candles. **Includes 0.1% Trading Fee per trade.**")
            
            # Calculate Buy & Hold Equity
            initial_price = df_viz['close'].iloc[0]
            df_viz['Buy_Hold_Equity'] = 1000 * (df_viz['close'] / initial_price)
            bh_return = (df_viz['Buy_Hold_Equity'].iloc[-1] - 1000) / 1000 * 100
            
            fig_pnl = go.Figure()
            
            # Strategy Equity
            fig_pnl.add_trace(go.Scatter(
                x=df_viz['timestamp'],
                y=df_viz['Equity'],
                mode='lines',
                name=f'{viz_ind} Strategy',
                line=dict(color='gold', width=2)
            ))
            
            # Buy & Hold Equity
            fig_pnl.add_trace(go.Scatter(
                x=df_viz['timestamp'],
                y=df_viz['Buy_Hold_Equity'],
                mode='lines',
                name='Buy & Hold (Benchmark)',
                line=dict(color='gray', dash='dash')
            ))
            
            # Calculate Max Drawdown
            peak = df_viz['Equity'].cummax()
            drawdown = (df_viz['Equity'] - peak) / peak
            max_dd = drawdown.min() * 100
            final_equity = df_viz['Equity'].iloc[-1]
            total_return = (final_equity - 1000) / 1000 * 100
            
            fig_pnl.update_layout(
                title=f"Total Return: {total_return:.2f}% (Strategy) vs {bh_return:.2f}% (Buy & Hold) | Max Drawdown: {max_dd:.2f}%",
                xaxis_title="Time",
                yaxis_title="Equity ($)",
                height=400,
                template="plotly_dark"
            )
            st.plotly_chart(fig_pnl, use_container_width=True)

    # -----------------------------------------------------------------------------
    # Tab 9: Twitter Sentiment Analysis
    # -----------------------------------------------------------------------------
    with tab9: # Changed from tab8 to tab9 to accommodate the new tab
        st.header("🐦 Twitter Sentiment Analysis (Beta)")
        st.markdown("Analyze real-time sentiment from Twitter using AI (BERT) models.")
        
        # Check login status
        import os
        cookies_path = 'cookies.json'
        is_logged_in = os.path.exists(cookies_path)
        
        if not is_logged_in:
            st.warning("⚠️ You are not logged in to Twitter.")
            st.markdown("### 🔐 Setup Method")
            
            # Show guide link
            st.info("📖 **推荐方法**: 手动导入 Cookies（更稳定）- 查看 `TWITTER_COOKIES_GUIDE.md` 获取详细步骤")
            
            login_method = st.radio(
                "选择登录方式：",
                ["🍪 手动导入 Cookies (推荐)", "🔑 自动登录 (可能失败)"],
                index=0
            )
            
            if login_method == "🍪 手动导入 Cookies (推荐)":
                st.markdown("#### 手动导入 Cookies")
                st.markdown("""
                **步骤**:
                1. 在浏览器中登录 [Twitter](https://twitter.com)
                2. 按 `F12` 打开开发者工具
                3. 切换到 "Application" 标签 → "Cookies" → "https://twitter.com"
                4. 找到并复制以下两个 cookies 的值：
                   - `auth_token` (必填)
                   - `ct0` (必填 - CSRF token)
                5. 粘贴到下方文本框
                """)
                
                auth_token = st.text_input("auth_token (必填)", type="password", help="从浏览器复制的 auth_token cookie 值")
                ct0 = st.text_input("ct0 (必填)", type="password", help="从浏览器复制的 ct0 cookie 值 - 这是 CSRF token，必须提供")
                
                if st.button("💾 保存 Cookies", type="primary"):
                    if not auth_token or not ct0:
                        st.error("⚠️ auth_token 和 ct0 都是必填的！Twitter API 需要这两个 cookies 才能工作。")
                    else:
                        try:
                            import json
                            # Create cookies in twikit-compatible format
                            cookies = {
                                "auth_token": {
                                    "value": auth_token,
                                    "domain": ".twitter.com",
                                    "path": "/"
                                }
                            }
                            
                            if ct0:
                                cookies["ct0"] = {
                                    "value": ct0,
                                    "domain": ".twitter.com",
                                    "path": "/"
                                }
                            
                            # Save to cookies.json
                            with open(cookies_path, 'w') as f:
                                json.dump(cookies, f, indent=2)
                            
                            st.success("✅ Cookies 已保存！正在刷新...")
                            time.sleep(1)
                            st.rerun()
                        except Exception as e:
                            st.error(f"保存失败: {e}")
            
            else:
                st.warning("⚠️ 自动登录可能因 Cloudflare 保护而失败，建议使用手动导入方式")
                with st.form("twitter_login_form"):
                    username = st.text_input("Twitter Username")
                    email = st.text_input("Twitter Email")
                    password = st.text_input("Twitter Password", type="password")
                    
                    submitted = st.form_submit_button("Login & Save Cookies")
                    
                    if submitted:
                        if not (username and email and password):
                            st.error("Please fill in all fields.")
                        else:
                            with st.spinner("Logging in to Twitter... (This may take a few seconds)"):
                                os.environ['TWITTER_USERNAME'] = username
                                os.environ['TWITTER_EMAIL'] = email
                                os.environ['TWITTER_PASSWORD'] = password
                                
                                import asyncio
                                from sentiment.twitter_auth import login
                                success = asyncio.run(login())
                                
                                if success:
                                    st.success("✅ Login successful! Please refresh the page.")
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.error("❌ Login failed. 建议使用上方的 '手动导入 Cookies' 方式")
        
        else:
            st.success("✅ Logged in to Twitter")
            
            # Analysis UI
            col1, col2 = st.columns([3, 1])
            with col1:
                # Common coins list
                common_queries = [
                    "Bitcoin ($BTC)", 
                    "Ethereum ($ETH)", 
                    "Solana ($SOL)", 
                    "Dogecoin ($DOGE)", 
                    "Ripple ($XRP)", 
                    "BNB ($BNB)",
                    "Cardano ($ADA)",
                    "Custom (自定义)"
                ]
                
                selected_query = st.selectbox("Select Asset (选择资产)", common_queries, index=0)
                
                if selected_query == "Custom (自定义)":
                    query = st.text_input("Search Query (e.g., $SOL, Bitcoin, #Crypto)", value="Bitcoin")
                else:
                    # Map selection to search query
                    query_map = {
                        "Bitcoin ($BTC)": "Bitcoin",
                        "Ethereum ($ETH)": "Ethereum",
                        "Solana ($SOL)": "$SOL",
                        "Dogecoin ($DOGE)": "$DOGE",
                        "Ripple ($XRP)": "$XRP",
                        "BNB ($BNB)": "$BNB",
                        "Cardano ($ADA)": "$ADA"
                    }
                    query = query_map.get(selected_query, "Bitcoin")
                    st.caption(f"🔎 Searching for: `{query}`")
            with col2:
                tweet_count = st.number_input("Max Tweets", min_value=10, max_value=200, value=20)

            # AI Narrative Config
            with st.expander("🤖 AI Narrative Settings (Optional)", expanded=False):
                t_ai_provider = st.radio("Select AI Model", ["OpenAI (GPT-4o)", "DeepSeek-V3"], horizontal=True, key="twitter_ai_provider")
                if "OpenAI" in t_ai_provider:
                    t_api_key = st.text_input("OpenAI API Key", type="password", key="twitter_openai_key")
                    t_base_url = None
                    t_model = "gpt-4o"
                else:
                    t_api_key = st.text_input("DeepSeek API Key", type="password", key="twitter_deepseek_key")
                    t_base_url = "https://api.deepseek.com"
                    t_model = "deepseek-chat"
            
            if st.button("🔍 Analyze Twitter Sentiment", type="primary"):
                with st.spinner("Fetching tweets and analyzing sentiment (Loading AI models)..."):
                    try:
                        import asyncio
                        from sentiment.twitter_sentiment import TwitterSentimentAnalyzer
                        
                        analyzer = TwitterSentimentAnalyzer()
                        
                        # Run async fetch
                        tweets = asyncio.run(analyzer.fetch_tweets(query, tweet_count))
                        
                        if not tweets:
                            st.warning("No tweets found or error fetching tweets.")
                        else:
                            # Analyze
                            result = analyzer.analyze_sentiment(tweets)

                            # 3. AI Narrative Summary (if Key provided)
                            narrative_summary = None
                            if t_api_key:
                                with st.spinner("🤖 Generating AI Narrative Summary..."):
                                    narrative_summary = analyzer.generate_narrative_summary(
                                        tweets, 
                                        api_key=t_api_key,
                                        provider="DeepSeek-V3" if "DeepSeek" in t_ai_provider else "OpenAI",
                                        base_url=t_base_url,
                                        model_name=t_model
                                    )
                            
                            # Display Results
                            st.markdown("### 📊 Sentiment Results")

                            # Display AI Summary if available
                            if narrative_summary:
                                st.info(narrative_summary, icon="🤖")
                            
                            # Metrics
                            m1, m2, m3 = st.columns(3)
                            m1.metric("Sentiment Score", f"{result['score']:.2f}", delta=result['label'])
                            m2.metric("Tweets Analyzed", result['count'])
                            m3.metric("Dominant Emotion", max(result['distribution'], key=result['distribution'].get))
                            
                            # Model Breakdown
                            with st.expander("🧠 Model Score Breakdown (Details)", expanded=False):
                                st.caption("Individual model scores (Range: -1.0 to 1.0)")
                                
                                # Extract AI Score if available
                                ai_score = None
                                if narrative_summary:
                                    import re
                                    match = re.search(r"\*\*🎯 AI Score\*\*:?\s*([-\d\.]+)", narrative_summary)
                                    if match:
                                        try:
                                            ai_score = float(match.group(1))
                                        except:
                                            pass
                                
                                # Display 4 columns if AI score exists, else 3
                                if ai_score is not None:
                                    b1, b2, b3, b4 = st.columns(4)
                                    b4.metric("AI Agent (LLM)", f"{ai_score:.2f}", help="Context-aware score by GPT-4o/DeepSeek")
                                else:
                                    b1, b2, b3 = st.columns(3)
                                    
                                b1.metric("CryptoBERT", f"{result['breakdown']['crypto_bert']:.2f}", help="Specialized in Crypto slang")
                                b2.metric("Twitter-roBERTa", f"{result['breakdown']['twitter_roberta']:.2f}", help="General social media sentiment")
                                b3.metric("VADER", f"{result['breakdown']['vader']:.2f}", help="Rule-based lexicon analysis")
                            
                            # Chart
                            st.markdown("#### Sentiment Distribution")
                            dist_df = pd.DataFrame({
                                'Sentiment': list(result['distribution'].keys()),
                                'Count': list(result['distribution'].values())
                            })
                            fig = px.pie(dist_df, values='Count', names='Sentiment', 
                                         color='Sentiment',
                                         color_discrete_map={'Positive':'#00cc96', 'Neutral':'#636efa', 'Negative':'#ef553b'})
                            st.plotly_chart(fig, use_container_width=True)
                            
                            # Top Tweets
                            st.markdown("### 📝 Recent Tweets")
                            for tweet in tweets[:5]:
                                with st.expander(f"@{tweet['screen_name']} - {tweet['created_at']}"):
                                    st.write(tweet['text'])
                                    st.caption(f"❤️ {tweet['likes']} | 🔄 {tweet['retweets']}")
                                    
                    except Exception as e:
                        st.error(f"❌ Error: {str(e)}")
                        import traceback
                        st.code(traceback.format_exc())
            
            if st.button("🚪 Logout (Delete Cookies)"):
                os.remove(cookies_path)
                st.success("Logged out.")
                st.rerun()

# ==============================================================================
# ==============================================================================
# Tab 10: Project & Compliance Risk
# ==============================================================================
with tab10:
    st.header("🛡️ Project & Compliance Risk Analysis")
    st.markdown("Evaluate project fundamentals, code activity, audit status, and regulatory risks.")
    
    # Input Section
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        cr_project = st.text_input(
            "项目名称 (Project Name)", 
            value="Uniswap",
            help="输入项目名称，如 Uniswap, Aave, Compound 等"
        )
    with col2:
        cr_github_owner = st.text_input(
            "GitHub Owner (可选)", 
            value="",
            help="GitHub 仓库所有者，如留空将自动查找"
        )
    with col3:
        cr_github_repo = st.text_input(
            "GitHub Repo (可选)", 
            value="",
            help="GitHub 仓库名称"
        )
    
    # Optional GitHub token
    with st.expander("⚙️ 高级设置 (Advanced Settings)"):
        cr_github_token = st.text_input(
            "GitHub Token (可选，用于提高 API 速率限制)",
            type="password",
            help="未认证时 GitHub API 速率限制为 60次/小时，认证后可达 5000次/小时"
        )
    
    if st.button("🔍 分析项目风险 (Analyze Risk)", type="primary"):
        with st.spinner("正在分析项目合规风险..."):
            try:
                from risk.compliance_risk import analyze_project_compliance
                
                results = analyze_project_compliance(
                    project_name=cr_project,
                    github_owner=cr_github_owner if cr_github_owner else None,
                    github_repo=cr_github_repo if cr_github_repo else None,
                    github_token=cr_github_token if cr_github_token else None
                )
                
                # Display Risk Score
                risk = results.get("risk_score", {})
                score = risk.get("score", 50)
                grade = risk.get("grade", "C")
                label = risk.get("label", "Unknown")
                
                # Color based on grade
                grade_colors = {"A": "🟢", "B": "🔵", "C": "🟡", "D": "🟠", "F": "🔴"}
                grade_icon = grade_colors.get(grade, "⚪")
                
                st.markdown("---")
                st.subheader("📊 综合风险评估 (Overall Risk Assessment)")
                
                # Show track info
                track_label = risk.get("track", "未分类")
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("项目风险评分", f"{score}/100", help="0=低风险, 100=高风险")
                with col2:
                    st.metric("项目风险等级", f"{grade_icon} {grade}")
                with col3:
                    st.metric("项目风险描述", label)
                with col4:
                    st.metric("项目赛道", track_label)
                
                # Risk Breakdown with new format
                breakdown = risk.get("breakdown", {})
                if breakdown:
                    st.markdown("##### 📈 风险评分计算")
                    
                    # Show calculation
                    calc = breakdown.get("calculation", {})
                    if calc:
                        st.info(f"🧮 **计算公式**: 基准分 ({calc.get('base_score', 0)}) + 风险增项 ({calc.get('total_increase', 0):+d}) + 风险减项 ({calc.get('total_decrease', 0)}) = **{calc.get('final_score', 0)}**")
                    
                    # Track info
                    track_info = breakdown.get("track", {})
                    if track_info:
                        st.caption(f"📌 {track_info.get('description', '')}")
                    
                    # Risk factors display
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.markdown("###### 🔴 风险增项")
                        increases = breakdown.get("risk_increases", [])
                        if increases:
                            for item in increases:
                                st.error(f"**{item['label']}** ({item['impact']}) - {item['category']}")
                        else:
                            st.success("✅ 无风险增项")
                    
                    with col2:
                        st.markdown("###### 🟢 风险减项")
                        decreases = breakdown.get("risk_decreases", [])
                        if decreases:
                            for item in decreases:
                                st.success(f"**{item['label']}** ({item['impact']}) - {item['category']}")
                
                st.markdown("---")
                
                # GitHub Activity Section
                github_data = results.get("github")
                if github_data and github_data.success:
                    st.subheader("📊 GitHub 代码活动 (Code Activity)")
                    st.markdown(f"**仓库**: [{github_data.owner}/{github_data.repo}](https://github.com/{github_data.owner}/{github_data.repo})")
                    
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("Commits (30天)", github_data.commits_30d)
                    with col2:
                        st.metric("Commits (90天)", github_data.commits_90d)
                    with col3:
                        st.metric("Contributors", github_data.contributors)
                    with col4:
                        st.metric("Stars ⭐", f"{github_data.stars:,}")
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Forks", f"{github_data.forks:,}")
                    with col2:
                        st.metric("Open Issues", github_data.open_issues)
                    with col3:
                        st.metric("Last Commit", github_data.last_commit_date)
                else:
                    st.warning("⚠️ GitHub 数据不可用。请手动输入 GitHub Owner 和 Repo。")
                
                st.markdown("---")
                
                # Audit Status Section
                audit_data = results.get("audit")
                if audit_data and audit_data.success:
                    st.subheader("🔐 审计状态 (Audit Status)")
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        audit_badge = "✅ 已审计" if audit_data.audited else "❌ 未审计"
                        st.metric("审计状态", audit_badge)
                    with col2:
                        tvl_formatted = f"${audit_data.tvl:,.0f}" if audit_data.tvl else "N/A"
                        st.metric("TVL (锁仓量)", tvl_formatted)
                    with col3:
                        st.metric("类别", audit_data.category)
                    
                    if audit_data.auditors:
                        st.markdown(f"**审计机构**: {', '.join(audit_data.auditors[:5])}")
                else:
                    st.warning(f"⚠️ 在 DefiLlama 中未找到 '{cr_project}' 的数据。")
                
                st.markdown("---")
                
                # News Section
                news_items = results.get("news", [])
                st.subheader(f"📰 相关新闻 (Recent News) - {len(news_items)} 条")
                
                # Check if any news is project-specific
                project_specific = any(n.is_project_specific for n in news_items)
                if news_items and not project_specific:
                    st.info(f"ℹ️ 未找到 {cr_project} 直接相关新闻，以下是加密货币领域的最新动态：")
                
                # Count by sentiment
                negative_news = [n for n in news_items if n.sentiment == "negative"]
                positive_news = [n for n in news_items if n.sentiment == "positive"]
                neutral_news = [n for n in news_items if n.sentiment == "neutral"]
                
                # Show sentiment summary
                col1, col2, col3 = st.columns(3)
                with col1:
                    if negative_news:
                        st.error(f"🔴 负面: {len(negative_news)} 条")
                    else:
                        st.success("🔴 负面: 0 条")
                with col2:
                    if positive_news:
                        st.success(f"🟢 正面: {len(positive_news)} 条")
                    else:
                        st.info("🟢 正面: 0 条")
                with col3:
                    st.info(f"⚪ 中性: {len(neutral_news)} 条")
                
                if news_items:
                    # Define sentiment icons
                    sentiment_icons = {"negative": "🔴", "positive": "🟢", "neutral": "⚪"}
                    sentiment_labels = {"negative": "负面", "positive": "正面", "neutral": "中性"}
                    
                    for news in news_items[:15]:
                        icon = sentiment_icons.get(news.sentiment, "📄")
                        label = sentiment_labels.get(news.sentiment, "")
                        specific = "📌" if news.is_project_specific else ""
                        
                        with st.expander(f"{icon}{specific} {news.title[:75]}...", expanded=False):
                            st.markdown(f"**情感**: {label} | **来源**: {news.source} | **日期**: {news.published}")
                            st.markdown(f"[🔗 阅读原文]({news.link})")
                            if news.matched_keywords:
                                kw_type = "⚠️ 负面关键词" if news.sentiment == "negative" else "✨ 正面关键词" if news.sentiment == "positive" else "🔑 关键词"
                                st.caption(f"{kw_type}: {', '.join(news.matched_keywords[:5])}")
                else:
                    st.success("✅ 未找到相关新闻报道。")
                
            except Exception as e:
                st.error(f"❌ 分析失败: {str(e)}")
                import traceback
                st.code(traceback.format_exc())
    


# ==============================================================================
# Tab 11: AI Alpha Lab (Machine Learning Strategy)
# ==============================================================================
with tab11:
    st.header("🧠 AI Alpha Lab")
    st.info("This module uses Machine Learning to learn patterns from multiple technical indicators and predict future price movements.")
    
    col_ai_1, col_ai_2 = st.columns([1, 3])
    
    with col_ai_1:
        st.subheader("⚙️ Configuration")
        ai_symbol = st.selectbox("Symbol", ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"], key="ai_symbol")
        ai_timeframe = st.selectbox("Timeframe", ["1h", "4h", "1d"], key="ai_timeframe")
        ai_limit = st.slider("Training Data (Candles)", 1000, 10000, 3000, step=1000, key="ai_limit")
        ai_horizon = st.slider("Prediction Horizon (Candles)", 1, 12, 4, key="ai_horizon")
        
        st.subheader("🤖 Model Selection")
        # Check model availability
        try:
            from ai_strategy import XGBOOST_AVAILABLE, LIGHTGBM_AVAILABLE
        except:
            XGBOOST_AVAILABLE = False
            LIGHTGBM_AVAILABLE = False
        
        # Build available models list
        available_models = ["Random Forest", "Ensemble (RF+LR+SVC)"]
        if LIGHTGBM_AVAILABLE:
            available_models.append("LightGBM")
        if XGBOOST_AVAILABLE:
            available_models.append("XGBoost")
        
        ai_model_type = st.selectbox("Algorithm (Select Model)", available_models, key="ai_model_type")
        # Debug: Show what models are available
        st.caption(f"Debug: Available models: {available_models}")
        
        if not XGBOOST_AVAILABLE and not LIGHTGBM_AVAILABLE:
            st.caption("⚠️ Gradient Boosting libraries not available.")
        
        # Hyperparameter Tuning
        st.subheader("🎛️ Hyperparameters")
        rf_n_estimators = st.slider("Number of Trees", 50, 500, 100, step=50, key="rf_n_estimators", help="More trees = better accuracy but slower training")
        rf_max_depth = st.slider("Max Depth", 3, 20, 10, key="rf_max_depth", help="Deeper trees can overfit; shallower trees generalize better")
        
        st.subheader("🔄 Validation Mode")
        use_walk_forward = st.checkbox("Use Walk-Forward Validation", value=False, help="Rolling window training for more robust testing")
        if use_walk_forward:
            n_splits = st.slider("Number of Folds", 3, 10, 5, key="wf_splits")
        else:
            n_splits = 5  # default
        
        train_button = st.button("🤖 Train AI Model", type="primary")
        
    with col_ai_2:
        if train_button:
            with st.spinner(f"Training AI Model on {ai_symbol}..."):
                try:
                    from backtest_engine import BacktestEngine
                    from ai_strategy import AIStrategy
                    import plotly.express as px
                    import plotly.graph_objects as go
                    
                    # 1. Fetch Data
                    engine = BacktestEngine()
                    df = engine.fetch_data(ai_symbol, ai_timeframe, limit=ai_limit)
                    
                    if df.empty:
                        st.error("No data fetched.")
                    else:
                        # 2. Prepare Data
                        # Convert model selection to internal name
                        model_key_map = {
                            'Random Forest': 'random_forest', 
                            'Ensemble (RF+LR+SVC)': 'ensemble',
                            'XGBoost': 'xgboost', 
                            'LightGBM': 'lightgbm'
                        }
                        model_key = model_key_map.get(ai_model_type, 'random_forest')
                        ai = AIStrategy(model_type=model_key, n_estimators=rf_n_estimators, max_depth=rf_max_depth)
                        df = ai.prepare_features(df)
                        df = ai.prepare_labels(df, horizon=ai_horizon)
                        
                        # 3. Train Model (Simple or Walk-Forward)
                        if use_walk_forward:
                            metrics, feature_imp, test_df, y_prob = ai.walk_forward_train(df, n_splits=n_splits)
                            st.success(f"✅ {ai_model_type} Walk-Forward Trained ({metrics['windows_used']} folds)")
                        else:
                            metrics, feature_imp, test_df, y_prob = ai.train_model(df)
                            st.success(f"✅ {ai_model_type} Model Trained Successfully!")
                        
                        m1, m2, m3 = st.columns(3)
                        m1.metric("Accuracy", f"{metrics['Accuracy']:.2%}")
                        m2.metric("Precision", f"{metrics['Precision']:.2%}")
                        m3.metric("Recall", f"{metrics['Recall']:.2%}")
                        
                        # 4.5 Confusion Matrix
                        st.subheader("🎯 Confusion Matrix")
                        from sklearn.metrics import confusion_matrix
                        import plotly.figure_factory as ff
                        
                        # Get predictions from probabilities
                        y_pred = (y_prob >= 0.5).astype(int)
                        y_actual = test_df['Target'].values
                        
                        cm = confusion_matrix(y_actual, y_pred)
                        # Labels: 0 = Price Down, 1 = Price Up
                        labels = ['Down (0)', 'Up (1)']
                        
                        # Create annotated heatmap
                        fig_cm = ff.create_annotated_heatmap(
                            z=cm,
                            x=labels,
                            y=labels,
                            colorscale='Blues',
                            showscale=True
                        )
                        fig_cm.update_layout(
                            title="Predicted vs Actual",
                            xaxis_title="Predicted",
                            yaxis_title="Actual"
                        )
                        fig_cm['layout']['yaxis']['autorange'] = "reversed"  # Flip y-axis
                        
                        col_cm1, col_cm2 = st.columns([2, 1])
                        with col_cm1:
                            st.plotly_chart(fig_cm, use_container_width=True)
                        with col_cm2:
                            # Explain the confusion matrix
                            tn, fp, fn, tp = cm.ravel()
                            st.markdown(f"""
                            **解读:**
                            - ✅ True Positive (TP): **{tp}** - 正确预测涨
                            - ✅ True Negative (TN): **{tn}** - 正确预测跌
                            - ❌ False Positive (FP): **{fp}** - 误报涨
                            - ❌ False Negative (FN): **{fn}** - 错过涨
                            """)
                        
                        # 5. Feature Importance
                        st.subheader("📊 Feature Importance")
                        fig_imp = px.bar(feature_imp, x='Importance', y='Feature', orientation='h', title="Top Predictors")
                        st.plotly_chart(fig_imp, use_container_width=True)
                        
                        # 6. Backtest Simulation
                        train_size = int(ai_limit * 0.8)
                        test_size = ai_limit - train_size
                        st.subheader(f"💰 AI Strategy Backtest (Test Set: {test_size} candles)")
                        st.caption(f"📊 Data Split: Training = {train_size} candles | Test = {test_size} candles (80/20 split)")
                        test_df, bt_metrics = ai.run_backtest(test_df, y_prob)
                        
                        # Display Enhanced Metrics
                        st.markdown("##### 📈 Performance Metrics")
                        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
                        col_m1.metric("Total Return", f"{bt_metrics['total_return']}%", delta_color="normal")
                        col_m2.metric("Max Drawdown", f"{bt_metrics['max_drawdown']}%", delta_color="inverse")
                        col_m3.metric("Sharpe Ratio", f"{bt_metrics['sharpe_ratio']}", help="Risk-adjusted return (annualized)")
                        col_m4.metric("Win Rate", f"{bt_metrics['win_rate']}%")
                        
                        # Trade breakdown
                        st.markdown("##### 📊 Trade Breakdown")
                        col_t1, col_t2, col_t3 = st.columns(3)
                        col_t1.metric("Total Trades", bt_metrics['total_trades'])
                        col_t2.metric(f"Long Trades ({bt_metrics['long_win_rate']}% Win)", bt_metrics['long_trades'])
                        col_t3.metric(f"Short Trades ({bt_metrics['short_win_rate']}% Win)", bt_metrics['short_trades'])
                        
                        # Equity Curve
                        fig_eq = go.Figure()
                        fig_eq.add_trace(go.Scatter(x=test_df['timestamp'], y=test_df['Equity'], mode='lines', name='AI Strategy', line=dict(color='cyan')))
                        # Benchmark (Buy & Hold)
                        bh_ret = (test_df['close'] / test_df['close'].iloc[0]) * 1000
                        bh_return = round((bh_ret.iloc[-1] - 1000) / 1000 * 100, 2)
                        fig_eq.add_trace(go.Scatter(x=test_df['timestamp'], y=bh_ret, mode='lines', name=f'Buy & Hold ({bh_return}%)', line=dict(color='gray', dash='dash')))
                        
                        fig_eq.update_layout(title=f"Equity Curve: AI {bt_metrics['total_return']}% vs B&H {bh_return}%", xaxis_title="Time", yaxis_title="Equity ($)")
                        st.plotly_chart(fig_eq, use_container_width=True)
                        
                        # Signals on Chart
                        st.subheader("🚦 Trade Signals (Long & Short)")
                        fig_sig = go.Figure()
                        fig_sig.add_trace(go.Candlestick(x=test_df['timestamp'], open=test_df['open'], high=test_df['high'], low=test_df['low'], close=test_df['close'], name='Price'))
                        
                        # Buy Signals (Green Up Triangle)
                        buy_sigs = test_df[test_df['Signal'] == 1]
                        fig_sig.add_trace(go.Scatter(x=buy_sigs['timestamp'], y=buy_sigs['low']*0.99, mode='markers', marker=dict(symbol='triangle-up', color='lime', size=12), name='AI Long Signal'))
                        
                        # Sell Signals (Red Down Triangle)
                        sell_sigs = test_df[test_df['Signal'] == -1]
                        fig_sig.add_trace(go.Scatter(x=sell_sigs['timestamp'], y=sell_sigs['high']*1.01, mode='markers', marker=dict(symbol='triangle-down', color='red', size=12), name='AI Short Signal'))
                        
                        fig_sig.update_layout(title="Price & AI Signals (Long/Short)", xaxis_title="Time", yaxis_title="Price")
                        st.plotly_chart(fig_sig, use_container_width=True)
                        
                        # Display signal counts
                        st.caption(f"📊 Long Signals: {len(buy_sigs)} | Short Signals: {len(sell_sigs)}")
                        
                except Exception as e:
                    st.error(f"An error occurred: {e}")
                    st.exception(e)
        else:
            st.write("👈 Configure and click **Train AI Model** on the left to begin.")
