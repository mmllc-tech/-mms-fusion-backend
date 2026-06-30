"""
Discovery — file upload, text extraction, AI extraction via Claude API
Supports: XLSX, DOCX, PDF, TXT, CSV
"""
import os, json, io, re
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from app.models.database import get_db, Project, UploadedFile
import httpx

router = APIRouter()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-6"

REQUIRED_QUESTIONS = [
    "legislation","enterprise","legal_entity","ldg",
    "payroll_freq","salary_basis","elements",
    "worker_types","positions","modules_enabled","security"
]

EXTRACTION_PROMPT = """You are an expert Oracle HCM Core HR implementation consultant.

Read these discovery documents and extract answers to the following Oracle HCM implementation questions.
Return ONLY a valid JSON object with the question IDs as keys.
Only include questions where you found clear evidence — do not guess or invent.

Questions to answer:
- "legislation": Country and legislation (e.g. United States, US Legislation, USD)
- "enterprise": Enterprise / company name in Oracle HCM
- "legal_entity": Legal Entities and Legal Employers in scope, with EIN numbers if found
- "ldg": Legislative Data Group name (e.g. US Legislative Data Group)
- "bus_units": Business Units in scope
- "payroll_freq": Payroll frequency (Biweekly, Monthly, Semimonthly etc)
- "salary_basis": Salary bases required (Annual, Hourly, annualization factors)
- "elements": Earning elements in scope for conversion
- "payroll_int": Payroll interface or integration requirements
- "worker_types": Worker types in scope (Employee, Contingent Worker etc)
- "positions": Whether Position
