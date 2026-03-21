from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum


class ProficiencyLevel(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class Skill(BaseModel):
    name: str
    category: str
    proficiency: Optional[ProficiencyLevel] = None
    years_experience: Optional[float] = None
    confidence_score: float = Field(ge=0.0, le=1.0)


class ExtractRequest(BaseModel):
    job_description: str
    resume_text: Optional[str] = None  # fallback if PDF parse is done client-side


class ExtractResponse(BaseModel):
    candidate_skills: List[Skill]
    required_skills: List[Skill]
    reasoning_trace: List[str]


class SkillGap(BaseModel):
    skill_name: str
    category: str
    required_proficiency: ProficiencyLevel
    candidate_proficiency: Optional[ProficiencyLevel]
    gap_score: float = Field(ge=0.0, le=1.0, description="1.0 = completely missing, 0.0 = fully met")
    priority: str  # "high" | "medium" | "low"


class GapRequest(BaseModel):
    candidate_skills: List[Skill]
    required_skills: List[Skill]


class GapResponse(BaseModel):
    gaps: List[SkillGap]
    coverage_percent: float
    redundant_skills: List[str]
    reasoning_trace: List[str]


class Course(BaseModel):
    id: str
    title: str
    description: str
    skills_taught: List[str]
    prerequisites: List[str]  # list of course IDs
    duration_hours: float
    difficulty: ProficiencyLevel
    provider: str
    url: Optional[str] = None
    tags: List[str] = []


class LearningStep(BaseModel):
    order: int
    course: Course
    addresses_gaps: List[str]  # skill names this course resolves
    rationale: str


class PathwayRequest(BaseModel):
    gaps: List[SkillGap]
    candidate_skills: List[Skill]
    role_title: Optional[str] = None


class PathwayResponse(BaseModel):
    role_title: Optional[str]
    total_hours: float
    steps: List[LearningStep]
    skipped_courses: List[str]  # courses skipped because candidate already has the skill
    estimated_redundancy_saved_hours: float
    reasoning_trace: List[str]


class FullAnalysisRequest(BaseModel):
    job_description: str
    resume_text: str
    role_title: Optional[str] = None


class FullAnalysisResponse(BaseModel):
    extract: ExtractResponse
    gap: GapResponse
    pathway: PathwayResponse
