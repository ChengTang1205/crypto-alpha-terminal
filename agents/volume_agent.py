from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import json

def create_volume_agent(llm):
    """
    Create a volume analysis agent node.
    """
    def volume_agent_node(state) -> dict:
        messages = state["messages"]
        kline_data = state["kline_data"]
        time_frame = state["time_frame"]
        stock_name = state["stock_name"]
        
        # Prepare data for prompt (convert to JSON string for clarity)
        # We use the dict of lists format directly
        data_str = json.dumps(kline_data, indent=2)
        
        system_prompt = f"""You are a high-frequency trading (HFT) volume analyst for {stock_name}.
        Your task is to analyze the trading volume dynamics based on the provided OHLCV data for the {time_frame} timeframe.
        
        Focus on:
        1. **Volume Trend**: Is volume increasing or decreasing? What does this indicate about the current trend strength?
        2. **Volume Spikes**: Identify significant volume spikes. Do they coincide with price reversals, breakouts, or climaxes?
        3. **Price-Volume Divergence**: Are there signs of divergence (e.g., price rising on falling volume)?
        4. **Accumulation/Distribution**: Are there signs of institutional accumulation (buying on dips) or distribution (selling on rallies)?
        
        Provide a concise, professional report summarizing your findings.
        """
        
        user_message = """Here is the market data:
        {market_data}
        
        Please provide your Volume Analysis Report.
        """
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("user", user_message),
        ])
        
        chain = prompt | llm
        response = chain.invoke({"market_data": data_str})
        
        return {
            "messages": messages + [response],
            "volume_report": response.content
        }
        
    return volume_agent_node
