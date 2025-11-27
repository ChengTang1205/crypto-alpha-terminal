import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go # [新增] 用于画双轴图
from plotly.subplots import make_subplots # [新增]
import yfinance as yf # [新增]
import time
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
# 把这行改成 5 个 Tab
tab1, tab2, tab3, tab4, tab5 = st.tabs(["💵 宏观资金", "🌉 跨链热点", "🏦 CEX 储备", "🚨 风险监控", "🎭 情绪与合约"])

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
            option = {
                "series": [
                    {
                        "type": "gauge",
                        "startAngle": 180,
                        "endAngle": 0,
                        "min": 0,
                        "max": 100,
                        "splitNumber": 10,
                        "radius": "110%",
                        "center": ["50%", "75%"],
                        "axisLine": {
                            "lineStyle": {
                                "width": 15,
                                "color": [[0.25, "#FF4B4B"], [0.5, "#FFAA00"], [0.75, "#FCD535"], [1, "#00FFAA"]],
                                "shadowBlur": 10, "shadowColor": "rgba(0, 0, 0, 0.5)"
                            }
                        },
                        "pointer": {
                            "icon": "path://M12.8,0.7l12,40.1H0.7L12.8,0.7z",
                            "length": "60%", "width": 6, "offsetCenter": [0, "-10%"],
                            "itemStyle": {"color": "auto", "shadowBlur": 5, "shadowColor": "#fff"}
                        },
                        "axisTick": {"length": 5, "lineStyle": {"color": "auto", "width": 1}},
                        "splitLine": {"length": 10, "lineStyle": {"color": "auto", "width": 2}},
                        "axisLabel": {"color": "#999", "fontSize": 10, "distance": -45, "formatter": "{value}"},
                        "detail": {
                            "fontSize": 40, "offsetCenter": [0, "-10%"], "valueAnimation": True,
                            "formatter": "{value}", "color": "white", "fontWeight": "bold"
                        },
                        "title": {"offsetCenter": [0, "25%"], "fontSize": 18, "color": "#ccc"},
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