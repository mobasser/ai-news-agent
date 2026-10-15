from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src import graph
from src.auth import hash_password
from src.main import app_fastapi
from src.state import DialogueLine, NewsScript

LONG = "Major policy update announced today that affects how AI systems are regulated across the region."
SCRIPT = NewsScript(title="Test Briefing", script=[DialogueLine(speaker="Host A", text="Hello.")])


def base_state(**overrides):
    state = {"user_interests": ["AI"], "language": "English", "search_results": [], "synthesized_context": None, "final_script": None}
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


def test_search_raises_when_no_results():
    tool = MagicMock()
    tool.invoke.return_value = {"query": "AI", "results": []}
    with patch.object(graph, "TavilySearch", return_value=tool):
        with pytest.raises(RuntimeError):
            graph.search_news_node(base_state())


def test_search_collects_content():
    tool = MagicMock()
    tool.invoke.return_value = {"query": "AI", "results": [{"content": LONG}, {"title": "no content"}]}
    with patch.object(graph, "TavilySearch", return_value=tool):
        out = graph.search_news_node(base_state(user_interests=["AI", "space"]))
    assert out["search_results"] == [LONG, LONG]


def test_script_failure_propagates():
    llm = MagicMock()
    llm.with_structured_output.return_value.invoke.side_effect = Exception("insufficient_quota")
    with patch.object(graph, "ChatOpenAI", return_value=llm):
        with pytest.raises(Exception, match="insufficient_quota"):
            graph.generate_script_node(base_state(synthesized_context="# ctx"))


def test_full_graph_with_mocks():
    tool = MagicMock()
    tool.invoke.return_value = {"query": "AI", "results": [{"content": LONG}]}
    llm = MagicMock()
    llm.with_structured_output.return_value.invoke.return_value = SCRIPT.model_copy(deep=True)
    with patch.object(graph, "TavilySearch", return_value=tool), patch.object(graph, "ChatOpenAI", return_value=llm):
        result = graph.app.invoke(base_state())
    assert result["final_script"].title == "Test Briefing"
    assert result["final_script"].script[0].speaker == "Agent Anna"


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


def test_index_serves_ui():
    r = TestClient(app_fastapi).get("/")
    assert r.status_code == 200
    assert "Daily AI Briefing" in r.text


def test_api_returns_500_on_pipeline_failure(client):
    with patch("src.main.app.invoke", side_effect=RuntimeError("boom")):
        r = client.post("/api/generate-briefing", json={"user_interests": ["AI"]})
    assert r.status_code == 500
    assert "boom" in r.json()["detail"]


def test_api_returns_script_on_success(client):
    with patch("src.main.app.invoke", return_value={"final_script": SCRIPT}):
        r = client.post("/api/generate-briefing", json={"user_interests": ["AI"]})
    assert r.status_code == 200
    assert r.json() == {"title": "Test Briefing", "script": [{"speaker": "Host A", "text": "Hello."}]}
