from langgraph.graph import START, END, StateGraph
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.prebuilt import ToolNode
from functools import partial

from .graph_state import State
from .nodes import *
from .edges import *

def create_agent_graph(llm, tools_list, appointment_service=None):
    llm_with_tools = llm.bind_tools(tools_list)
    tool_node = ToolNode(tools_list)

    checkpointer = InMemorySaver()

    print("Compiling agent graph...")
    agent_builder = StateGraph(AgentState)
    agent_builder.add_node("orchestrator", partial(orchestrator, llm_with_tools=llm_with_tools))
    agent_builder.add_node("tools", tool_node)
    agent_builder.add_node("compress_context", partial(compress_context, llm=llm))
    agent_builder.add_node("fallback_response", partial(fallback_response, llm=llm))
    agent_builder.add_node(should_compress_context)
    agent_builder.add_node(collect_answer)

    agent_builder.add_edge(START, "orchestrator")
    agent_builder.add_conditional_edges("orchestrator", route_after_orchestrator_call, {"tools": "tools", "fallback_response": "fallback_response", "collect_answer": "collect_answer"})
    agent_builder.add_edge("tools", "should_compress_context")
    agent_builder.add_edge("compress_context", "orchestrator")
    agent_builder.add_edge("fallback_response", "collect_answer")
    agent_builder.add_edge("collect_answer", END)

    agent_subgraph = agent_builder.compile()

    graph_builder = StateGraph(State)
    graph_builder.add_node("summarize_history", partial(summarize_history, llm=llm))
    graph_builder.add_node("analyze_turn", analyze_turn)
    graph_builder.add_node("intent_router", partial(intent_router, llm=llm))
    graph_builder.add_node("rewrite_query", partial(rewrite_query, llm=llm))
    graph_builder.add_node("recommend_department", partial(recommend_department, llm=llm))
    graph_builder.add_node("handle_appointment", partial(handle_appointment, llm=llm, appointment_service=appointment_service))
    graph_builder.add_node("handle_cancel_appointment", partial(handle_cancel_appointment, llm=llm, appointment_service=appointment_service))
    graph_builder.add_node(request_clarification)
    graph_builder.add_node("prepare_secondary_turn", prepare_secondary_turn)
    graph_builder.add_node("agent", agent_subgraph)
    graph_builder.add_node("aggregate_answers", partial(aggregate_answers, llm=llm))

    graph_builder.add_edge(START, "summarize_history")
    graph_builder.add_edge("summarize_history", "analyze_turn")
    graph_builder.add_edge("analyze_turn", "intent_router")
    graph_builder.add_conditional_edges("intent_router", route_after_intent, {
        "rewrite_query": "rewrite_query",
        "recommend_department": "recommend_department",
        "handle_appointment": "handle_appointment",
        "handle_cancel_appointment": "handle_cancel_appointment",
        "request_clarification": "request_clarification",
        "__end__": END,
    })
    graph_builder.add_conditional_edges("rewrite_query", route_after_rewrite)
    graph_builder.add_conditional_edges("request_clarification", route_after_clarification)
    graph_builder.add_edge(["agent"], "aggregate_answers")
    graph_builder.add_conditional_edges("recommend_department", route_after_action, {"prepare_secondary_turn": "prepare_secondary_turn", "__end__": END})
    graph_builder.add_conditional_edges("handle_appointment", route_after_action, {"prepare_secondary_turn": "prepare_secondary_turn", "__end__": END})
    graph_builder.add_conditional_edges("handle_cancel_appointment", route_after_action, {"prepare_secondary_turn": "prepare_secondary_turn", "__end__": END})
    graph_builder.add_conditional_edges("prepare_secondary_turn", route_after_prepare_secondary_turn, {
        "rewrite_query": "rewrite_query",
        "handle_appointment": "handle_appointment",
        "handle_cancel_appointment": "handle_cancel_appointment",
        "recommend_department": "recommend_department",
    })
    graph_builder.add_edge("aggregate_answers", END)

    agent_graph = graph_builder.compile(checkpointer=checkpointer, interrupt_before=["request_clarification"])

    print("Agent graph compiled successfully.")
    return agent_graph
