"""
FastAPI Application Entry Point
"""

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import pdfplumber
import io

from app.models.schemas import (
    ExtractRequest, ExtractResponse,
    GapRequest, GapResponse,
    PathwayRequest, PathwayResponse,
    FullAnalysisRequest, FullAnalysisResponse,
)
from app.services.skill_extractor import extract_skills
from app.services.gap_analyzer import analyze_gap
from app.services.path_planner import generate_pathway

app = FastAPI(
    title="Adaptive Onboarding Engine",
    description="AI-driven personalized learning pathway generator",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# /extract  — parse resume + JD into skill lists
# ---------------------------------------------------------------------------

@app.post("/extract", response_model=ExtractResponse)
async def extract(
    resume: UploadFile = File(...),
    job_description: str = Form(...),
):
    # Parse PDF resume
    try:
        pdf_bytes = await resume.read()
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            resume_text = "\n".join(
                page.extract_text() or "" for page in pdf.pages
            )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse resume PDF: {e}")

    candidate_skills, cand_trace = await extract_skills(resume_text, "resume")
    required_skills, req_trace = await extract_skills(job_description, "job description")

    return ExtractResponse(
        candidate_skills=candidate_skills,
        required_skills=required_skills,
        reasoning_trace=cand_trace + req_trace,
    )


# ---------------------------------------------------------------------------
# /gap  — compute skill gap between candidate and role
# ---------------------------------------------------------------------------

@app.post("/gap", response_model=GapResponse)
async def gap(request: GapRequest):
    gaps, coverage_pct, redundant, trace = await analyze_gap(
        request.candidate_skills,
        request.required_skills,
    )
    return GapResponse(
        gaps=gaps,
        coverage_percent=coverage_pct,
        redundant_skills=redundant,
        reasoning_trace=trace,
    )


# ---------------------------------------------------------------------------
# /pathway  — generate personalized learning pathway
# ---------------------------------------------------------------------------

@app.post("/pathway", response_model=PathwayResponse)
async def pathway(request: PathwayRequest):
    steps, total_hours, skipped, saved, trace = await generate_pathway(
        request.gaps,
        request.candidate_skills,
        request.role_title,
    )
    return PathwayResponse(
        role_title=request.role_title,
        total_hours=total_hours,
        steps=steps,
        skipped_courses=skipped,
        estimated_redundancy_saved_hours=saved,
        reasoning_trace=trace,
    )


# ---------------------------------------------------------------------------
# /analyze  — full pipeline in one request (used by the React UI)
# ---------------------------------------------------------------------------

@app.post("/analyze", response_model=FullAnalysisResponse)
async def analyze(
    resume: UploadFile = File(...),
    job_description: str = Form(...),
    role_title: str = Form(default=""),
):
    # Parse PDF
    try:
        pdf_bytes = await resume.read()
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            resume_text = "\n".join(
                page.extract_text() or "" for page in pdf.pages
            )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse resume PDF: {e}")
    
    print(resume_text)

    # Stage 1: Extract
    candidate_skills, cand_trace = await extract_skills(resume_text, "resume")
    required_skills, req_trace   = await extract_skills(job_description, "job description")

    # Stage 2: Gap analysis
    gaps, coverage_pct, redundant, gap_trace = await analyze_gap(
        candidate_skills, required_skills
    )

    # Stage 3: Pathway generation
    steps, total_hours, skipped, saved, path_trace = await generate_pathway(
        gaps, candidate_skills, role_title or None
    )

    return FullAnalysisResponse(
        extract=ExtractResponse(
            candidate_skills=candidate_skills,
            required_skills=required_skills,
            reasoning_trace=cand_trace + req_trace,
        ),
        gap=GapResponse(
            gaps=gaps,
            coverage_percent=coverage_pct,
            redundant_skills=redundant,
            reasoning_trace=gap_trace,
        ),
        pathway=PathwayResponse(
            role_title=role_title or None,
            total_hours=total_hours,
            steps=steps,
            skipped_courses=skipped,
            estimated_redundancy_saved_hours=saved,
            reasoning_trace=path_trace,
        ),
    )
