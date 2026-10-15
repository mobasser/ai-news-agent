import truststore

truststore.inject_into_ssl()

from datetime import datetime
from langchain_core.tools import tool
from langchain_tavily import TavilySearch


def search_web(query: str) -> list[dict]:
    response = TavilySearch(max_results=5, search_depth="basic", topic="news", time_range="day").invoke({"query": query})
    if not isinstance(response, dict) or "results" not in response:
        return []
    return [r for r in response["results"] if r.get("content")]


@tool
def search_news(query: str) -> list[dict]:
    """Search recent news for a query. Returns articles with title, url and content snippet."""
    return search_web(f"{query} {datetime.now().strftime('%Y-%m-%d')}")


@tool
def finish_research(reason: str) -> str:
    """Call this when coverage of every topic is sufficient, or when more searching cannot help. Give the reason."""
    return reason
