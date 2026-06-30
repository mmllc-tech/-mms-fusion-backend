"""
Database — PostgreSQL via Supabase in production, SQLite for local dev
"""
import os, json
from datetime import datetime
from sqlalchemy import (create_engine, Column, String, Integer, Text,
                        DateTime, Boolean, JSON)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./mms_fusion.db"
)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    pool_pre_ping=True
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class Project(Base):
    __tablename__ = "projects"
    id          = Column(String, primary_key=True)
    name        = Column(String, nullable=False)
    industry    = Column(String, default="")
    impl_type   = Column(String, default="")
    golive      = Column(String, default="")
    consultant  = Column(String, default="")
    modules     = Column(Text, default="[]")
    status      = Column(String, default="new")
    completion  = Column(Integer, default=0)
    answers     = Column(Text, default="{}")
    missing     = Column(Text, default="[]")
    has_files   = Column(Boolean, default=False)
    file_names  = Column(Text, default="[]")
    created_at  = Column(DateTime, default=datetime.utcnow)
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class UploadedFile(Base):
    __tablename__ = "uploaded_files"
    id             = Column(Integer, primary_key=True, autoincrement=True)
    project_id     = Column(String, nullable=False)
    file_name      = Column(String, nullable=False)
    file_type      = Column(String, default="")
    extracted_text = Column(Text, default="")
    uploaded_at    = Column(DateTime, default=datetime.utcnow)

class LoadRun(Base):
    __tablename__ = "load_runs"
    id                = Column(Integer, primary_key=True, autoincrement=True)
    project_id        = Column(String, nullable=False)
    object_name       = Column(String, nullable=False)
    method            = Column(String, default="HDL")
    sequence          = Column(Integer, default=0)
    status            = Column(String, default="queued")
    hdl_file_name     = Column(String, default="")
    oracle_process_id = Column(String, default="")
    error_count       = Column(Integer, default=0)
    warning_count     = Column(Integer, default=0)
    log_text          = Column(Text, default="")
    started_at        = Column(DateTime)
    completed_at      = Column(DateTime)
    created_at        = Column(DateTime, default=datetime.utcnow)

class HdlFile(Base):
    __tablename__ = "hdl_files"
    id           = Column(Integer, primary_key=True, autoincrement=True)
    project_id   = Column(String, nullable=False)
    object_name  = Column(String, nullable=False)
    file_name    = Column(String, nullable=False)
    file_content = Column(Text, nullable=False)
    row_count    = Column(Integer, default=0)
    sequence     = Column(Integer, default=0)
    created_at   = Column(DateTime, default=datetime.utcnow)

class RpaTask(Base):
    __tablename__ = "rpa_tasks"
    id             = Column(Integer, primary_key=True, autoincrement=True)
    project_id     = Column(String, nullable=False)
    task_name      = Column(String, nullable=False)
    oracle_path    = Column(String, default="")
    status         = Column(String, default="pending")
    screenshot_url = Column(String, default="")
    error_message  = Column(Text, default="")
    started_at     = Column(DateTime)
    completed_at   = Column(DateTime)
    created_at     = Column(DateTime, default=datetime.utcnow)

class Evidence(Base):
    __tablename__ = "evidence"
    id            = Column(Integer, primary_key=True, autoincrement=True)
    project_id    = Column(String, nullable=False)
    evidence_type = Column(String, default="")
    file_name     = Column(String, default="")
    file_path     = Column(String, default="")
    notes         = Column(Text, default="")
    created_at    = Column(DateTime, default=datetime.utcnow)

def init_db():
    Base.metadata.create_all(bind=engine)
    print("Database tables ready")
