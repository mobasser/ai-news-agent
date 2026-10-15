from typing import TypedDict, List, Annotated, Optional
from pydantic import BaseModel, Field
from langgraph.graph.message import add_messages
from operator import add


class DialogueLine(BaseModel):
    speaker: str = Field(description="The host speaking: 'Host A' or 'Host B'")
    text: str = Field(description="The exact spoken dialogue line without brackets or markup.")


class NewsScript(BaseModel):
    title: str = Field(description="Catchy title for today's current news briefing")
    script: List[DialogueLine]


class ResearchPlan(BaseModel):
    queries: List[str] = Field(description="3 to 5 distinct news search queries that cover the user's topics")


class Relevance(BaseModel):
    verdicts: List[str] = Field(description="For each numbered result in order: the one topic it is genuinely about, or 'none' if off-topic or an advertisement")


class AgentState(TypedDict):
    user_interests: List[str]
    language: str
    messages: Annotated[list, add_messages]
    plan: List[str]
    sources: Annotated[list, add]
    search_results: Annotated[List[str], add]
    run_log: Annotated[List[dict], add]
    steps: int
    searches_used: int
    stop_reason: Optional[str]
    synthesized_context: Optional[str]
    final_script: Optional[NewsScript]
