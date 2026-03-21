"""
Gap Analyzer Service
--------------------
Pipeline:
  1. Sentence-BERT embeds both candidate and required skill sets
  2. Cosine similarity matching — each required skill is matched to its
     closest candidate skill (handles synonyms / paraphrases)
  3. Gap scoring — similarity < threshold → gap, scored by distance
  4. Priority classification — high/medium/low based on gap score
"""

from typing import List, Tuple, Dict
import numpy as np

from app.models.schemas import Skill, SkillGap, ProficiencyLevel
from app.services.reasoning_trace import ReasoningTrace

PROFICIENCY_ORDER = {
    ProficiencyLevel.BEGINNER: 1,
    ProficiencyLevel.INTERMEDIATE: 2,
    ProficiencyLevel.ADVANCED: 3,
    ProficiencyLevel.EXPERT: 4,
}

SIMILARITY_THRESHOLD = 0.72  # below this → treat as a gap

# Lazy-load the embedding model to avoid startup delay
_embedder = None

def _get_embedder():
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedder


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def _proficiency_gap(required: ProficiencyLevel, candidate: ProficiencyLevel | None) -> float:
    """
    Returns a 0-1 gap score based on proficiency levels.
    0.0 = candidate meets or exceeds required, 1.0 = no proficiency at all.
    """
    if candidate is None:
        return 0.5  # skill exists but level unknown
    req_val = PROFICIENCY_ORDER[required]
    cand_val = PROFICIENCY_ORDER[candidate]
    if cand_val >= req_val:
        return 0.0
    return (req_val - cand_val) / 3.0  # max gap = 3 levels = 1.0


def _priority(gap_score: float) -> str:
    if gap_score >= 0.7:
        return "high"
    if gap_score >= 0.35:
        return "medium"
    return "low"


async def analyze_gap(
    candidate_skills: List[Skill],
    required_skills: List[Skill],
) -> Tuple[List[SkillGap], float, List[str], List[str]]:
    """
    Returns (gaps, coverage_percent, redundant_skill_names, trace_steps).
    """
    trace = ReasoningTrace("GapAnalyzer")
    trace.log(f"Candidate has {len(candidate_skills)} skills; role requires {len(required_skills)}")

    embedder = _get_embedder()
    trace.log("Loaded Sentence-BERT (all-MiniLM-L6-v2) for semantic skill matching")

    cand_names = [s.name for s in candidate_skills]
    req_names  = [s.name for s in required_skills]

    cand_embeddings = embedder.encode(cand_names, normalize_embeddings=True)
    req_embeddings  = embedder.encode(req_names,  normalize_embeddings=True)
    trace.log(f"Encoded {len(cand_names)} candidate + {len(req_names)} required skill embeddings")

    gaps: List[SkillGap] = []
    matched_candidate_indices = set()

    for i, req_skill in enumerate(required_skills):
        # Find best matching candidate skill by cosine similarity
        sims = [_cosine_similarity(req_embeddings[i], cand_embeddings[j])
                for j in range(len(cand_embeddings))]

        if sims:
            best_idx = int(np.argmax(sims))
            best_sim = sims[best_idx]
        else:
            best_idx, best_sim = -1, 0.0

        if best_sim >= SIMILARITY_THRESHOLD:
            # Skill semantically matched — check proficiency gap
            matched_candidate_indices.add(best_idx)
            cand_skill = candidate_skills[best_idx]
            prof_gap = _proficiency_gap(req_skill.proficiency or ProficiencyLevel.INTERMEDIATE,
                                         cand_skill.proficiency)
            gap_score = prof_gap * (1.0 - best_sim + 0.3)  # blend similarity + proficiency
            gap_score = min(gap_score, 1.0)

            if gap_score > 0.05:  # small non-zero gap still worth logging
                gaps.append(SkillGap(
                    skill_name=req_skill.name,
                    category=req_skill.category,
                    required_proficiency=req_skill.proficiency or ProficiencyLevel.INTERMEDIATE,
                    candidate_proficiency=cand_skill.proficiency,
                    gap_score=round(gap_score, 3),
                    priority=_priority(gap_score),
                ))
                trace.log(f"Partial gap — '{req_skill.name}' matched '{cand_skill.name}' "
                          f"(sim={best_sim:.2f}), proficiency gap={prof_gap:.2f}")
        else:
            # Skill completely missing
            gaps.append(SkillGap(
                skill_name=req_skill.name,
                category=req_skill.category,
                required_proficiency=req_skill.proficiency or ProficiencyLevel.INTERMEDIATE,
                candidate_proficiency=None,
                gap_score=round(1.0 - best_sim, 3),
                priority=_priority(1.0 - best_sim),
            ))
            trace.log(f"Missing skill — '{req_skill.name}' (best match sim={best_sim:.2f})")

    # Redundant skills: candidate skills not matched to any requirement
    redundant = [cand_names[j] for j in range(len(candidate_skills))
                 if j not in matched_candidate_indices]
    trace.log(f"Identified {len(redundant)} redundant/non-required skills in candidate profile")

    covered = len(required_skills) - len([g for g in gaps if g.gap_score > 0.5])
    coverage_pct = round((covered / max(len(required_skills), 1)) * 100, 1)
    trace.log(f"Coverage: {coverage_pct}% of required skills already met")

    return gaps, coverage_pct, redundant, trace.all()
