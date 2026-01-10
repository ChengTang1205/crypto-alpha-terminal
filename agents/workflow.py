from typing import Dict, Any
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph, START
from langgraph.prebuilt import ToolNode
from .tools import TechnicalTools

import os
from langchain.chat_models import init_chat_model
from langchain_core.messages import AnyMessage, BaseMessage # [FIX] Added BaseMessage
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt.chat_agent_executor import AgentState
from langgraph.prebuilt import create_react_agent
from langgraph.graph import END, StateGraph, START

from typing import TypedDict, List
import random
import pandas as pd
from .tools import *
# from langchain_community.chat_models import ChatOpenAI
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode
from .state import IndicatorAgentState

from .indicator_agent import *
from .decision_agent import *
from .pattern_agent import *
from .trend_agent import *
from .volume_agent import *
from .decision_agent import *


class SetGraph:
    def __init__(
        self,
        agent_llm: ChatOpenAI,
        graph_llm: ChatOpenAI,
        toolkit: TechnicalTools,
        tool_nodes: Dict[str, ToolNode],
    ):
        self.agent_llm = agent_llm
        self.graph_llm = graph_llm
        self.toolkit = toolkit
        self.tool_nodes = tool_nodes
    
    def set_graph(self):
         # Create analyst nodes
        agent_nodes = {}
        tool_nodes = {}
        all_agents = ['indicator', 'pattern', 'trend']
        
        # create nodes for indicator agent
        agent_nodes['indicator'] = create_indicator_agent(self.graph_llm, self.toolkit)
        # create nodes for pattern agent
        # agent_nodes['pattern'] = create_pattern_agent(self.agent_llm, self.graph_llm, self.toolkit)
        # tool_nodes['pattern'] = self.tool_nodes['pattern']

        # Create agent nodes
        agent_nodes = {
            "indicator": create_indicator_agent(self.graph_llm, self.toolkit),
            "pattern": create_pattern_agent(self.agent_llm, self.graph_llm, self.toolkit),
            "trend": create_trend_agent(self.agent_llm, self.graph_llm, self.toolkit),
            "volume": create_volume_agent(self.agent_llm) # [NEW]
        }
        
        decision_agent_node = create_final_trade_decider(self.graph_llm)
        
        graph = StateGraph(IndicatorAgentState)
        
        # add agent nodes and associated tool nodes to graph
        for agent_type, cur_node in agent_nodes.items():
            graph.add_node(f"{agent_type.capitalize()} Agent", cur_node)
            # Volume agent doesn't have tools currently, but we can check if it needs them
            if agent_type != "volume": 
                graph.add_node(f"{agent_type}_tools", self.tool_nodes[agent_type])
        
        graph.add_node("Decision Maker", decision_agent_node)
        
        graph.add_edge(START, "Indicator Agent")
        graph.add_edge(START, "Pattern Agent")
        graph.add_edge(START, "Trend Agent")
        graph.add_edge(START, "Volume Agent") # [NEW]
        
        # Define conditional edges for tool use
        # This function will be called to decide which node to next after an agent
        def tools_condition(state: IndicatorAgentState):
            messages = state.get("messages", [])
            if messages and isinstance(messages[-1], BaseMessage) and messages[-1].tool_calls:
                return "tools"
            return END # Or "Decision Maker" if the agent is done and doesn't need tools

        graph.add_conditional_edges("Indicator Agent", tools_condition, {"tools": "indicator_tools", END: "Decision Maker"})
        graph.add_edge("indicator_tools", "Indicator Agent")
        
        graph.add_conditional_edges("Pattern Agent", tools_condition, {"tools": "pattern_tools", END: "Decision Maker"})
        graph.add_edge("pattern_tools", "Pattern Agent")
        
        graph.add_conditional_edges("Trend Agent", tools_condition, {"tools": "trend_tools", END: "Decision Maker"})
        graph.add_edge("trend_tools", "Trend Agent")
        
        # Volume Agent direct edge (no tools yet)
        graph.add_edge("Volume Agent", "Decision Maker") # [NEW]
        
        graph.add_edge("Decision Maker", END)

        
        return graph.compile()
