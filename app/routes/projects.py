"""Projects — create, list, get, update, delete"""
import json, uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy.orm import Session
from app.models.database import get_db, Project, init_db

router = APIRouter()

REQUIRED_QUESTIONS = [
    "legislation","enterprise","legal_entity","ldg",
    "payroll_freq","salary_basis","elements",
    "worker_types","positions","modules_enabled","security"
]

def calc_completion(answers: dict, missing: list) -> int:
    answered = [q for q in REQUIRED_QUESTIONS if answers.get(q)]
    return round((len(answered) / len(REQUIRED_QUESTIONS)) * 100)

def get_missing(answers: dict) -> list:
    return [q for q in REQUIRED_QUESTIONS if not answers.get(q)]

class ProjectCreate(BaseModel):
    name: str
    industry: Optional[str] = ""
    impl_type: Optional[str] = ""
    golive: Optional[str] = ""
    consultant: Optional[str] = ""
    modules: Optional[List[str]] = []

class ProjectUpdate(BaseModel):
    answers: Optional[dict] = None
    status: Optional[str] = None

def project_to_out(p: Project) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "industry": p.industry,
        "impl_type": p.impl_type,
        "golive": p.golive,
        "consultant": p.consultant,
        "modules": json.loads(p.modules or "[]"),
        "status": p.status,
        "completion": p.completion,
        "answers": json.loads(p.answers or "{}"),
        "missing": json.loads(p.missing or "[]"),
        "has_files": p.has_files,
        "file_names": json.loads(p.file_names or "[]"),
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }

@router.on_event("startup")
def startup():
    init_db()

@router.get("/")
def list_projects(db: Session = Depends(get_db)):
    projects = db.query(Project).order_by(Project.updated_at.desc()).all()
    return [project_to_out(p) for p in projects]

@router.post("/")
def create_project(data: ProjectCreate, db: Session = Depends(get_db)):
    p = Project(
        id=str(uuid.uuid4()),
        name=data.name,
        industry=data.industry,
        impl_type=data.impl_type,
        golive=data.golive,
        consultant=data.consultant,
        modules=json.dumps(data.modules),
        answers="{}",
        missing=json.dumps(REQUIRED_QUESTIONS),
        completion=0,
    )
    db.add(p); db.commit(); db.refresh(p)
    return project_to_out(p)

@router.get("/{project_id}")
def get_project(project_id: str, db: Session = Depends(get_db)):
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p: raise HTTPException(status_code=404, detail="Project not found")
    return project_to_out(p)

@router.patch("/{project_id}")
def update_project(project_id: str, data: ProjectUpdate, db: Session = Depends(get_db)):
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p: raise HTTPException(status_code=404, detail="Project not found")

    if data.answers is not None:
        existing = json.loads(p.answers or "{}")
        existing.update({k: v for k, v in data.answers.items() if v})
        p.answers = json.dumps(existing)
        p.missing = json.dumps(get_missing(existing))
        p.completion = calc_completion(existing, [])

    if data.status:
        p.status = data.status

    p.updated_at = datetime.utcnow()
    db.commit(); db.refresh(p)
    return project_to_out(p)

@router.delete("/{project_id}")
def delete_project(project_id: str, db: Session = Depends(get_db)):
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p: raise HTTPException(status_code=404, detail="Project not found")
    db.delete(p); db.commit()
    return {"deleted": project_id}
