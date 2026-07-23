"""
Discovery routes - file upload, text extraction, AI extraction via Claude API
"""
import os
import json
import io
import re
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from app.models.database import get_db, Project, UploadedFile
import httpx

router = APIRouter()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-6"

REQUIRED_QUESTIONS = [
    "legislation", "enterprise", "legal_entity", "ldg",
    "payroll_freq", "salary_basis", "elements",
    "worker_types", "positions", "modules_enabled", "security"
]

def get_extraction_prompt(content):
    return (
        "You are an expert Oracle HCM Core HR implementation consultant.\n"
        "Read these discovery documents and extract answers to the following questions.\n"
        "Return ONLY a valid JSON object. Only include questions where you found clear evidence.\n\n"
        "Questions to answer:\n"
        "- legislation: Country and legislation\n"
        "- enterprise: Enterprise/company name in Oracle HCM\n"
        "- legal_entity: Legal Entities in scope with EIN numbers\n"
        "- ldg: Legislative Data Group name\n"
        "- bus_units: Business Units in scope\n"
        "- payroll_freq: Payroll frequency\n"
        "- salary_basis: Salary bases required\n"
        "- elements: Earning elements in scope for conversion\n"
        "- payroll_int: Payroll interface requirements\n"
        "- worker_types: Worker types in scope\n"
        "- positions: Position Management scope\n"
        "- modules_enabled: Oracle modules enabled\n"
        "- security: Custom security roles required\n"
        "- dff: Descriptive Flexfield segments needed\n\n"
        "Documents:\n"
        + content[:45000]
        + "\n\nReturn only JSON: {\"legislation\": \"...\", \"enterprise\": \"...\", ...}"
    )

def extract_text_from_excel(content, filename):
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
        text = "Excel file: " + filename + "\nSheets: " + ", ".join(wb.sheetnames) + "\n\n"
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            sheet_text = "--- Sheet: " + sheet_name + " ---\n"
            for row in ws.iter_rows(values_only=True):
                row_vals = [str(v) if v is not None else "" for v in row]
                if any(v.strip() for v in row_vals):
                    sheet_text += " | ".join(row_vals) + "\n"
            text += sheet_text + "\n"
        return text[:50000]
    except Exception as e:
        return "Excel file: " + filename + " (parse error: " + str(e) + ")"

def extract_text_from_docx(content, filename):
    try:
        from docx import Document
        doc = Document(io.BytesIO(content))
        text = "Document: " + filename + "\n\n"
        for para in doc.paragraphs:
            if para.text.strip():
                text += para.text + "\n"
        for table in doc.tables:
            for row in table.rows:
                row_text = " | ".join(
                    cell.text.strip() for cell in row.cells if cell.text.strip()
                )
                if row_text:
                    text += row_text + "\n"
        return text[:50000]
    except Exception as e:
        return "Document: " + filename + " (parse error: " + str(e) + ")"

def extract_text_from_pdf(content, filename):
    try:
        import pdfplumber
        text = "PDF: " + filename + "\n\n"
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text[:50000]
    except Exception as e:
        return "PDF: " + filename + " (parse error: " + str(e) + ")"

def extract_text(content, filename):
    ext = filename.split(".")[-1].lower()
    if ext in ("xlsx", "xls"):
        return extract_text_from_excel(content, filename)
    elif ext == "docx":
        return extract_text_from_docx(content, filename)
    elif ext == "pdf":
        return extract_text_from_pdf(content, filename)
    else:
        try:
            return content.decode("utf-8", errors="replace")[:50000]
        except Exception:
            return "File: " + filename

async def call_claude(content, api_key):
    prompt = get_extraction_prompt(content)
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": CLAUDE_MODEL,
                "max_tokens": 2000,
                "messages": [{"role": "user", "content": prompt}]
            }
        )
        if resp.status_code != 200:
            raise HTTPException(
                status_code=resp.status_code,
                detail="Claude API error: " + resp.text[:500]
            )
        data = resp.json()
        raw = data["content"][0]["text"]
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                return {}
        return {}

@router.post("/{project_id}/upload")
async def upload_file(
    project_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    content = await file.read()
    extracted_text = extract_text(content, file.filename)
    uf = UploadedFile(
        project_id=project_id,
        file_name=file.filename,
        file_type=file.filename.split(".")[-1].lower(),
        extracted_text=extracted_text
    )
    db.add(uf)
    names = json.loads(p.file_names or "[]")
    if file.filename not in names:
        names.append(file.filename)
    p.file_names = json.dumps(names)
    p.has_files = True
    p.updated_at = datetime.utcnow()
    db.commit()
    return {
        "file_name": file.filename,
        "chars_extracted": len(extracted_text),
        "message": "File uploaded and text extracted."
    }

@router.post("/{project_id}/extract")
async def extract_answers(
    project_id: str,
    db: Session = Depends(get_db)
):
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    api_key = ANTHROPIC_API_KEY
    if not api_key:
        raise HTTPException(status_code=400, detail="ANTHROPIC_API_KEY not configured on server")
    files = db.query(UploadedFile).filter(UploadedFile.project_id == project_id).all()
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded yet")
    combined = "\n\n".join(
        "=== FILE: " + f.file_name + " ===\n" + (f.extracted_text or "")
        for f in files
    )
    extracted = await call_claude(combined, api_key)
    existing = json.loads(p.answers or "{}")
    found_count = 0
    for k, v in extracted.items():
        val = str(v or "").strip()
        if val and val not in ("null", "undefined", "None"):
            existing[k] = val
            found_count += 1
    missing = [q for q in REQUIRED_QUESTIONS if not existing.get(q)]
    completion = round(((len(REQUIRED_QUESTIONS) - len(missing)) / len(REQUIRED_QUESTIONS)) * 100)
    p.answers = json.dumps(existing)
    p.missing = json.dumps(missing)
    p.completion = completion
    p.updated_at = datetime.utcnow()
    db.commit()
    return {
        "extracted_count": found_count,
        "extracted": extracted,
        "completion": completion,
        "missing": missing,
        "all_answers": existing
    }

@router.get("/{project_id}/files")
def list_files(project_id: str, db: Session = Depends(get_db)):
    files = db.query(UploadedFile).filter(UploadedFile.project_id == project_id).all()
    return [
        {
            "id": f.id,
            "name": f.file_name,
            "type": f.file_type,
            "chars": len(f.extracted_text or ""),
            "uploaded": f.uploaded_at
        }
        for f in files
    ]
