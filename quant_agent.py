import os
from typing import TypedDict, Annotated
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END

# 定义状态字典：用于在图的节点之间传递数据
class AgentState(TypedDict):
    market_data: str       # 市场数据 (DataFrame string)
    fng_index: str         # 贪婪指数
    analysis_result: str   # AI 生成的最终分析

class CryptoQuantAgent:
    def __init__(self, api_key):
        # 初始化 LLM (推荐使用 GPT-4o 或 GPT-4-turbo 以获得更好的数学逻辑)
        self.llm = ChatOpenAI(
            api_key=api_key, 
            model="gpt-4o", 
            temperature=0.2 # 低温度，保证分析严谨
        )
        self.workflow = self._build_graph()

    def _build_graph(self):
        # 1. 定义 Prompt
        system_prompt = """
        你是一位拥有 20 年经验的华尔街加密货币量化交易员。你的任务是根据提供的实时衍生品数据撰写一份简短、犀利的投资备忘录。

        核心分析逻辑：
        1. **资金费率 (Funding Rate)**: 
           - 负费率 (Negative) + 价格不跌 = 主力做空被套，可能轧空 (Bullish)。
           - 极高正费率 (>0.03%) = 市场极度拥挤，谨防回调。
           - Binance 与 Bybit 费率背离 = 套利机会或主力定向爆破。
        
        2. **多空比 (Long/Short Ratio)**:
           - L/S > 2.5 (Binance) 或 > 3.0 (Bybit) = 散户极度做多，车太重，主力难以拉盘 (Bearish)。
           - L/S < 0.8 = 散户极度恐慌做空，可能见底 (Bullish)。
        
        3. **综合判断**:
           - 如果 L/S 极高 且 费率为负 = 主力在现货出货并在合约对冲，散户在死扛，极度危险。
        
        请输出 Markdown 格式，包含以下部分：
        ### 🚨 核心信号诊断
        (用一句话总结当前最危险或机会最大的信号)
        
        ### 📊 数据深度解读
        (对比 Binance 和 Bybit 的数据，指出异常点)
        
        ### ♟️ 机构操盘手策略
        (给出具体的行动建议：做多/做空/观望/对冲，并说明止损思路)
        """

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("user", "当前贪婪指数: {fng_index}\n\n当前合约数据概览:\n{market_data}")
        ])

        # 2. 定义节点函数
        def analyze_node(state: AgentState):
            # 调用 LLM
            chain = prompt | self.llm
            response = chain.invoke({
                "fng_index": state["fng_index"],
                "market_data": state["market_data"]
            })
            return {"analysis_result": response.content}

        # 3. 构建 LangGraph 图
        workflow = StateGraph(AgentState)
        workflow.add_node("analyst", analyze_node)
        workflow.set_entry_point("analyst")
        workflow.add_edge("analyst", END)
        
        return workflow.compile()

    def run_analysis(self, df, fng_data):
        """运行分析流程"""
        # 数据预处理：将 DataFrame 转为易读的 Markdown 表格
        if df.empty:
            return "数据为空，无法分析。"
            
        # 精简数据，只保留重要列，节省 Token
        cols = ['Symbol', 'Price', 'Binance Funding', 'Binance LS', 'Bybit Funding', 'Bybit LS']
        # 确保列存在
        valid_cols = [c for c in cols if c in df.columns]
        data_str = df[valid_cols].to_markdown(index=False)
        
        fng_str = f"{fng_data.get('value', 'N/A')} ({fng_data.get('status', 'N/A')})" if fng_data else "Unknown"

        # 触发 LangGraph
        result = self.workflow.invoke({
            "market_data": data_str,
            "fng_index": fng_str
        })
        
        return result["analysis_result"]