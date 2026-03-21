"""
Skill Extractor Service
-----------------------
Pipeline:
  Resume  -> spaCy NER (amjad-awad/skill-extractor) -> skills + proficiency inference
  JD      -> spaCy NER + required/preferred signal detection -> skills + priority weight

Primary:  amjad-awad/skill-extractor (HuggingFace spaCy NER model)
Fallback: Keyword matching (always works, no network needed)
"""

import json
import re
from pathlib import Path
from typing import List, Tuple, Optional

from app.models.schemas import Skill, ProficiencyLevel
from app.services.reasoning_trace import ReasoningTrace

ONET_PATH = Path("/app/data/onet_skills.json")

# JD signal patterns
REQUIRED_SIGNALS  = [
    "required", "must have", "must", "need", "essential",
    "mandatory", "minimum", "qualification", "you have", "you will have",
]
PREFERRED_SIGNALS = [
    "preferred", "nice to have", "plus", "bonus", "desired",
    "advantage", "beneficial", "ideally", "good to have", "optional",
]

PROFICIENCY_HINTS = {
    ProficiencyLevel.EXPERT:       ["expert", "10+ years", "8+ years", "lead", "principal", "architect"],
    ProficiencyLevel.ADVANCED:     ["advanced", "strong", "proficient", "senior", "5+ years", "deep knowledge"],
    ProficiencyLevel.INTERMEDIATE: ["experience", "familiar", "working knowledge", "2+ years", "3+ years"],
    ProficiencyLevel.BEGINNER:     ["basic", "beginner", "exposure", "learning", "introductory", "entry"],
}


def _load_onet() -> dict:
    if ONET_PATH.exists():
        return json.loads(ONET_PATH.read_text())
    return {}

ONET = _load_onet()

def _normalise(name: str) -> str:
    return ONET.get("aliases", {}).get(name.lower(), name)

def _categorise(name: str) -> str:
    name_lower = name.lower()
    for cat, skills in ONET.get("categories", {}).items():
        if any(name_lower == s.lower() for s in skills):
            return cat
    return "domain_knowledge"

def _infer_proficiency(context: str) -> Optional[ProficiencyLevel]:
    ctx = context.lower()
    for level, hints in PROFICIENCY_HINTS.items():
        if any(h in ctx for h in hints):
            return level
    return ProficiencyLevel.INTERMEDIATE


# spaCy NER model — lazy loaded
_nlp = None

def _get_nlp():
    global _nlp
    if _nlp is None:
        from huggingface_hub import snapshot_download
        import spacy
        print("[SkillExtractor] Downloading amjad-awad/skill-extractor from HuggingFace...")
        model_path = snapshot_download("amjad-awad/skill-extractor", repo_type="model")
        _nlp = spacy.load(model_path)
        print("[SkillExtractor] spaCy NER model loaded successfully")
    return _nlp


def _run_ner(text: str) -> List[Tuple[str, int, int]]:
    """Run NER model, return list of (skill_text, start_char, end_char)."""
    nlp    = _get_nlp()
    spans  = []
    offset = 0
    chunk_size = 100_000
    for i in range(0, len(text), chunk_size):
        chunk = text[i:i + chunk_size]
        doc   = nlp(chunk)
        for ent in doc.ents:
            if "SKILL" in ent.label_.upper():
                spans.append((
                    ent.text.strip(),
                    ent.start_char + offset,
                    ent.end_char   + offset,
                ))
        offset += len(chunk)
    return spans


def _split_sentences(text: str) -> List[str]:
    return re.split(r'(?<=[.!?])\s+|\n', text)

def _sentence_priority(sentence: str) -> str:
    s = sentence.lower()
    if any(sig in s for sig in REQUIRED_SIGNALS):
        return "required"
    if any(sig in s for sig in PREFERRED_SIGNALS):
        return "preferred"
    return "neutral"

def _build_priority_map(text: str) -> dict:
    """Map each character position to sentence priority."""
    priority_map = {}
    pos = 0
    for sentence in _split_sentences(text):
        priority = _sentence_priority(sentence)
        for i in range(pos, pos + len(sentence)):
            priority_map[i] = priority
        pos += len(sentence) + 1
    return priority_map

def _confidence(priority: str, source_label: str) -> float:
    if source_label == "resume":
        return 0.88
    if priority == "required":
        return 0.95
    if priority == "preferred":
        return 0.78
    return 0.85


async def extract_skills(
    text: str,
    source_label: str = "text",
) -> Tuple[List[Skill], List[str]]:
    trace = ReasoningTrace("SkillExtractor")
    trace.log(f"Received {source_label} ({len(text)} chars)")

    skills: List[Skill] = []

    # Primary: spaCy NER model
    try:
        spans = _run_ner(text)
        trace.log(f"spaCy NER found {len(spans)} raw skill spans")

        priority_map = _build_priority_map(text) if source_label == "job description" else {}

        seen = set()
        for span_text, start, end in spans:
            name = _normalise(span_text)
            if not name or len(name) < 2 or name.lower() in seen:
                continue
            seen.add(name.lower())

            context  = text[max(0, start - 60): end + 60]
            priority = priority_map.get(start, "neutral")

            skills.append(Skill(
                name=name,
                category=_categorise(name),
                proficiency=_infer_proficiency(context),
                confidence_score=_confidence(priority, source_label),
            ))

        required_count  = sum(1 for s in skills if s.confidence_score >= 0.9)
        preferred_count = sum(1 for s in skills if s.confidence_score < 0.85)
        trace.log(
            f"Extracted {len(skills)} unique skills via NER"
            + (f" — {required_count} required, {preferred_count} preferred"
               if source_label == "job description" else "")
        )

    except Exception as e:
        trace.log(f"spaCy NER failed: {e} — falling back to keywords")
        skills = []

    # Fallback: keyword matching
    if not skills:
        trace.log("Using keyword fallback extraction")
        skills = _keyword_fallback(text, source_label)
        trace.log(f"Keyword fallback found {len(skills)} skills")

    trace.log(f"Final: {len(skills)} skills from {source_label}")
    return skills, trace.all()


def _keyword_fallback(text: str, source_label: str = "text") -> List[Skill]:
    text_lower = text.lower()
    skill_map = [
        ("Python","programming_language",ProficiencyLevel.INTERMEDIATE),
        ("JavaScript","programming_language",ProficiencyLevel.INTERMEDIATE),
        ("TypeScript","programming_language",ProficiencyLevel.INTERMEDIATE),
        ("Java","programming_language",ProficiencyLevel.INTERMEDIATE),
        ("C++","programming_language",ProficiencyLevel.INTERMEDIATE),
        ("SQL","programming_language",ProficiencyLevel.INTERMEDIATE),
        ("Scala","programming_language",ProficiencyLevel.INTERMEDIATE),
        ("Go","programming_language",ProficiencyLevel.INTERMEDIATE),
        ("R","programming_language",ProficiencyLevel.BEGINNER),
        ("PyTorch","framework",ProficiencyLevel.INTERMEDIATE),
        ("TensorFlow","framework",ProficiencyLevel.INTERMEDIATE),
        ("scikit-learn","framework",ProficiencyLevel.INTERMEDIATE),
        ("React","framework",ProficiencyLevel.INTERMEDIATE),
        ("FastAPI","framework",ProficiencyLevel.INTERMEDIATE),
        ("Django","framework",ProficiencyLevel.INTERMEDIATE),
        ("Flask","framework",ProficiencyLevel.INTERMEDIATE),
        ("Pandas","framework",ProficiencyLevel.INTERMEDIATE),
        ("NumPy","framework",ProficiencyLevel.INTERMEDIATE),
        ("LangChain","framework",ProficiencyLevel.INTERMEDIATE),
        ("Hugging Face","framework",ProficiencyLevel.INTERMEDIATE),
        ("Docker","tool",ProficiencyLevel.INTERMEDIATE),
        ("Kubernetes","tool",ProficiencyLevel.INTERMEDIATE),
        ("Git","tool",ProficiencyLevel.INTERMEDIATE),
        ("AWS","tool",ProficiencyLevel.INTERMEDIATE),
        ("GCP","tool",ProficiencyLevel.INTERMEDIATE),
        ("Azure","tool",ProficiencyLevel.INTERMEDIATE),
        ("Terraform","tool",ProficiencyLevel.INTERMEDIATE),
        ("Apache Spark","tool",ProficiencyLevel.INTERMEDIATE),
        ("Apache Kafka","tool",ProficiencyLevel.INTERMEDIATE),
        ("Apache Airflow","tool",ProficiencyLevel.INTERMEDIATE),
        ("PostgreSQL","tool",ProficiencyLevel.INTERMEDIATE),
        ("MongoDB","tool",ProficiencyLevel.INTERMEDIATE),
        ("Redis","tool",ProficiencyLevel.INTERMEDIATE),
        ("Elasticsearch","tool",ProficiencyLevel.INTERMEDIATE),
        ("Tableau","tool",ProficiencyLevel.INTERMEDIATE),
        ("Power BI","tool",ProficiencyLevel.INTERMEDIATE),
        ("Machine Learning","ml_ai",ProficiencyLevel.INTERMEDIATE),
        ("Deep Learning","ml_ai",ProficiencyLevel.INTERMEDIATE),
        ("NLP","ml_ai",ProficiencyLevel.INTERMEDIATE),
        ("Natural Language Processing","ml_ai",ProficiencyLevel.INTERMEDIATE),
        ("Computer Vision","ml_ai",ProficiencyLevel.INTERMEDIATE),
        ("MLOps","ml_ai",ProficiencyLevel.INTERMEDIATE),
        ("LLM","ml_ai",ProficiencyLevel.INTERMEDIATE),
        ("RAG","ml_ai",ProficiencyLevel.INTERMEDIATE),
        ("Prompt Engineering","ml_ai",ProficiencyLevel.INTERMEDIATE),
        ("Fine-tuning","ml_ai",ProficiencyLevel.INTERMEDIATE),
        ("Reinforcement Learning","ml_ai",ProficiencyLevel.INTERMEDIATE),
        ("Agile","methodology",ProficiencyLevel.INTERMEDIATE),
        ("Scrum","methodology",ProficiencyLevel.INTERMEDIATE),
        ("CI/CD","methodology",ProficiencyLevel.INTERMEDIATE),
        ("DevOps","methodology",ProficiencyLevel.INTERMEDIATE),
        ("REST APIs","methodology",ProficiencyLevel.INTERMEDIATE),
        ("Microservices","methodology",ProficiencyLevel.INTERMEDIATE),
        ("ETL Pipelines","domain_knowledge",ProficiencyLevel.INTERMEDIATE),
        ("Data Engineering","domain_knowledge",ProficiencyLevel.INTERMEDIATE),
        ("Statistics","domain_knowledge",ProficiencyLevel.INTERMEDIATE),
        ("Data Analysis","domain_knowledge",ProficiencyLevel.INTERMEDIATE),
        ("Data Science","domain_knowledge",ProficiencyLevel.INTERMEDIATE),
        ("A/B Testing","domain_knowledge",ProficiencyLevel.INTERMEDIATE),
        ("Communication","soft_skill",ProficiencyLevel.INTERMEDIATE),
        ("Project Management","soft_skill",ProficiencyLevel.INTERMEDIATE),
        ("Leadership","soft_skill",ProficiencyLevel.INTERMEDIATE),
        ("Teamwork","soft_skill",ProficiencyLevel.INTERMEDIATE),
        ("Problem Solving","soft_skill",ProficiencyLevel.INTERMEDIATE),
    ]

    # For JDs detect required vs preferred per sentence
    required_lower  = set()
    preferred_lower = set()
    if source_label == "job description":
        for sent in _split_sentences(text):
            priority   = _sentence_priority(sent)
            sent_lower = sent.lower()
            for name, _, _ in skill_map:
                if name.lower() in sent_lower:
                    if priority == "required":
                        required_lower.add(name.lower())
                    elif priority == "preferred":
                        preferred_lower.add(name.lower())

    results = []
    for name, category, proficiency in skill_map:
        if name.lower() not in text_lower:
            continue
        n = name.lower()
        confidence = 0.95 if n in required_lower else 0.78 if n in preferred_lower else 0.82
        results.append(Skill(
            name=name,
            category=category,
            proficiency=proficiency,
            confidence_score=confidence,
        ))
    return results