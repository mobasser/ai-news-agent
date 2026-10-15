from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src import graph
from src.auth import hash_password
from src.main import FRONTEND_DIR, app_fastapi
from src.state import DialogueLine, NewsScript

LONG = "Major policy update announced today that affects how AI systems are regulated across the region."
SCRIPT = NewsScript(title="Test Briefing", script=[DialogueLine(speaker="Host A", text="Hello.")])


def base_state(**overrides):
    state = {
        "user_interests": ["AI"], "language": "English", "messages": [], "plan": [],
        "search_results": [], "run_log": [], "steps": 0, "searches_used": 0,
        "stop_reason": None, "synthesized_context": None, "final_script": None,
    }
    state.update(overrides)
    return state


def test_synthesize_filters_ads_and_duplicates():
    state = base_state(search_results=[LONG, LONG.upper(), "Subscribe now to our newsletter for more updates and deals!", "too short"])
    out = graph.synthesize_context_node(state)
    assert out["synthesized_context"].count("## Fact") == 1
    assert LONG in out["synthesized_context"]


def test_synthesize_raises_when_nothing_usable():
    with pytest.raises(RuntimeError):
        graph.synthesize_context_node(base_state(search_results=["short"]))


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setenv("TAVILY_API_KEY", "x")
    monkeypatch.setenv("APP_USERNAME", "admin")
    monkeypatch.setenv("APP_PASSWORD_HASH", hash_password("pw123"))
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    c = TestClient(app_fastapi)
    assert c.post("/api/auth/login", json={"username": "admin", "password": "pw123"}).status_code == 200
    return c


def test_api_requires_login():
    r = TestClient(app_fastapi).post("/api/generate-briefing", json={"user_interests": ["AI"]})
    assert r.status_code == 401
    r = TestClient(app_fastapi).post("/api/briefing/audio", json={"title": "t", "script": []})
    assert r.status_code == 401


def test_login_rejects_wrong_password(monkeypatch):
    monkeypatch.setenv("APP_USERNAME", "admin")
    monkeypatch.setenv("APP_PASSWORD_HASH", hash_password("pw123"))
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    c = TestClient(app_fastapi)
    assert c.post("/api/auth/login", json={"username": "admin", "password": "wrong"}).status_code == 401
    assert c.post("/api/auth/login", json={"username": "root", "password": "pw123"}).status_code == 401
    assert c.get("/api/auth/session").status_code == 401


def test_login_fails_closed_without_config(monkeypatch):
    monkeypatch.delenv("APP_USERNAME", raising=False)
    monkeypatch.delenv("APP_PASSWORD_HASH", raising=False)
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    assert TestClient(app_fastapi).post("/api/auth/login", json={"username": "", "password": ""}).status_code == 401


def test_session_and_logout(client):
    assert client.get("/api/auth/session").json() == {"user": "admin"}
    client.post("/api/auth/logout")
    assert TestClient(app_fastapi).get("/api/auth/session").status_code == 401


def test_audio_endpoint_returns_mp3(client):
    with patch("src.main.synthesize_briefing", return_value=[b"ID3a", b"ID3b"]) as synth:
        r = client.post("/api/briefing/audio", json={"title": "Test Briefing", "script": [{"speaker": "Host A", "text": "Hello."}]})
    assert r.status_code == 200
    assert r.json() == {"segments": ["SUQzYQ==", "SUQzYg=="]}
    assert synth.call_args[0][0].title == "Test Briefing"


def test_api_rejects_unsupported_language(client):
    r = client.post("/api/generate-briefing", json={"user_interests": ["AI"], "language": "Klingon"})
    assert r.status_code == 422


@pytest.mark.skipif(not FRONTEND_DIR.exists(), reason="frontend not built; run npm run build in frontend/")
def test_index_serves_ui():
    r = TestClient(app_fastapi).get("/")
    assert r.status_code == 200
    assert "Daily AI Briefing" in r.text


def test_api_returns_500_on_pipeline_failure(client):
    with patch("src.main.app.invoke", side_effect=RuntimeError("boom")):
        r = client.post("/api/generate-briefing", json={"user_interests": ["AI"]})
    assert r.status_code == 500
    assert "boom" in r.json()["detail"]


def test_api_returns_script_and_run_log_on_success(client):
    run_log = [{"step": 0, "action": "plan", "observation": "q"}]
    with patch("src.main.app.invoke", return_value={"final_script": SCRIPT, "run_log": run_log, "stop_reason": "enough coverage"}):
        r = client.post("/api/generate-briefing", json={"user_interests": ["AI"]})
    assert r.status_code == 200
    assert r.json() == {
        "title": "Test Briefing",
        "script": [{"speaker": "Host A", "text": "Hello."}],
        "run_log": run_log,
        "stop_reason": "enough coverage",
    }


def test_stream_emits_progress_then_briefing(client):
    import json
    from langchain_core.messages import AIMessage
    from src.state import ResearchPlan, Relevance

    def article(q):
        return {"title": f"Story {q}", "url": f"https://news.example/{q.replace(' ', '-')}", "content": f"Detailed report on {q} with facts and figures today."}

    responses = [
        ResearchPlan(queries=["AI regulation"]),
        AIMessage(content="", tool_calls=[{"name": "search_news", "args": {"query": "AI regulation"}, "id": "1"}]), Relevance(verdicts=["AI"]),
        AIMessage(content="", tool_calls=[{"name": "search_news", "args": {"query": "AI policy rules"}, "id": "2"}]), Relevance(verdicts=["AI"]),
        AIMessage(content="", tool_calls=[{"name": "finish_research", "args": {"reason": "enough"}, "id": "3"}]),
        SCRIPT,
    ]

    class Fake:
        def __init__(self):
            self.items = list(responses)

        def bind_tools(self, tools, **kwargs):
            return self

        def with_structured_output(self, schema):
            return self

        def invoke(self, messages):
            return self.items.pop(0)

    with patch.object(graph, "make_llm", return_value=Fake()), patch("src.tools.search_web", side_effect=lambda q: [article(q)]):
        r = client.post("/api/generate-briefing/stream", json={"user_interests": ["AI"]})
    events = [json.loads(line) for line in r.text.splitlines() if line.strip()]
    types = [e["type"] for e in events]
    assert "thinking" in types and "searching" in types and "step" in types
    assert types[-1] == "done"
    assert events[-1]["briefing"]["title"] == "Test Briefing"
    assert events[-1]["briefing"]["stop_reason"] == "enough"
