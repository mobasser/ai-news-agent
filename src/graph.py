import truststore

truststore.inject_into_ssl()

from datetime import datetime
from langchain_openai import ChatOpenAI
from langchain_tavily import TavilySearch
from langgraph.graph import StateGraph, END
from .state import AgentState, NewsScript

SPEAKER_NAMES = {"Host A": "Agent Anna", "Host B": "Agent Sam"}

AD_MARKERS = [
    "subscribe", "advertisement", "sponsored", "promo",
    "click here", "buy now", "limited offer", "special deal",
]


def search_news_node(state: AgentState) -> AgentState:
    """Phase 1: Dynamic Targeted Data Gathering"""
    current_date = datetime.now().strftime("%Y-%m-%d")
    search_tool = TavilySearch(max_results=5, search_depth="basic", topic="news", time_range="day")

    all_results = []
    for interest in state["user_interests"]:
        response = search_tool.invoke({"query": f"{interest} news {current_date}"})
        if isinstance(response, dict) and "results" in response:
            all_results.extend(r["content"] for r in response["results"] if r.get("content"))

    if not all_results:
        raise RuntimeError("Tavily search returned no results for the given interests")
    return {"search_results": all_results}


def synthesize_context_node(state: AgentState) -> AgentState:
    """Phase 2: Information Filtering & Fact Synthesis"""
    seen_texts = set()
    filtered_facts = []

    for text in state["search_results"]:
        if not text or not isinstance(text, str):
            continue

        text_lower = text.lower().strip()

        if len(text_lower) < 50:
            continue

        if any(ad_word in text_lower for ad_word in AD_MARKERS):
            continue

        if text_lower not in seen_texts:
            seen_texts.add(text_lower)
            filtered_facts.append(text)

    if not filtered_facts:
        raise RuntimeError("No usable news facts remained after filtering")

    context_block = "# Current News Context\n\n"
    for i, fact in enumerate(filtered_facts, 1):
        context_block += f"## Fact {i}\n{fact}\n\n"

    return {"synthesized_context": context_block}


def generate_script_node(state: AgentState) -> AgentState:
    """Phase 3: Multi-Voice Creative Script Writing"""
    context = state["synthesized_context"]
    language = state["language"]

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)
    structured_llm = llm.with_structured_output(NewsScript)

    prompt = f"""You are creating an engaging two-person podcast/briefing conversation about current news.

Host A (named Agent Anna) is informative, factual, and provides clear explanations.
Host B (named Agent Sam) is dynamic, conversational, and adds engaging commentary and reactions.
Refer to the hosts only by their names, Agent Anna and Agent Sam, never as "Host A" or "Host B" in the dialogue text.

Based on the following news context, create a compelling news briefing script:

{context}

Requirements:
- Write the title and every dialogue line in {language}
- Create a catchy title for today's briefing
- Write a natural back-and-forth dialogue between Host A and Host B
- Keep the conversation engaging but factual
- Each dialogue line should be substantial (not just "yes" or "okay")
- Ensure smooth transitions between topics
- End with a brief summary or closing thought
"""

    script: NewsScript = structured_llm.invoke(prompt)
    for line in script.script:
        line.speaker = SPEAKER_NAMES.get(line.speaker, line.speaker)
    return {"final_script": script}


def create_graph():
    """Create and compile the LangGraph StateGraph"""
    workflow = StateGraph(AgentState)

    workflow.add_node("search_news", search_news_node)
    workflow.add_node("synthesize_context", synthesize_context_node)
    workflow.add_node("generate_script", generate_script_node)

    workflow.set_entry_point("search_news")
    workflow.add_edge("search_news", "synthesize_context")
    workflow.add_edge("synthesize_context", "generate_script")
    workflow.add_edge("generate_script", END)

    return workflow.compile()


app = create_graph()
