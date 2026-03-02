# Ved.io — Python Backend

> AI Drama Video Generation Platform  
> **Python 3.11 + FastAPI** (migrated from Go/Gin)

## Quick Start

```bash
# 1. Install dependencies
cd backend-py
pip install -e ".[dev]"

# 2. Copy and configure environment
cp .env.example .env

# 3. Initialize database
make migrate             # Alembic migrations
# OR (dev only, creates tables directly)
python -c "import asyncio; from core.database import init_db; from core.config import settings; asyncio.run(init_db(settings().database))"

# 4. Start development server
make run
# → http://localhost:5678
# → API docs at http://localhost:5678/docs
```

## Docker (full stack with Postgres + MinIO + Redis)

```bash
docker compose -f docker-compose.python.yml up --build
```

## Project Structure

```
backend-py/
├── main.py                    # FastAPI app factory & entry point
├── core/
│   ├── config.py              # Pydantic BaseSettings (replaces Go Viper)
│   ├── database.py            # SQLAlchemy 2.0 async engine + session
│   ├── logger.py              # structlog (replaces Go Zap)
│   ├── storage.py             # Local file storage adapter
│   └── ai_clients/
│       ├── openai_client.py   # OpenAI-compatible async HTTP client
│       └── gemini_client.py   # Google Gemini async client
├── models/                    # SQLAlchemy ORM models (replaces GORM)
│   ├── drama.py               # Drama, Character, Episode, Storyboard, Scene, Prop
│   ├── image_generation.py
│   ├── video_generation.py
│   ├── ai_config.py
│   ├── task.py                # AsyncTask
│   ├── asset.py               # Asset, CharacterLibrary
│   └── video_merge.py         # VideoMerge, FramePrompt
├── schemas/                   # Pydantic v2 request/response schemas
│   ├── drama.py
│   └── generation.py
├── services/                  # Business logic layer
│   ├── ai_service.py          # Dynamic LLM client provider
│   ├── drama_service.py       # Drama CRUD
│   ├── image_service.py       # Image generation + storage
│   ├── script_service.py      # LLM script + storyboard generation
│   ├── task_service.py        # Async task tracking
│   ├── video_merge_service.py # FFmpeg video concatenation
│   └── critic.py              # [NEW] Iterative Feedback Critic (LLM-based scorer)
├── orchestrator/
│   └── pipeline.py            # [NEW] Iterative Feedback Generator pipeline
├── api/
│   ├── deps.py                # FastAPI dependency injection
│   └── routers/
│       ├── dramas.py          # /api/v1/dramas (11 routes)
│       ├── ai_configs.py      # /api/v1/ai-configs (6 routes)
│       ├── images.py          # /api/v1/images (8 routes)
│       ├── videos.py          # /api/v1/videos + video-merges + tasks + assets
│       └── misc.py            # characters, scenes, storyboards, props, episodes, etc.
├── alembic/                   # Database migrations (replaces GORM AutoMigrate)
│   └── env.py
├── tests/
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_critic.py         # 5 tests
│   │   └── test_script_service.py # 4 tests
│   └── integration/
│       └── test_smoke_pipeline.py # 5 smoke tests
└── Makefile                   # dev commands (run, test, lint, migrate)
```

## API Reference

All 75+ routes from the original Go backend are preserved:

| Route | Description |
|-------|------------|
| `GET /health` | Health check |
| `GET/POST /api/v1/dramas` | List / create dramas |
| `GET/PUT/DELETE /api/v1/dramas/:id` | Get / update / delete drama |
| `PUT /api/v1/dramas/:id/outline` | Save story outline |
| `PUT /api/v1/dramas/:id/characters` | Bulk-save characters |
| `PUT /api/v1/dramas/:id/episodes` | Bulk-save episodes |
| `GET/POST /api/v1/ai-configs` | AI provider configuration |
| `POST /api/v1/ai-configs/test` | Test AI connection |
| `GET/POST /api/v1/images` | Image generation |
| `GET/POST /api/v1/videos` | Video generation |
| `GET/POST /api/v1/video-merges` | FFmpeg video merge |
| `GET /api/v1/tasks/:id` | Background task status |
| `GET/POST /api/v1/assets` | Asset management |
| `GET/POST /api/v1/character-library` | Character library |
| `POST /api/v1/generation/characters` | LLM character generation |
| `POST /api/v1/upload/image` | Image upload |
| `GET/PUT /api/v1/settings/language` | Language settings |
| *(and many more)* | |

Full OpenAPI docs: http://localhost:5678/docs

## Development Commands

```bash
make run          # Hot-reload dev server
make test         # Full test suite
make test-unit    # Unit tests only
make lint         # Black + Ruff check
make typecheck    # mypy
make security     # Bandit security scan
make migrate      # Apply Alembic migrations
make format       # Auto-format code
```

## New: Iterative Feedback Generator

The `critic.py` + `pipeline.py` modules implement an iterative draft→evaluate→regenerate loop:

1. **Draft**: Generate initial scene images/videos with AI providers
2. **Evaluate**: `CriticService` scores each scene 0–10 using an LLM
3. **Replan**: Low-scoring scenes get `alternative_prompt` fix suggestions  
4. **Regenerate**: Flagged scenes are regenerated with improved prompts
5. **Repeat**: Until all scenes pass threshold score or max iterations reached

Configure via environment:
```env
CRITIC_SCORE_THRESHOLD=7.5  # Default: 7.5/10
CRITIC_MAX_ITERATIONS=3     # Default: 3 iterations
```

## Tech Stack

| Go (before) | Python (after) |
|------------|---------------|
| `gin-gonic/gin` | `FastAPI` |
| `gorm.io/gorm` | `SQLAlchemy 2.0 async` |
| `gorm.io/gorm` AutoMigrate | `Alembic` |
| `spf13/viper` | `pydantic-settings` |
| `go.uber.org/zap` | `structlog` |
| Custom HTTP client | `httpx` (async) |
| Manual retry logic | `tenacity` |
| N/A | Iterative Feedback Generator |
