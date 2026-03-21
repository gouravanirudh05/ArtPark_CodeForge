"""
Path Planner Service
--------------------
Algorithm:
  1. Load course catalog (source of truth — no hallucinated courses)
  2. Semantic matching — embed course skills + gap skills with Sentence-BERT,
     match via cosine similarity instead of exact string lookup
  3. Build a prerequisite DAG (directed acyclic graph) over filtered courses
  4. Topological sort (Kahn's algorithm) to determine safe learning order
  5. Skip courses whose skills the candidate already has → saves hours
  6. Attach per-step rationale for the reasoning trace
"""

import json
from collections import deque
from pathlib import Path
from typing import List, Tuple, Dict, Set

import numpy as np

from app.models.schemas import (
    Course, LearningStep, SkillGap, Skill, ProficiencyLevel
)
from app.services.reasoning_trace import ReasoningTrace

CATALOG_PATH = Path("/app/data/course_catalog.json")

# Similarity threshold — course skill must be at least this similar
# to a gap skill to count as "addressing" it
SEMANTIC_THRESHOLD = 0.60

# Lazy-loaded embedder (shared with gap_analyzer)
_embedder = None

def _get_embedder():
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedder


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def _load_catalog() -> List[Course]:
    if not CATALOG_PATH.exists():
        return []
    raw = json.loads(CATALOG_PATH.read_text())
    return [Course(**c) for c in raw]


def _semantic_course_relevance(
    course: Course,
    gaps: List[SkillGap],
    gap_embeddings: np.ndarray,
    gap_names: List[str],
) -> List[str]:
    """
    For each skill a course teaches, find the most semantically similar
    gap skill. If similarity >= SEMANTIC_THRESHOLD, the course addresses
    that gap. Returns list of matched gap skill names.
    """
    if not course.skills_taught or not gaps:
        return []

    embedder          = _get_embedder()
    course_embeddings = embedder.encode(course.skills_taught, normalize_embeddings=True)

    addressed = []
    for ci, course_skill_emb in enumerate(course_embeddings):
        best_sim = 0.0
        best_gap = None
        for gi, gap_emb in enumerate(gap_embeddings):
            sim = _cosine_sim(course_skill_emb, gap_emb)
            if sim > best_sim:
                best_sim = sim
                best_gap = gap_names[gi]

        if best_sim >= SEMANTIC_THRESHOLD and best_gap:
            addressed.append(best_gap)

    # Deduplicate — multiple course skills may match the same gap
    return list(dict.fromkeys(addressed))


def _candidate_covers_course_semantically(
    course: Course,
    candidate_embeddings: np.ndarray,
    candidate_names: List[str],
    threshold: float = 0.75,
) -> bool:
    """
    Returns True if every skill taught by the course is semantically
    covered by at least one candidate skill above the threshold.
    """
    if not course.skills_taught or candidate_embeddings is None or len(candidate_embeddings) == 0:
        return False

    embedder          = _get_embedder()
    course_embeddings = embedder.encode(course.skills_taught, normalize_embeddings=True)

    for course_skill_emb in course_embeddings:
        best_sim = max(
            _cosine_sim(course_skill_emb, cand_emb)
            for cand_emb in candidate_embeddings
        )
        if best_sim < threshold:
            return False

    return True


def _topological_sort(courses: List[Course]) -> List[Course]:
    """Kahn's algorithm — courses with no prerequisites come first."""
    id_to_course = {c.id: c for c in courses}
    in_degree: Dict[str, int] = {c.id: 0 for c in courses}
    adj: Dict[str, List[str]] = {c.id: [] for c in courses}

    for course in courses:
        for prereq_id in course.prerequisites:
            if prereq_id in id_to_course:
                adj[prereq_id].append(course.id)
                in_degree[course.id] += 1

    queue      = deque([c.id for c in courses if in_degree[c.id] == 0])
    sorted_ids: List[str] = []

    while queue:
        cid = queue.popleft()
        sorted_ids.append(cid)
        for neighbour in adj.get(cid, []):
            in_degree[neighbour] -= 1
            if in_degree[neighbour] == 0:
                queue.append(neighbour)

    remaining = [c.id for c in courses if c.id not in sorted_ids]
    sorted_ids.extend(remaining)

    return [id_to_course[cid] for cid in sorted_ids if cid in id_to_course]


async def generate_pathway(
    gaps: List[SkillGap],
    candidate_skills: List[Skill],
    role_title: str | None = None,
) -> Tuple[List[LearningStep], float, List[str], float, List[str]]:
    """
    Returns (steps, total_hours, skipped_course_titles, redundancy_saved_hours, trace_steps).
    """
    trace   = ReasoningTrace("PathPlanner")
    catalog = _load_catalog()
    trace.log(f"Loaded course catalog: {len(catalog)} courses available")

    if not catalog:
        trace.log("WARNING: course_catalog.json not found or empty — returning empty pathway")
        return [], 0.0, [], 0.0, trace.all()

    embedder = _get_embedder()

    # Pre-compute gap skill embeddings
    gap_names      = [g.skill_name for g in gaps]
    gap_embeddings = embedder.encode(gap_names, normalize_embeddings=True) if gaps else np.array([])
    trace.log(f"Encoded {len(gap_names)} gap embeddings (threshold={SEMANTIC_THRESHOLD})")

    # Pre-compute candidate skill embeddings
    cand_names      = [s.name for s in candidate_skills]
    cand_embeddings = (
        embedder.encode(cand_names, normalize_embeddings=True)
        if candidate_skills else np.array([])
    )
    trace.log(f"Encoded {len(cand_names)} candidate embeddings for skip detection")

    high_priority_gaps = {g.skill_name for g in gaps if g.gap_score > 0.15}
    trace.log(f"Targeting {len(high_priority_gaps)} skill gaps with score > 0.15")

    relevant:       List[Tuple[Course, List[str]]] = []
    skipped_titles: List[str] = []
    saved_hours = 0.0

    for course in catalog:
        addressed = _semantic_course_relevance(
            course, gaps, gap_embeddings, gap_names
        )
        if not addressed:
            continue

        already_covered = _candidate_covers_course_semantically(
            course, cand_embeddings, cand_names
        )
        if already_covered:
            skipped_titles.append(course.title)
            saved_hours += course.duration_hours
            trace.log(
                f"Skipping '{course.title}' — semantically covered by candidate "
                f"(saves {course.duration_hours}h)"
            )
            continue

        relevant.append((course, addressed))

    trace.log(
        f"{len(relevant)} courses selected after semantic filtering; "
        f"{len(skipped_titles)} skipped"
    )

    relevant.sort(key=lambda x: len(x[1]), reverse=True)
    sorted_courses = _topological_sort([c for c, _ in relevant])
    trace.log("Applied Kahn's topological sort respecting prerequisites")

    course_addressed_map = {c.id: addr for c, addr in relevant}
    steps:      List[LearningStep] = []
    total_hours = 0.0

    for order, course in enumerate(sorted_courses, start=1):
        addressed = course_addressed_map.get(course.id, [])
        rationale = (
            f"Addresses: {', '.join(addressed)} "
            f"(semantic similarity ≥ {SEMANTIC_THRESHOLD}). "
            f"Difficulty: {course.difficulty}. "
        )
        if course.prerequisites:
            rationale += f"Prerequisites: {', '.join(course.prerequisites)}."

        steps.append(LearningStep(
            order=order,
            course=course,
            addresses_gaps=addressed,
            rationale=rationale,
        ))
        total_hours += course.duration_hours

    trace.log(
        f"Generated {len(steps)}-step pathway — {total_hours}h total; "
        f"saved {saved_hours}h by skipping covered courses"
    )

    return steps, total_hours, skipped_titles, saved_hours, trace.all()