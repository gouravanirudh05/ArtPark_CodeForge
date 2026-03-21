"""
Skill Extractor Service
-----------------------
Pipeline:
  1. spaCy NER pass — fast noun-phrase extraction to seed the LLM prompt
  2. Llama 3 structured extraction — returns JSON list of skills with
     category, proficiency level, and confidence score
  3. Deduplication against O*NET taxonomy for normalisation
"""

import json
import re
from pathlib import Path
from typing import List, Tuple

import spacy

from app.models.schemas import Skill, ProficiencyLevel
from app.services.llm_client import chat_json
from app.services.reasoning_trace import ReasoningTrace

# Load spaCy model once at import time (en_core_web_sm must be installed)
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    nlp = None  # graceful fallback — LLM-only mode

ONET_PATH = Path(__file__).parent.parent.parent.parent / "data" / "onet_skills.json"

def _load_onet_taxonomy() -> dict:
    if ONET_PATH.exists():
        return json.loads(ONET_PATH.read_text())
    return {}


ONET_TAXONOMY = _load_onet_taxonomy()

EXTRACT_SYSTEM = """You are a precise skill extraction engine for HR and talent management.
Extract technical and professional skills from the provided text.
Return a JSON array where each item has:
  - "name": canonical skill name (e.g. "Python", "Project Management", "SQL")
  - "category": one of ["programming_language", "framework", "tool", "domain_knowledge", "soft_skill", "certification", "methodology"]
  - "proficiency": one of ["beginner", "intermediate", "advanced", "expert"] or null if not mentioned
  - "years_experience": numeric or null
  - "confidence_score": 0.0-1.0 reflecting how clearly the skill is stated

Rules:
- Normalise synonyms (e.g. "JS" -> "JavaScript", "ML" -> "Machine Learning")
- Do NOT invent skills not present in the text
- Include soft skills only if explicitly mentioned
- Return ONLY the JSON array, nothing else"""


def _spacy_noun_phrases(text: str) -> List[str]:
    """Fast pre-pass: pull noun phrases as hints for the LLM."""
    if nlp is None:
        return []
    doc = nlp(text[:10000])  # cap to avoid timeout on huge docs
    return list({chunk.text.strip() for chunk in doc.noun_chunks if len(chunk.text.strip()) > 2})


async def extract_skills(text: str, source_label: str = "text") -> Tuple[List[Skill], List[str]]:
    """
    Extract skills from a block of text (resume or JD).
    Returns (skills_list, trace_steps).
    """
    trace = ReasoningTrace("SkillExtractor")
    trace.log(f"Received {source_label} ({len(text)} chars)")

    # Step 1: spaCy seed extraction
    noun_phrases = _spacy_noun_phrases(text)
    trace.log(f"spaCy extracted {len(noun_phrases)} noun phrases as extraction hints")

    hint_str = ""
    if noun_phrases:
        hint_str = f"\n\nKey noun phrases found by NLP pre-pass (use as hints): {', '.join(noun_phrases[:60])}"

    # Step 2: LLM structured extraction
    prompt = f"""Extract all skills from this {source_label}:

---
{text[:6000]}
---
{hint_str}

Return a JSON array of skill objects as specified."""

    trace.log("Sending to LLM for structured skill extraction")
    raw_skills = await chat_json(prompt, system=EXTRACT_SYSTEM)
    trace.log(f"LLM returned {len(raw_skills)} raw skill entries")

    # Step 3: Validate and normalise against O*NET
    skills: List[Skill] = []
    for item in raw_skills:
        try:
            # Normalise against O*NET if taxonomy is loaded
            name = item.get("name", "").strip()
            if ONET_TAXONOMY:
                # Simple alias lookup — O*NET JSON maps aliases to canonical names
                name = ONET_TAXONOMY.get("aliases", {}).get(name.lower(), name)

            skill = Skill(
                name=name,
                category=item.get("category", "domain_knowledge"),
                proficiency=item.get("proficiency"),
                years_experience=item.get("years_experience"),
                confidence_score=float(item.get("confidence_score", 0.7)),
            )
            skills.append(skill)
        except Exception as e:
            trace.log(f"Skipped malformed skill entry '{item.get('name', '?')}': {e}")

    trace.log(f"Validated {len(skills)} skills after normalisation")
    return skills, trace.all()
