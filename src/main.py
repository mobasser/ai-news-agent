from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Literal
from pathlib import Path
import base64
import json
import os
from dotenv import load_dotenv

from .auth import SESSION_SECONDS, check_credentials, make_token, verify_token
from .graph import RECURSION_LIMIT, app
from .audio import synthesize_briefing
from .state import NewsScript, DialogueLine

load_dotenv()

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend" / "out"
SESSION_COOKIE = "session"

app_fastapi = FastAPI(title="Personal Current News Agent", version="1.0.0")


LANGUAGES = Literal["English", "Spanish", "French", "German", "Portuguese", "Italian", "Hindi", "Arabic", "Chinese", "Japanese"]


class BriefingRequest(BaseModel):
    user_interests: List[str]
    language: LANGUAGES = "English"


class BriefingResponse(BaseModel):
    title: str
    script: List[dict]
    run_log: List[dict] = []
    stop_reason: str = ""


class LoginRequest(BaseModel):
    username: str
    password: str


def current_user(request: Request) -> str:
    user = verify_token(request.cookies.get(SESSION_COOKIE))
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")
    return user


@app_fastapi.post("/api/auth/login")
def login(body: LoginRequest, request: Request, response: Response):
    if not check_credentials(body.username, body.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    response.set_cookie(SESSION_COOKIE, make_token(body.username), max_age=SESSION_SECONDS, httponly=True, samesite="lax", secure=secure)
    return {"user": body.username}


@app_fastapi.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


@app_fastapi.get("/api/auth/session")
def session(user: str = Depends(current_user)):
    return {"user": user}


@app_fastapi.post("/api/generate-briefing", response_model=BriefingResponse)
def generate_briefing(request: BriefingRequest, user: str = Depends(current_user)):
    """Generate a news briefing based on user interests"""

    if not request.user_interests:
        raise HTTPException(status_code=400, detail="user_interests cannot be empty")

    openai_key = os.getenv("OPENAI_API_KEY")
    tavily_key = os.getenv("TAVILY_API_KEY")

    if not openai_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured")
    if not tavily_key:
        raise HTTPException(status_code=500, detail="TAVILY_API_KEY not configured")

    try:
        initial_state = {
            "user_interests": request.user_interests,
            "language": request.language,
            "messages": [],
            "plan": [],
            "sources": [],
            "search_results": [],
            "run_log": [],
            "steps": 0,
            "searches_used": 0,
            "stop_reason": None,
            "synthesized_context": None,
            "final_script": None,
        }

        result = app.invoke(initial_state, {"recursion_limit": RECURSION_LIMIT})

        final_script: NewsScript = result["final_script"]

        response = BriefingResponse(
            title=final_script.title,
            script=[
                {"speaker": line.speaker, "text": line.text}
                for line in final_script.script
            ],
            run_log=result.get("run_log", []),
            stop_reason=result.get("stop_reason") or "",
        )

        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating briefing: {str(e)}")


@app_fastapi.post("/api/generate-briefing/stream")
def generate_briefing_stream(request: BriefingRequest, user: str = Depends(current_user)):
    """Stream agent progress as newline-delimited JSON, ending with the full briefing"""

    if not request.user_interests:
        raise HTTPException(status_code=400, detail="user_interests cannot be empty")
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured")
    if not os.getenv("TAVILY_API_KEY"):
        raise HTTPException(status_code=500, detail="TAVILY_API_KEY not configured")

    def events():
        def line(event):
            return json.dumps(event, default=str) + "\n"

        run_log, stop_reason, final_script = [], "", None
        try:
            state = {
                "user_interests": request.user_interests,
                "language": request.language,
                "messages": [],
                "plan": [],
                "sources": [],
                "search_results": [],
                "run_log": [],
                "steps": 0,
                "searches_used": 0,
                "stop_reason": None,
                "synthesized_context": None,
                "final_script": None,
            }
            for mode, chunk in app.stream(state, {"recursion_limit": RECURSION_LIMIT}, stream_mode=["updates", "custom"]):
                if mode == "custom":
                    yield line(chunk)
                    continue
                for node, update in chunk.items():
                    for entry in update.get("run_log", []):
                        run_log.append(entry)
                        yield line({"type": "step", "entry": entry})
                    if node == "synthesize_context":
                        stop_reason = update.get("stop_reason") or stop_reason
                        yield line({"type": "stage", "text": "Writing the two-host script"})
                    if node == "generate_script":
                        final_script = update["final_script"]
            briefing = BriefingResponse(
                title=final_script.title,
                script=[{"speaker": l.speaker, "text": l.text} for l in final_script.script],
                run_log=run_log,
                stop_reason=stop_reason,
            )
            yield line({"type": "done", "briefing": briefing.model_dump()})
        except Exception as e:
            yield line({"type": "error", "detail": f"Error generating briefing: {e}"})

    return StreamingResponse(events(), media_type="application/x-ndjson")


class AudioResponse(BaseModel):
    segments: List[str]


@app_fastapi.post("/api/briefing/audio", response_model=AudioResponse)
def briefing_audio(briefing: BriefingResponse, user: str = Depends(current_user)):
    """Convert a generated briefing into one base64 MP3 segment per dialogue line"""

    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured")

    script = NewsScript(
        title=briefing.title,
        script=[DialogueLine(**line) for line in briefing.script],
    )
    try:
        segments = synthesize_briefing(script)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating audio: {str(e)}")
    return AudioResponse(segments=[base64.b64encode(s).decode("ascii") for s in segments])


@app_fastapi.get("/health")
async def health():
    return {"status": "healthy"}


app_fastapi.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True, check_dir=False), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app_fastapi, host="0.0.0.0", port=8000)
