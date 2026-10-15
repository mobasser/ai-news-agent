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

## Architecture

The agent uses a LangGraph StateGraph with three sequential phases:

1. **search_news_node**: Executes targeted search queries for each user interest with current date context
2. **synthesize_context_node**: Filters out ads, removes duplicates, and compiles facts into a markdown context block
3. **generate_script_node**: Uses structured output to generate a two-host conversation script based on the synthesized context

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
