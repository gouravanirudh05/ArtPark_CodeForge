# Adaptive Onboarding Engine

An AI-driven, adaptive learning engine that parses a new hire's capabilities from their resume and a job description, then dynamically generates a personalized training pathway to close identified skill gaps.

---

## Quick Start

### Prerequisites
- Docker + Docker Compose **or** Python 3.11+ and Node 20+
- [Ollama](https://ollama.ai) running locally with `llama3` pulled

### With Docker Compose (recommended)

```bash
git clone <your-repo>
cd adaptive-onboarding

docker compose up --build

# In a separate terminal, pull the LLM model:
docker exec adaptive-onboarding-ollama-1 ollama pull llama3
```

- Backend: http://localhost:8000
- Frontend: http://localhost:3000
- API docs: http://localhost:8000/docs

### Without Docker

**Backend**
```bash
cd backend
pip install -r requirements.txt
python -m spacy download en_core_web_sm

# Start Ollama separately and pull llama3:
ollama pull llama3

uvicorn main:app --reload --port 8000
```

**Frontend**
```bash
cd frontend
npm install
npm run dev
```

---

## Architecture

```
frontend/          React SPA — upload, roadmap, gap chart, trace panel
backend/
  main.py          FastAPI app — CORS, /extract, /gap, /pathway, /analyze
  app/
    models/
      schemas.py   Pydantic models for all request/response types
    services/
      llm_client.py       Ollama API wrapper (Llama 3 / Mistral)
      skill_extractor.py  spaCy NER + LLM structured JSON extraction
      gap_analyzer.py     Sentence-BERT embeddings + cosine similarity gap scoring
      path_planner.py     Prerequisite DAG + Kahn's topological sort
      reasoning_trace.py  Step-by-step decision logger
    routers/       (endpoint logic lives in main.py for simplicity)
data/
  course_catalog.json   Source-of-truth course list (no hallucinated courses)
  onet_skills.json      O*NET skill taxonomy for normalisation
```

---

## Skill-Gap Analysis Logic

### 1. Skill Extraction (`skill_extractor.py`)
- **spaCy pass**: `en_core_web_sm` extracts noun phrases as hints to reduce LLM hallucination
- **LLM pass**: Llama 3 receives the text + spaCy hints and returns a structured JSON array of skills with name, category, proficiency level, and confidence score
- **Normalisation**: Skills are mapped to canonical names using the O*NET taxonomy alias table

### 2. Gap Analysis (`gap_analyzer.py`)
- Skills are embedded using **Sentence-BERT** (`all-MiniLM-L6-v2`)
- Each required skill is matched to the most semantically similar candidate skill using **cosine similarity**
- Similarity below 0.72 → skill is treated as **missing** (gap score ≈ 1 - similarity)
- Similarity above threshold → **proficiency gap** scored from level distance (beginner→expert = 3 levels)
- Final gap score blends similarity distance and proficiency delta
- **Redundant skills** (candidate skills not matched to any requirement) are surfaced for training skip decisions

### 3. Adaptive Path Planning (`path_planner.py`)
- Loads `course_catalog.json` as the only permissible course source (grounds the system)
- Filters to courses that teach at least one identified gap skill
- Skips courses whose entire skill set the candidate already demonstrates
- Builds a **prerequisite DAG** over remaining courses
- Applies **Kahn's topological sort** to ensure prerequisites are always completed before dependents
- Each step includes a human-readable rationale logged to the reasoning trace

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/analyze` | Full pipeline (resume PDF + JD form data) |
| POST | `/extract` | Skill extraction only |
| POST | `/gap` | Gap analysis only |
| POST | `/pathway` | Pathway generation only |
| GET | `/health` | Health check |

Interactive docs at `/docs` (Swagger UI).

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| LLM | Llama 3 (via Ollama) or Mistral |
| Embeddings | Sentence-BERT `all-MiniLM-L6-v2` |
| NER pre-pass | spaCy `en_core_web_sm` |
| Graph algorithm | Kahn's topological sort (stdlib) |
| Backend | FastAPI + Uvicorn |
| Frontend | React 18 + Vite |
| PDF parsing | pdfplumber |
| Skill taxonomy | O*NET database |

---

## Datasets

- **O*NET 28.0** — skill taxonomy and occupational data (public domain, onetcenter.org)
- **Kaggle Resume Dataset** — used for prompt engineering and testing (CC0)
- **Internal `course_catalog.json`** — custom catalog ensuring zero hallucinated course recommendations

---

## Evaluation Criteria Coverage

| Criterion | Implementation |
|-----------|---------------|
| Technical sophistication (20%) | spaCy NER + Sentence-BERT embeddings + DAG topological sort |
| Grounding & reliability (15%) | Pathway strictly limited to `course_catalog.json` — no invented courses |
| Reasoning trace (10%) | `ReasoningTrace` class logs every decision step; surfaced in UI |
| Product impact (10%) | Redundant hours saved metric displayed on results dashboard |
| User experience (15%) | React SPA with timeline roadmap, gap bars, skill comparison, trace panel |
| Cross-domain scalability (10%) | Semantic embedding matching works across technical and non-technical roles |
| Documentation (20%) | This README + inline docstrings + 5-slide deck |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `LLM_MODEL` | `llama3` | Model name (also accepts `mistral`) |
