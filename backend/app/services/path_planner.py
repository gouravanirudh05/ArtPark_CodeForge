"""
Path Planner Service
--------------------
Algorithm:
  1. Load course catalog (source of truth — no hallucinated courses)
  2. Filter to courses that address identified skill gaps
  3. Build a prerequisite DAG (directed acyclic graph) over filtered courses
  4. Topological sort (Kahn's algorithm) to determine safe learning order
  5. Skip courses whose skills the candidate already has → saves hours
  6. Attach per-step rationale for the reasoning trace
"""

import json
from collections import deque
from pathlib import Path
from typing import List, Tuple, Dict, Set

from app.models.schemas import (
    Course, LearningStep, SkillGap, Skill, ProficiencyLevel
)
from app.services.reasoning_trace import ReasoningTrace

CATALOG_PATH = Path("/app/data/course_catalog.json")


def _load_catalog() -> List[Course]:
    if not CATALOG_PATH.exists():
        return []
    raw = json.loads(CATALOG_PATH.read_text())
    return [Course(**c) for c in raw]


def _candidate_skill_names(candidate_skills: List[Skill]) -> Set[str]:
    return {s.name.lower() for s in candidate_skills}


def _course_relevance(course: Course, gaps: List[SkillGap]) -> List[str]:
    """Return list of gap skill names this course addresses."""
    gap_names = {g.skill_name.lower() for g in gaps}
    addressed = []
    for skill in course.skills_taught:
        if skill.lower() in gap_names:
            addressed.append(skill)
    return addressed


def _topological_sort(courses: List[Course]) -> List[Course]:
    """
    Kahn's algorithm for topological ordering respecting prerequisites.
    Courses with no prerequisites come first.
    """
    id_to_course = {c.id: c for c in courses}
    in_degree: Dict[str, int] = {c.id: 0 for c in courses}
    adj: Dict[str, List[str]] = {c.id: [] for c in courses}

    for course in courses:
        for prereq_id in course.prerequisites:
            if prereq_id in id_to_course:
                adj[prereq_id].append(course.id)
                in_degree[course.id] += 1

    queue = deque([c.id for c in courses if in_degree[c.id] == 0])
    sorted_ids: List[str] = []

    while queue:
        cid = queue.popleft()
        sorted_ids.append(cid)
        for neighbour in adj.get(cid, []):
            in_degree[neighbour] -= 1
            if in_degree[neighbour] == 0:
                queue.append(neighbour)

    # Any remaining nodes indicate a cycle — append them at end
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
    trace = ReasoningTrace("PathPlanner")
    catalog = _load_catalog()
    trace.log(f"Loaded course catalog: {len(catalog)} courses available")

    if not catalog:
        trace.log("WARNING: course_catalog.json not found or empty — returning empty pathway")
        return [], 0.0, [], 0.0, trace.all()

    candidate_known = _candidate_skill_names(candidate_skills)
    high_priority_gaps = {g.skill_name for g in gaps if g.gap_score > 0.15}
    trace.log(f"Targeting {len(high_priority_gaps)} skill gaps with score > 0.15")

    # Filter: only courses that address at least one gap
    relevant: List[Tuple[Course, List[str]]] = []
    skipped_titles: List[str] = []
    saved_hours = 0.0

    for course in catalog:
        addressed = _course_relevance(course, gaps)
        if not addressed:
            continue

        # Skip if ALL skills this course teaches are already known
        taught_lower = {s.lower() for s in course.skills_taught}
        already_known = taught_lower.issubset(candidate_known)
        if already_known:
            skipped_titles.append(course.title)
            saved_hours += course.duration_hours
            trace.log(f"Skipping '{course.title}' — candidate already has all taught skills "
                      f"(saves {course.duration_hours}h)")
            continue

        relevant.append((course, addressed))

    trace.log(f"{len(relevant)} courses selected after filtering; "
              f"{len(skipped_titles)} skipped (redundant)")

    # Sort by number of gaps addressed descending (greedy coverage), then topological sort
    relevant.sort(key=lambda x: len(x[1]), reverse=True)
    courses_to_sort = [c for c, _ in relevant]
    sorted_courses = _topological_sort(courses_to_sort)
    trace.log("Applied Kahn's topological sort respecting course prerequisites")

    # Build steps with rationale
    steps: List[LearningStep] = []
    total_hours = 0.0
    course_addressed_map = {c.id: addr for c, addr in relevant}

    for order, course in enumerate(sorted_courses, start=1):
        addressed = course_addressed_map.get(course.id, [])
        rationale = (
            f"This course addresses: {', '.join(addressed)}. "
            f"Difficulty ({course.difficulty}) aligns with identified gap priority. "
        )
        if course.prerequisites:
            rationale += f"Must follow prerequisite course(s): {', '.join(course.prerequisites)}."

        steps.append(LearningStep(
            order=order,
            course=course,
            addresses_gaps=addressed,
            rationale=rationale,
        ))
        total_hours += course.duration_hours

    trace.log(f"Generated {len(steps)}-step pathway — {total_hours}h total; "
              f"saved {saved_hours}h by skipping redundant courses")

    return steps, total_hours, skipped_titles, saved_hours, trace.all()
