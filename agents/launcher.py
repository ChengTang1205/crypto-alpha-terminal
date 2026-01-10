import os
import json
import yfinance as yf
import pandas as pd
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import ToolNode
from .workflow import SetGraph
from .tools import TechnicalTools

def fetch_market_data(ticker, period="1mo", interval="1h"):
    """Fetch OHLCV data from yfinance."""
    try:
        df = yf.download(ticker, period=period, interval=interval, progress=False)
        if df.empty:
            return None
        
        # Reset index to get Datetime column
        df = df.reset_index()
        
        # Flatten MultiIndex columns if present (yfinance update)
        if isinstance(df.columns, pd.MultiIndex):
            # Keep only the top level name if it matches our expected columns
            new_cols = []
            for col in df.columns:
                if col[0] in ["Date", "Open", "High", "Low", "Close", "Volume"]:
                    new_cols.append(col[0])
                else:
                    new_cols.append(col[0]) # Fallback
            df.columns = new_cols
            
        # Rename columns to match expected format
        df = df.rename(columns={
            "Date": "Datetime", 
            "Open": "Open", 
            "High": "High", 
            "Low": "Low", 
            "Close": "Close", 
            "Volume": "Volume"
        })
        
        # Ensure Datetime is string for JSON serialization
        df['Datetime'] = df['Datetime'].astype(str)
        
        # Return as dict of lists (not list of dicts) for tool compatibility
        return df.to_dict(orient="list")
    except Exception as e:
        print(f"Data fetch error: {e}")
        return None

def run_multi_agent_analysis(api_key, ticker, timeframe="1h"):
    """
    Run the Multi-Agent Quant System.
    """
    if not api_key:
        return {"error": "API Key is missing."}
        
    # 1. Initialize LLMs
    # Agent LLM (GPT-4o) for reasoning
    agent_llm = ChatOpenAI(api_key=api_key, model="gpt-4o", temperature=0)
    # Graph LLM (GPT-4o) for vision/graph decisions
    graph_llm = ChatOpenAI(api_key=api_key, model="gpt-4o", temperature=0)
    
    # 2. Initialize Toolkit
    toolkit = TechnicalTools()
    
    # 3. Create ToolNodes
    # Indicator Tools
    indicator_tools = [
        toolkit.compute_macd,
        toolkit.compute_rsi,
        toolkit.compute_roc,
        toolkit.compute_stoch,
        toolkit.compute_willr,
        toolkit.compute_adx,
    ]
    
    # Pattern Tools
    pattern_tools = [toolkit.generate_kline_image]
    
    # Trend Tools
    trend_tools = [toolkit.generate_trend_image]
    
    tool_nodes = {
        "indicator": ToolNode(indicator_tools),
        "pattern": ToolNode(pattern_tools),
        "trend": ToolNode(trend_tools)
    }
    
    # 4. Setup Graph
    graph_setter = SetGraph(agent_llm, graph_llm, toolkit, tool_nodes)
    graph = graph_setter.set_graph()
    
    # 5. Fetch Data
    # Map timeframe to yfinance params
    yf_period = "1mo"
    yf_interval = "1h"
    if timeframe == "15m":
        yf_period = "5d"
        yf_interval = "15m"
    elif timeframe == "4h":
        yf_period = "3mo"
        yf_interval = "1h" 
    elif timeframe == "1d":
        yf_period = "1y"
        yf_interval = "1d"
        
    market_data = fetch_market_data(ticker, period=yf_period, interval=yf_interval)
    if not market_data:
        return {"error": f"Failed to fetch data for {ticker}"}
    
    # 🔥 CRITICAL: Match original QuantAgent behavior - use only 45-46 candles
    # This prevents token limit errors while providing sufficient context
    # market_data is now a dict of lists, so we need to slice each list
    data_length = len(market_data.get('Datetime', []))
    if data_length > 49:
        # Take last 46 candles
        market_data = {key: value[-49:][:-3] for key, value in market_data.items()}
    elif data_length > 45:
        # Take last 45 candles
        market_data = {key: value[-45:] for key, value in market_data.items()}
    # else: keep all data if less than 45 candles
    
    # 🔥 Pre-generate images to avoid regenerating in each agent
    # This significantly reduces token usage
    try:
        from . import static_util
        pattern_img = static_util.generate_kline_image(market_data)
        trend_img = static_util.generate_trend_image(market_data)
        
        # 6. Run Graph with pre-generated images
        initial_state = {
            "kline_data": market_data,
            "time_frame": timeframe,
            "stock_name": ticker,
            "messages": [],
            "pattern_image": pattern_img.get("pattern_image", ""),
            "trend_image": trend_img.get("trend_image", "")
        }
    except ImportError:
        # Fallback if static_util doesn't exist
        initial_state = {
            "kline_data": market_data,
            "time_frame": timeframe,
            "stock_name": ticker,
            "messages": []
        }
    
    try:
        result = graph.invoke(initial_state)
        return result
    except Exception as e:
        return {"error": str(e)}
