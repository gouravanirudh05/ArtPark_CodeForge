# Adaptive Onboarding Engine

> AI-driven personalized learning pathway generator for corporate onboarding.

Upload a resume + job description → get a personalized, prerequisite-aware training pathway that skips what the candidate already knows and targets exactly what they need.

---

## Quick Start

### Prerequisites

- Docker + Docker Compose
- Internet connection (spaCy NER model downloads from HuggingFace on first request, ~100MB)

### Run with Docker

```bash
git clone <https://github.com/SathishAdithiyaaSV/ArtPark_CodeForge>
cd adaptive-onboarding

docker compose up --build
```

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API docs: http://localhost:8000/docs

### Run without Docker

**Backend**
```bash
cd backend
pip install -r requirements.txt
python -m spacy download en_core_web_sm
uvicorn main:app --reload --port 8000
```

**Frontend**
```bash
cd frontend
npm install
npm run dev
```

---

## Project Structure

```
adaptive-onboarding/
├── backend/
│   ├── main.py                        # FastAPI app — all endpoints
│   ├── requirements.txt
│   └── app/
│       ├── models/
│       │   └── schemas.py             # Pydantic models for all I/O types
│       └── services/
│           ├── skill_extractor.py     # spaCy NER + JD signal detection
│           ├── gap_analyzer.py        # Sentence-BERT semantic gap scoring
│           ├── path_planner.py        # Prerequisite DAG + Kahn's topo sort
│           ├── ner_inference.py       # DistilBERT NER inference (optional)
│           ├── llm_client.py          # Ollama wrapper (legacy fallback)
│           └── reasoning_trace.py    # Decision logging utility
├── frontend/
│   ├── src/
│   │   ├── App.jsx                    # Full React SPA
│   │   └── main.jsx
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
├── data/
│   ├── course_catalog.json            # Source-of-truth course list
│   └── onet_skills.json              # O*NET skill taxonomy + aliases
├── tests/
│   └── test_services.py              # Pytest suite (25 tests)
├── train_skill_ner.py                 # DistilBERT NER training script
├── distilbert_skill_ner_training.ipynb # Kaggle training notebook
├── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## How It Works

### Stage 1 — Skill Extraction

Two documents are processed independently:

**Resume** — The `amjad-awad/skill-extractor` spaCy NER model identifies skill entity spans. Proficiency level is inferred from surrounding context words (`"senior"` → advanced, `"learning"` → beginner).

**Job Description** — Same NER model, but with additional sentence-level signal detection. Sentences containing `"required"`, `"must have"`, `"essential"` mark skills as required (confidence 0.95). Sentences with `"preferred"`, `"nice to have"` mark skills as preferred (confidence 0.78).

If the NER model is unavailable, the system falls back to a keyword matcher covering 60+ common technical and soft skills.

### Stage 2 — Gap Analysis

All skills are embedded with **Sentence-BERT** (`all-MiniLM-L6-v2`) into 384-dimensional vectors.

For each required skill, the analyzer finds the most semantically similar candidate skill via cosine similarity:
- Similarity < 0.72 → skill is **missing** (gap score ≈ 1.0)
- Similarity ≥ 0.72 → **partial gap** scored by proficiency distance

**Gap score formula:**
```
gap_score = (1 - similarity) × proficiency_delta_weight
```

Skills are prioritised as high / medium / low based on gap score thresholds.

### Stage 3 — Pathway Generation

The path planner:
1. Loads `course_catalog.json` as the only permitted course source (no hallucinated courses)
2. Semantically matches course skills to gap skills (threshold: 0.60)
3. Skips courses where all taught skills are already semantically covered by the candidate (threshold: 0.75)
4. Builds a prerequisite **DAG** over remaining courses
5. Applies **Kahn's topological sort** — guarantees prerequisites always come before dependents
6. Attaches a rationale string to each step for the reasoning trace

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/analyze` | Full pipeline — resume PDF + JD → extract + gap + pathway |
| `POST` | `/extract` | Skill extraction only (resume PDF + JD text) |
| `POST` | `/gap` | Gap analysis only (JSON skill lists) |
| `POST` | `/pathway` | Pathway generation only (JSON gaps + candidate skills) |
| `GET`  | `/health` | Health check |

### `/analyze` — Full pipeline (used by the UI)

```bash
curl -X POST http://localhost:8000/analyze \
  -F "resume=@your_resume.pdf" \
  -F "job_description=We are looking for a Python ML Engineer..." \
  -F "role_title=ML Engineer"
```

### `/gap` — Gap analysis (Postman testing)

```json
POST /gap
{
  "candidate_skills": [
    {"name": "Python", "category": "programming_language", "proficiency": "intermediate", "confidence_score": 0.9},
    {"name": "SQL", "category": "programming_language", "proficiency": "beginner", "confidence_score": 0.8}
  ],
  "required_skills": [
    {"name": "Python", "category": "programming_language", "proficiency": "advanced", "confidence_score": 1.0},
    {"name": "PyTorch", "category": "framework", "proficiency": "intermediate", "confidence_score": 1.0},
    {"name": "MLOps", "category": "ml_ai", "proficiency": "intermediate", "confidence_score": 1.0}
  ]
}
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Skill extraction | spaCy NER — `amjad-awad/skill-extractor` (HuggingFace) |
| Embeddings | Sentence-BERT `all-MiniLM-L6-v2` |
| Graph algorithm | Kahn's topological sort |
| Backend | FastAPI + Uvicorn |
| PDF parsing | pdfplumber |
| Schema validation | Pydantic v2 |
| Frontend | React 18 + Vite |
| Skill taxonomy | O*NET 28.0 |
| Containerisation | Docker + Docker Compose |

---

## Running Tests

```bash
cd adaptive-onboarding
pip install -r backend/requirements.txt pytest-asyncio
pytest tests/ -v
```

The test suite covers:
- `ReasoningTrace` logging
- Proficiency gap math
- Cosine similarity edge cases
- Gap analyzer with mocked Sentence-BERT
- Topological sort correctness
- Course relevance matching
- Pathway skipping logic
- Pydantic schema validation

---

## Evaluation Criteria Coverage

| Criterion | Implementation |
|-----------|---------------|
| Technical sophistication (20%) | spaCy NER + Sentence-BERT + DAG topological sort |
| Grounding & reliability (15%) | Pathway strictly limited to `course_catalog.json` |
| Reasoning trace (10%) | `ReasoningTrace` logs every decision; surfaced in UI |
| Product impact (10%) | Hours-saved metric on dashboard; skipped courses listed |
| User experience (15%) | React SPA — timeline roadmap, gap bars, skill comparison, trace panel |
| Cross-domain scalability (10%) | NER generalises across technical, HR, finance, and operational roles |
| Documentation (20%) | This README + docstrings + technical doc + 5-slide deck |
