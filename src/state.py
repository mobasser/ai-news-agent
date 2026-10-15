from typing import TypedDict, List, Annotated, Optional
from pydantic import BaseModel, Field
from operator import add


class DialogueLine(BaseModel):
    speaker: str = Field(description="The host speaking: 'Host A' or 'Host B'")
    text: str = Field(description="The exact spoken dialogue line without brackets or markup.")


class NewsScript(BaseModel):
    title: str = Field(description="Catchy title for today's current news briefing")
    script: List[DialogueLine]


class AgentState(TypedDict):
    user_interests: List[str]
    language: str
    search_results: Annotated[List[str], add]
    synthesized_context: Optional[str]
    final_script: Optional[NewsScript]
