# Personal Current News Agent

A production-ready AI-powered news briefing agent that uses LangGraph for orchestration, LangChain for LLM integration, and FastAPI for API exposure.

## Features

- **Dynamic News Gathering**: Uses Tavily search to fetch current news based on user interests
- **Intelligent Filtering**: Removes ads and duplicates from search results
- **Creative Script Generation**: Generates engaging two-host podcast-style briefings using GPT-4o-mini
- **Structured Output**: Uses Pydantic models for type-safe JSON responses
- **FastAPI Integration**: RESTful API endpoint for triggering news briefings

## Technology Stack

- **Orchestration**: LangGraph (StateGraph)
- **LLM Provider**: LangChain with OpenAI (gpt-4o-mini)
- **Search**: Tavily Search API
- **API Framework**: FastAPI
- **Validation**: Pydantic v2
- **Environment**: python-dotenv

## Project Structure

```
Personal-AI-News-AGent/
├── requirements.txt          # Python dependencies
├── .env.example              # Example environment variables
├── .env                      # Actual environment keys (not committed)
├── src/
│   ├── __init__.py
│   ├── state.py              # TypedDict and Pydantic models
│   ├── graph.py              # LangGraph nodes and StateGraph
│   └── main.py               # FastAPI application
└── tests/
    └── test_pipeline.py      # Mocked pipeline and API tests
```

## Installation

1. Clone the repository:
```bash
cd Personal-AI-News-AGent
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
cp .env.example .env
```

Edit `.env` and add your API keys:
```
OPENAI_API_KEY=your_openai_api_key_here
TAVILY_API_KEY=your_tavily_api_key_here
```

## Usage

### Running the API Server

Start the FastAPI server:
```bash
python -m uvicorn src.main:app_fastapi --reload
```

The server will start on `http://localhost:8000`

### API Endpoint

**POST** `/api/generate-briefing`

Request body:
```json
{
  "user_interests": ["AI technology", "climate change", "space exploration"]
}
```

Response:
```json
{
  "title": "Today's Tech & Science Briefing",
  "script": [
    {
      "speaker": "Host A",
      "text": "Welcome to today's briefing where we cover the latest in AI, climate, and space news."
    },
    {
      "speaker": "Host B",
      "text": "That's right! Let's dive into what's happening in the world of technology today."
    }
  ]
}
```

### Testing

Run the test suite (external APIs are mocked, so no credits are used):
```bash
python -m pytest
```

### Interactive API Documentation

Once the server is running, visit:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Frontend (Next.js)

The web interface lives in `frontend/` and is built with Next.js (App Router, static export) and React.

Build it once, then run the server. FastAPI serves the built files from `frontend/out`:
```bash
cd frontend
npm install
npm run build
cd ..
python -m uvicorn src.main:app_fastapi --host 127.0.0.1 --port 8000
```

For frontend development with hot reload, run the API on port 8000 and then run `npm run dev` inside `frontend/`. The dev server runs on port 3000 and proxies `/api` to the API.

## Architecture

The agent is a LangGraph StateGraph:

1. **plan**: an LLM with structured output writes 3 to 5 search queries that cover the user's topics.
2. **agent** and **tools** loop: the model chooses each action. It can call `search_news` (Tavily, last day of news) or `finish_research` with a reason. Each search result is read back into the model's context before the next decision.
3. **synthesize_context_node**: Filters out ads, removes duplicates, and compiles facts into a markdown context block.
4. **generate_script_node**: Uses structured output to generate a two-host conversation script based on the synthesized context.

Budgets are set in `src/graph.py`: `MAX_SEARCHES` (6) and `MAX_STEPS` (10). Repeated queries are rejected without using a search. Every run returns a `run_log` of the plan and each action, with its observation, and a `stop_reason`. The page shows both under "Agent decisions".

Known limits: the agent doesn't check whether each result is on-topic, and it often uses its whole search budget instead of stopping once coverage is enough.

## Health Check

Check if the API is running:
```bash
curl http://localhost:8000/health
```

Response:
```json
{
  "status": "healthy"
}
```

## License

MIT
