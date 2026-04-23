# CodeSentinel — Agentic Code Review System

A multi-agent AI system that reviews any public GitHub repository for security vulnerabilities, code quality issues, and dependency risks — powered by Google Gemini 2.0 Flash.

## Architecture

```
Repo Fetcher → Planner Agent → [Security + Quality + Dependency] (parallel)
             → Critic Agent → Fix Suggester → Re-evaluator (loop ≤2x)
             → Final Report (SSE streamed to React frontend)
```

## Setup

### 1. Backend

```bash
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Mac/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in your keys:
```bash
cp .env.example .env
```

Required:
- `GOOGLE_API_KEY` — get free from [Google AI Studio](https://ai.google.dev)

Optional:
- `GITHUB_TOKEN` — increases GitHub rate limit from 60 to 5000 req/hr

Start the backend:
```bash
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

## Agents

| Agent | Role |
|---|---|
| RepoFetcher | Fetches up to 40 relevant files via GitHub REST API |
| PlannerAgent | Analyzes repo and routes to correct specialist agents |
| SecurityAgent | Finds vulnerabilities (SQL injection, secrets, unsafe patterns) |
| QualityAgent | Checks complexity, dead code, missing error handling |
| DependencyAgent | Checks for outdated/vulnerable packages |
| CriticAgent | Deduplicates and re-ranks all findings |
| FixSuggesterAgent | Generates before/after code fixes |
| ReEvaluatorAgent | Verifies fixes (loops up to 2× if insufficient) |

## Demo Repository

Try with [DVWA](https://github.com/digininja/DVWA) — intentionally vulnerable PHP app with known SQL injection, hardcoded credentials, and more.

## Tech Stack

- **Backend**: FastAPI + uvicorn + google-generativeai
- **Frontend**: React + Vite + react-syntax-highlighter
- **AI**: Gemini 2.0 Flash (via Google AI Studio — free tier)
- **Static Analysis**: bandit (Python security), radon (complexity)
