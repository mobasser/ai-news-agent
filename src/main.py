from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Literal
from pathlib import Path
import base64
import os
from dotenv import load_dotenv

from .auth import SESSION_SECONDS, check_credentials, make_token, verify_token
from .graph import app
from .audio import synthesize_briefing
from .state import NewsScript, DialogueLine

load_dotenv()

STATIC_DIR = Path(__file__).parent / "static"
SESSION_COOKIE = "session"

app_fastapi = FastAPI(title="Personal Current News Agent", version="1.0.0")
app_fastapi.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


LANGUAGES = Literal["English", "Spanish", "French", "German", "Portuguese", "Italian", "Hindi", "Arabic", "Chinese", "Japanese"]


class BriefingRequest(BaseModel):
    user_interests: List[str]
    language: LANGUAGES = "English"


class BriefingResponse(BaseModel):
    title: str
    script: List[dict]


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
            "search_results": [],
            "synthesized_context": None,
            "final_script": None,
        }

        result = app.invoke(initial_state)

        final_script: NewsScript = result["final_script"]

        response = BriefingResponse(
            title=final_script.title,
            script=[
                {"speaker": line.speaker, "text": line.text}
                for line in final_script.script
            ]
        )

        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating briefing: {str(e)}")


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


@app_fastapi.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app_fastapi.get("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app_fastapi, host="0.0.0.0", port=8000)
