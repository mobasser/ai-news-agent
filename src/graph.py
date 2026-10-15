import truststore

truststore.inject_into_ssl()

from datetime import datetime
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.config import get_stream_writer
from langgraph.graph import StateGraph, END
from .state import AgentState, NewsScript, Relevance, ResearchPlan
from .tools import finish_research, search_news

SPEAKER_NAMES = {"Host A": "Anna", "Host B": "Sam"}

AD_MARKERS = [
    "subscribe", "advertisement", "sponsored", "promo",
    "click here", "buy now", "limited offer", "special deal",
]

TOOLS = [search_news, finish_research]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}
MAX_SEARCHES = 6
MAX_STEPS = 10
MIN_SOURCES_PER_TOPIC = 2
RECURSION_LIMIT = 50


def make_llm(temperature: float = 0.2):
    return ChatOpenAI(model="gpt-4o-mini", temperature=temperature)


def plan_node(state: AgentState) -> AgentState:
    today = datetime.now().strftime("%Y-%m-%d")
    prompt = (
        f"Today is {today}. Write 3 to 5 distinct, specific news search queries that together cover "
        f"these topics: {', '.join(state['user_interests'])}."
    )
    plan: ResearchPlan = make_llm().with_structured_output(ResearchPlan).invoke(prompt)
    return {
        "plan": plan.queries,
        "messages": [HumanMessage(content="Begin the research.")],
        "run_log": [{"step": 0, "action": "plan", "observation": " | ".join(plan.queries)}],
        "steps": 0,
        "searches_used": 0,
        "stop_reason": None,
    }


def agent_node(state: AgentState) -> AgentState:
    get_stream_writer()({"type": "thinking"})
    counts = coverage(state.get("sources", []), state["user_interests"])
    coverage_text = "; ".join(
        f"{t}: {n}/{MIN_SOURCES_PER_TOPIC} relevant sources" + ("" if n >= MIN_SOURCES_PER_TOPIC else " (short)")
        for t, n in counts.items()
    )
    all_covered = all(n >= MIN_SOURCES_PER_TOPIC for n in counts.values())
    system = SystemMessage(content=(
        "You are a news research agent. Find current, reliable news for these topics: "
        f"{', '.join(state['user_interests'])}.\n"
        f"Planned queries: {'; '.join(state['plan'])}.\n"
        f"Searches used: {state['searches_used']} of {MAX_SEARCHES}.\n"
        f"Coverage: {coverage_text}.\n"
        + ("All topics are covered: call finish_research now.\n" if all_covered else "Search for the short topics.\n") +
        "Rules:\n"
        "- Use search_news with specific queries. Do not repeat a query you already ran.\n"
        "- If a search returns no relevant results, rewrite the query and try again.\n"
        f"- finish_research is refused until every topic has at least {MIN_SOURCES_PER_TOPIC} relevant sources. "
        "If it is refused, search for the topics listed as short.\n"
        "- When coverage is sufficient, or more searching cannot help, call finish_research with a reason."
    ))
    if all_covered:
        bound = make_llm().bind_tools([finish_research], tool_choice="finish_research", parallel_tool_calls=False)
    else:
        bound = make_llm().bind_tools(TOOLS, parallel_tool_calls=False)
    response = bound.invoke([system] + state["messages"])
    offered = "finish_research only" if all_covered else "search_news or finish_research"
    update = {
        "messages": [response],
        "steps": state["steps"] + 1,
        "run_log": [{"step": state["steps"] + 1, "action": "decide", "observation": f"Coverage: {coverage_text}. Offered: {offered}."}],
    }
    if not response.tool_calls:
        update["stop_reason"] = "model stopped without calling finish_research"
    return update


def judge_results(topics: list[str], found: list[dict]) -> list[str]:
    if not found:
        return []
    listing = "\n".join(f"{i}. {r.get('title', '')} - {r['content'][:300]}" for i, r in enumerate(found))
    prompt = (
        f"Topics: {', '.join(topics)}.\n"
        "For each numbered news result, answer with exactly one topic it is genuinely about, "
        "or 'none' if it is off-topic or an advertisement.\n" + listing
    )
    verdicts = make_llm(temperature=0).with_structured_output(Relevance).invoke(prompt).verdicts
    verdicts = [v if v in topics else "none" for v in verdicts[:len(found)]]
    return verdicts + ["none"] * (len(found) - len(verdicts))


def coverage(sources: list[dict], topics: list[str]) -> dict[str, int]:
    return {t: sum(1 for s in sources if s["topic"] == t) for t in topics}


def tools_node(state: AgentState) -> AgentState:
    last = state["messages"][-1]
    topics = state["user_interests"]
    searches = state["searches_used"]
    stop = state.get("stop_reason")
    queried = {e["input"].get("query", "").strip().lower() for e in state["run_log"] if e["action"] == "search_news"}
    accepted, results, messages, run_log = [], [], [], []

    for call in last.tool_calls:
        name, args = call["name"], call["args"]
        if name == "search_news":
            query = args.get("query", "").strip().lower()
            if query in queried:
                observation = f"Already searched '{args.get('query')}'. Use a different query."
            elif searches >= MAX_SEARCHES:
                observation = "Search budget is used up. Call finish_research now."
            else:
                searches += 1
                queried.add(query)
                get_stream_writer()({"type": "searching", "query": args.get("query", "")})
                raw = TOOLS_BY_NAME[name].invoke(args)
                seen = {s["url"] for s in state.get("sources", [])} | {a["url"] for a in accepted}
                found = [r for r in raw if r.get("url") not in seen]
                kept_titles = []
                for r, topic in zip(found, judge_results(topics, found)):
                    if topic == "none":
                        continue
                    accepted.append({"topic": topic, "title": r.get("title", ""), "url": r.get("url", ""), "content": r["content"]})
                    results.append(f"{r.get('title', '')}\n{r['content']}\nSource: {r.get('url', '')}")
                    kept_titles.append(r.get("title", ""))
                if kept_titles:
                    observation = f"{len(found)} new results, {len(kept_titles)} relevant: " + "; ".join(kept_titles)
                elif raw and not found:
                    observation = f"All {len(raw)} results for '{args.get('query')}' were already seen. Try a different query."
                else:
                    observation = f"No relevant results for '{args.get('query')}'. Try a different query."
        elif name == "finish_research":
            sources_now = state.get("sources", []) + accepted
            gaps = [f"{t} ({n}/{MIN_SOURCES_PER_TOPIC})" for t, n in coverage(sources_now, topics).items() if n < MIN_SOURCES_PER_TOPIC]
            if gaps and searches < MAX_SEARCHES:
                observation = "Not enough relevant sources: " + ", ".join(gaps) + ". Search for these topics."
            else:
                stop = args.get("reason") or "finished"
                observation = "Research closed." + (f" Short on sources: {', '.join(gaps)}." if gaps else "")
        else:
            observation = f"Unknown tool {name}."
        messages.append(ToolMessage(content=observation, tool_call_id=call["id"]))
        run_log.append({"step": state["steps"], "action": name, "input": args, "observation": observation})

    if not stop and searches >= MAX_SEARCHES:
        stop = "search budget reached"
    if not stop and state["steps"] >= MAX_STEPS:
        stop = "step budget reached"

    update = {"messages": messages, "sources": accepted, "search_results": results, "searches_used": searches, "run_log": run_log}
    if stop:
        update["stop_reason"] = stop
    return update


def route_after_agent(state: AgentState) -> str:
    return "tools" if state["messages"][-1].tool_calls else "synthesize"


def route_after_tools(state: AgentState) -> str:
    return "synthesize" if state.get("stop_reason") else "agent"


def synthesize_context_node(state: AgentState) -> AgentState:
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

    return {"synthesized_context": context_block, "stop_reason": state.get("stop_reason") or "finished"}


def generate_script_node(state: AgentState) -> AgentState:
    context = state["synthesized_context"]
    language = state["language"]

    llm = make_llm(temperature=0.7)
    structured_llm = llm.with_structured_output(NewsScript)

    prompt = f"""You are creating an engaging two-person podcast/briefing conversation about current news.

Host A (named Anna) is informative, factual, and provides clear explanations.
Host B (named Sam) is dynamic, conversational, and adds engaging commentary and reactions.
Refer to the hosts only by their names, Anna and Sam, never as "Host A" or "Host B" in the dialogue text.

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
    workflow = StateGraph(AgentState)

    workflow.add_node("plan", plan_node)
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tools_node)
    workflow.add_node("synthesize_context", synthesize_context_node)
    workflow.add_node("generate_script", generate_script_node)

    workflow.set_entry_point("plan")
    workflow.add_edge("plan", "agent")
    workflow.add_conditional_edges("agent", route_after_agent, {"tools": "tools", "synthesize": "synthesize_context"})
    workflow.add_conditional_edges("tools", route_after_tools, {"agent": "agent", "synthesize": "synthesize_context"})
    workflow.add_edge("synthesize_context", "generate_script")
    workflow.add_edge("generate_script", END)

    return workflow.compile()


app = create_graph()
