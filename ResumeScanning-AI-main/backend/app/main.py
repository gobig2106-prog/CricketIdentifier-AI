import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .core.config import get_settings
from .db import SessionLocal, init_db
from .models import Screening
from .schemas import HealthResponse, ScreeningResponse, ScreeningSummary
from .services.matcher import WEIGHTS, normalized_weights, rank_candidates
from .services.parser import extract_job_requirements, extract_text, parse_resume

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("signalboard")
settings = get_settings()

app = FastAPI(title=settings.app_name, version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
app.mount("/assets", StaticFiles(directory=FRONTEND_DIR), name="assets")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/api/health", response_model=HealthResponse)
def health():
    return {"status": "ok", "app": settings.app_name, "database": "configured"}


class JobAnalysisRequest(BaseModel):
    text: str


@app.post("/api/analyze-job")
def analyze_job(payload: JobAnalysisRequest):
    if len(payload.text.strip()) < 20:
        raise HTTPException(status_code=400, detail="Add at least a sentence or two about the role.")
    return extract_job_requirements(payload.text)


def _demo_payload() -> dict:
    job = (
        "Senior Python Engineer. Required: Python, FastAPI, SQL, REST API, Git. "
        "Preferred: Docker, AWS, React, Machine Learning. 4+ years experience. "
        "Bachelor's degree in Computer Science or related field."
    )
    requirements = extract_job_requirements(job)
    raw_candidates = [
        {
            "name": "Maya Chen",
            "email": "maya.chen@example.com",
            "phone": "+1 415 555 0198",
            "skills": ["aws", "docker", "fastapi", "git", "machine learning", "pandas", "python", "sql"],
            "education": ["Bachelor", "Computer Science"],
            "experience_years": 6.0,
            "certifications": ["AWS Certified Developer"],
            "filename": "maya-chen-resume.pdf",
            "raw_text": "Maya Chen Python FastAPI SQL REST API Git Docker AWS Machine Learning. 6 years experience. Bachelor Computer Science.",
        },
        {
            "name": "Arjun Rao",
            "email": "arjun.rao@example.com",
            "phone": "+91 98765 43210",
            "skills": ["fastapi", "git", "javascript", "python", "react", "rest api", "sql"],
            "education": ["Mca", "Computer Science"],
            "experience_years": 4.0,
            "certifications": [],
            "filename": "arjun-rao-resume.docx",
            "raw_text": "Arjun Rao Python FastAPI SQL REST API Git React JavaScript. 4 years experience. MCA Computer Science.",
        },
        {
            "name": "Noah Williams",
            "email": "noah.williams@example.com",
            "phone": "",
            "skills": ["django", "git", "python", "sql"],
            "education": ["Bachelor"],
            "experience_years": 3.0,
            "certifications": [],
            "filename": "noah-williams-resume.pdf",
            "raw_text": "Noah Williams Python Django SQL Git. 3 years experience. Bachelor's degree.",
        },
        {
            "name": "Priya Nair",
            "email": "priya.nair@example.com",
            "phone": "+91 90000 12345",
            "skills": ["aws", "machine learning", "pandas", "python", "scikit-learn", "sql"],
            "education": ["Master", "Computer Science"],
            "experience_years": 5.0,
            "certifications": ["Machine Learning Specialization"],
            "filename": "priya-nair-resume.pdf",
            "raw_text": "Priya Nair Python SQL AWS Machine Learning Pandas Scikit-learn. 5 years experience. Master's in Computer Science.",
        },
    ]
    requirements["scoring_weights"] = normalized_weights(WEIGHTS)
    candidates = rank_candidates(job, requirements, raw_candidates, WEIGHTS)
    return {
        "id": 0,
        "title": "Senior Python Engineer",
        "job_description": job,
        "requirements": requirements,
        "candidates": candidates,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/demo", response_model=ScreeningResponse)
def demo():
    return _demo_payload()


@app.post("/api/screenings", response_model=ScreeningResponse, status_code=201)
async def create_screening(
    job_description: Annotated[str, Form(...)],
    resumes: Annotated[list[UploadFile], File(...)],
    weights_json: Annotated[str, Form()] = "{}",
    db: Session = Depends(get_db),
):
    if len(job_description.strip()) < 30:
        raise HTTPException(status_code=400, detail="Add a fuller job description before screening.")
    if not resumes:
        raise HTTPException(status_code=400, detail="Upload at least one resume.")

    try:
        requested_weights: dict[str, Any] = json.loads(weights_json or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Scoring weights must be valid JSON.") from exc
    active_weights = normalized_weights(requested_weights)
    candidates = []
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    for uploaded in resumes:
        extension = Path(uploaded.filename or "").suffix.lower().lstrip(".")
        if extension not in settings.allowed_extension_set:
            raise HTTPException(status_code=415, detail=f"{uploaded.filename}: use PDF, DOCX or TXT.")
        content = await uploaded.read()
        if len(content) > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"{uploaded.filename}: file exceeds {settings.max_upload_size_mb} MB.",
            )
        try:
            text = extract_text(uploaded.filename or "resume.txt", content)
        except Exception as exc:
            logger.warning("Resume extraction failed for %s: %s", uploaded.filename, exc)
            raise HTTPException(status_code=422, detail=f"Could not read {uploaded.filename}.") from exc
        if len(text) < 20:
            raise HTTPException(status_code=422, detail=f"{uploaded.filename}: no readable resume text found.")
        candidates.append(parse_resume(uploaded.filename or "resume", text))

    requirements = extract_job_requirements(job_description)
    requirements["scoring_weights"] = active_weights
    ranked = rank_candidates(job_description, requirements, candidates, active_weights)
    title = next((line.strip() for line in job_description.splitlines() if line.strip()), "New screening")[:180]
    record = Screening(
        title=title,
        job_description=job_description,
        requirements_json=json.dumps(requirements),
        candidates_json=json.dumps(ranked),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    logger.info("Screening completed: id=%s candidates=%s", record.id, len(ranked))
    return _serialize(record)


def _serialize(record: Screening) -> dict:
    return {
        "id": record.id,
        "title": record.title,
        "job_description": record.job_description,
        "requirements": json.loads(record.requirements_json),
        "candidates": json.loads(record.candidates_json),
        "created_at": record.created_at,
    }


@app.get("/api/screenings", response_model=list[ScreeningSummary])
def list_screenings(db: Session = Depends(get_db)):
    records = db.query(Screening).order_by(Screening.created_at.desc()).limit(20).all()
    return [
        {
            "id": record.id,
            "title": record.title,
            "candidate_count": len(json.loads(record.candidates_json)),
            "top_score": max((candidate["score"] for candidate in json.loads(record.candidates_json)), default=0),
            "created_at": record.created_at,
        }
        for record in records
    ]


@app.get("/api/screenings/{screening_id}", response_model=ScreeningResponse)
def get_screening(screening_id: int, db: Session = Depends(get_db)):
    record = db.get(Screening, screening_id)
    if not record:
        raise HTTPException(status_code=404, detail="Screening not found.")
    return _serialize(record)


@app.delete("/api/screenings/{screening_id}", status_code=204)
def delete_screening(screening_id: int, db: Session = Depends(get_db)):
    record = db.get(Screening, screening_id)
    if not record:
        raise HTTPException(status_code=404, detail="Screening not found.")
    db.delete(record)
    db.commit()
