from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, SystemMessage

from src import graph
from src.state import DialogueLine, NewsScript, Relevance, ResearchPlan

SCRIPT = NewsScript(title="Briefing", script=[DialogueLine(speaker="Host A", text="Hello.")])


class FakeChat:
    def __init__(self, responses):
        self.responses = list(responses)
        self.systems = []
        self.bound = []
        self.tool_choices = []
        self.parallel = []

    def bind_tools(self, tools, tool_choice=None, parallel_tool_calls=None):
        self.bound.append([t.name for t in tools])
        self.tool_choices.append(tool_choice)
        self.parallel.append(parallel_tool_calls)
        return self

    def with_structured_output(self, schema):
        return self

    def invoke(self, messages):
        if isinstance(messages, list) and messages and isinstance(messages[0], SystemMessage):
            self.systems.append(messages[0].content)
        return self.responses.pop(0)


def call(name, args, call_id):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


def judge(*verdicts):
    return Relevance(verdicts=list(verdicts))


def article(query):
    return {
        "title": f"Story about {query}",
        "url": f"https://news.example/{query.replace(' ', '-')}",
        "content": f"Detailed report on {query}: officials outlined new measures and reported figures today.",
    }


def base_state(**overrides):
    state = {
        "user_interests": ["AI"], "language": "English", "messages": [], "plan": [], "sources": [],
        "search_results": [], "run_log": [], "steps": 0, "searches_used": 0,
        "stop_reason": None, "synthesized_context": None, "final_script": None,
    }
    state.update(overrides)
    return state


def run_agent(responses, search):
    fake = FakeChat(responses)
    with patch.object(graph, "make_llm", return_value=fake), patch("src.tools.search_web", side_effect=search):
        return graph.app.invoke(base_state(), {"recursion_limit": graph.RECURSION_LIMIT})


def test_agent_searches_then_finishes_when_coverage_is_met():
    result = run_agent(
        [
            ResearchPlan(queries=["AI regulation"]),
            call("search_news", {"query": "AI regulation"}, "1"), judge("AI"),
            call("search_news", {"query": "AI policy rules"}, "2"), judge("AI"),
            call("finish_research", {"reason": "enough coverage"}, "3"),
            SCRIPT,
        ],
        search=lambda q: [article(q)],
    )
    assert result["final_script"].title == "Briefing"
    assert result["stop_reason"] == "enough coverage"
    assert result["searches_used"] == 2
    assert len(result["sources"]) == 2
    assert [e["action"] for e in result["run_log"] if e["action"] != "decide"] == ["plan", "search_news", "search_news", "finish_research"]


def test_finish_is_refused_until_topic_has_enough_sources():
    result = run_agent(
        [
            ResearchPlan(queries=["AI regulation"]),
            call("search_news", {"query": "AI regulation"}, "1"), judge("AI"),
            call("finish_research", {"reason": "done"}, "2"),
            call("search_news", {"query": "AI policy rules"}, "3"), judge("AI"),
            call("finish_research", {"reason": "done"}, "4"),
            SCRIPT,
        ],
        search=lambda q: [article(q)],
    )
    finishes = [e for e in result["run_log"] if e["action"] == "finish_research"]
    assert finishes[0]["observation"].startswith("Not enough relevant sources: AI (1/2)")
    assert result["stop_reason"] == "done"
    assert result["searches_used"] == 2


def test_off_topic_results_are_dropped():
    result = run_agent(
        [
            ResearchPlan(queries=["AI chips"]),
            call("search_news", {"query": "AI chips"}, "1"), judge("none", "AI"),
            AIMessage(content="Done."),
            SCRIPT,
        ],
        search=lambda q: [article("cheap laptops"), article(q)],
    )
    search_entry = [e for e in result["run_log"] if e["action"] == "search_news"][0]
    assert search_entry["observation"].startswith("2 new results, 1 relevant")
    assert len(result["sources"]) == 1
    assert len(result["search_results"]) == 1


def test_article_with_seen_url_is_not_counted_twice():
    same = article("AI regulation")
    result = run_agent(
        [
            ResearchPlan(queries=["AI regulation"]),
            call("search_news", {"query": "AI regulation"}, "1"), judge("AI"),
            call("search_news", {"query": "AI policy rules"}, "2"),
            AIMessage(content="Done."),
            SCRIPT,
        ],
        search=lambda q: [same],
    )
    repeat = [e for e in result["run_log"] if e["action"] == "search_news"][1]
    assert repeat["observation"].startswith("All 1 results")
    assert len(result["sources"]) == 1


def test_agent_sees_coverage_on_each_turn():
    fake = FakeChat([
        ResearchPlan(queries=["AI regulation"]),
        call("search_news", {"query": "AI regulation"}, "1"), judge("AI"),
        call("search_news", {"query": "AI policy rules"}, "2"), judge("AI"),
        call("finish_research", {"reason": "enough coverage"}, "3"),
        SCRIPT,
    ])
    with patch.object(graph, "make_llm", return_value=fake), patch("src.tools.search_web", side_effect=lambda q: [article(q)]):
        graph.app.invoke(base_state(), {"recursion_limit": graph.RECURSION_LIMIT})
    assert "Coverage: AI: 0/2 relevant sources (short)" in fake.systems[0]
    assert "AI: 2/2 relevant sources" in fake.systems[-1]
    assert "call finish_research now" in fake.systems[-1]


def test_model_is_offered_only_finish_once_covered():
    fake = FakeChat([
        ResearchPlan(queries=["AI regulation"]),
        call("search_news", {"query": "AI regulation"}, "1"), judge("AI"),
        call("search_news", {"query": "AI policy rules"}, "2"), judge("AI"),
        call("finish_research", {"reason": "enough coverage"}, "3"),
        SCRIPT,
    ])
    with patch.object(graph, "make_llm", return_value=fake), patch("src.tools.search_web", side_effect=lambda q: [article(q)]):
        result = graph.app.invoke(base_state(), {"recursion_limit": graph.RECURSION_LIMIT})
    assert fake.bound[0] == ["search_news", "finish_research"]
    assert fake.bound[-1] == ["finish_research"]
    assert fake.tool_choices[-1] == "finish_research"
    assert all(p is False for p in fake.parallel)
    assert result["stop_reason"] == "enough coverage"


def test_agent_rewrites_query_after_empty_result():
    result = run_agent(
        [
            ResearchPlan(queries=["AI regulation"]),
            call("search_news", {"query": "AI regulation"}, "1"),
            call("search_news", {"query": "AI regulation policy 2026"}, "2"), judge("AI"),
            AIMessage(content="Done."),
            SCRIPT,
        ],
        search=[[], [article("AI regulation policy 2026")]],
    )
    searches = [e for e in result["run_log"] if e["action"] == "search_news"]
    assert searches[0]["observation"].startswith("No relevant results for 'AI regulation'")
    assert [e["input"]["query"] for e in searches] == ["AI regulation", "AI regulation policy 2026"]


def test_repeated_query_is_rejected_without_using_budget():
    result = run_agent(
        [
            ResearchPlan(queries=["AI chips"]),
            call("search_news", {"query": "AI chips"}, "1"), judge("AI"),
            call("search_news", {"query": "ai chips "}, "2"),
            AIMessage(content="Done."),
            SCRIPT,
        ],
        search=lambda q: [article(q)],
    )
    repeat = [e for e in result["run_log"] if e["action"] == "search_news"][1]
    assert repeat["observation"].startswith("Already searched")
    assert result["searches_used"] == 1


def test_agent_stops_at_search_budget():
    responses = [ResearchPlan(queries=["q"])]
    for i in range(graph.MAX_SEARCHES):
        responses += [call("search_news", {"query": f"query {i}"}, str(i)), judge("AI")]
    responses.append(SCRIPT)
    result = run_agent(responses, search=lambda q: [article(q)])
    assert result["stop_reason"] == "search budget reached"
    assert result["searches_used"] == graph.MAX_SEARCHES


def test_agent_stops_when_model_does_not_finish():
    result = run_agent(
        [
            ResearchPlan(queries=["q"]),
            call("search_news", {"query": "q"}, "1"), judge("AI"),
            AIMessage(content="Done."),
            SCRIPT,
        ],
        search=lambda q: [article(q)],
    )
    assert result["stop_reason"] == "model stopped without calling finish_research"


def test_script_failure_propagates():
    llm = MagicMock()
    llm.with_structured_output.return_value.invoke.side_effect = Exception("insufficient_quota")
    with patch.object(graph, "make_llm", return_value=llm):
        with pytest.raises(Exception, match="insufficient_quota"):
            graph.generate_script_node(base_state(synthesized_context="# ctx"))
