"""
MMS Fusion AI Accelerator — FastAPI Backend v2.0
Complete Oracle HCM Core HR Implementation Automation
"""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import projects, discovery, templates, hdl, oracle, evidence
from app.models.database import init_db

app = FastAPI(
    title="MMS Fusion AI Accelerator",
    description="Oracle HCM Core HR Implementation Automation — Modern Mind Solutions LLC",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    init_db()

app.include_router(projects.router,  prefix="/api/projects",  tags=["Projects"])
app.include_router(discovery.router, prefix="/api/discovery", tags=["Discovery"])
app.include_router(templates.router, prefix="/api/templates", tags=["Templates"])
app.include_router(hdl.router,       prefix="/api/hdl",       tags=["HDL"])
app.include_router(oracle.router,    prefix="/api/oracle",    tags=["Oracle"])
app.include_router(evidence.router,  prefix="/api/evidence",  tags=["Evidence"])

@app.get("/")
def root():
    return {
        "product": "MMS Fusion AI Accelerator",
        "company": "Modern Mind Solutions LLC",
        "version": "2.0.0",
        "status": "running",
        "docs": "/docs"
    }

@app.get("/health")
def health():
    return {"status": "healthy"}
