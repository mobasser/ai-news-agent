from concurrent.futures import ThreadPoolExecutor

from openai import OpenAI

from .state import NewsScript

VOICES = {"Agent Anna": "nova", "Agent Sam": "onyx"}
TTS_MODEL = "tts-1"


def synthesize_briefing(script: NewsScript) -> list[bytes]:
    """Convert each dialogue line to an MP3 segment in parallel, preserving script order."""
    client = OpenAI()

    def speak(line):
        response = client.audio.speech.create(
            model=TTS_MODEL,
            voice=VOICES.get(line.speaker, "alloy"),
            input=line.text,
            response_format="mp3",
        )
        return response.read()

    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(speak, script.script))
