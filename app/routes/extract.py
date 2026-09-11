"""
Secure extraction endpoint - Claude API key never exposed to browser
All AI calls go through this backend endpoint
"""
import os
import json
import re
from fastapi import APIRouter, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx

router = APIRouter()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-6"
BACKEND_VERSION = "1.0.0"

# ── KILL SWITCH ──────────────────────────────────────────────────────────────
# Set EXTRACTION_ENABLED=false on Render to pause ALL extraction instantly
# Set EXTRACTION_ENABLED=true to resume
# Default is true if not set
EXTRACTION_ENABLED = os.getenv("EXTRACTION_ENABLED", "true").lower() == "true"

def check_extraction_enabled():
    """Raise 503 if extraction is paused via kill switch."""
    # Re-read env var each call so Render env changes take effect immediately
    enabled = os.getenv("EXTRACTION_ENABLED", "true").lower() == "true"
    if not enabled:
        raise HTTPException(
            status_code=503,
            detail="AI extraction is temporarily paused. Please contact info@modernmindsolutionsllc.com"
        )


class ExtractRequest(BaseModel):
    documents: str  # Combined document text from browser
    pass_number: int = 1  # Which extraction pass (1, 2, or 3)


PROMPT_1 = """You are a senior Oracle HCM Cloud Core HR consultant with 15+ years experience.
Read these Oracle HCM implementation documents and extract the requested fields.
Return ONLY valid JSON. No markdown. No explanation. No preamble.
Only include a field if you found clear specific evidence. Do not guess.
If the value is a list, return it as a comma-separated string, NOT an array.

FIELDS TO EXTRACT:
- legislation: Country and legislation type
- enterprise: Enterprise name in Oracle HCM
- currency: Primary currency code
- go_live_date: Target go-live date
- impl_type: New implementation or migration type
- legal_entity: ALL legal entities - each with full name and EIN as comma-separated string
- legal_employer: Which legal entities are legal employers as comma-separated string
- psu: Which legal entities are Payroll Statutory Units as comma-separated string
- ldg: Legislative Data Group name
- bus_units: ALL business units as comma-separated list
- locations_count: Number of locations and states
- departments_count: Number of departments
- job_structure: Job structure description
- grade_structure: Grade structure description
- grade_rates: Whether salary ranges are needed
- positions: Position management scope
- positions_count: Number of budgeted positions
- worker_types: Worker types in scope
- multiple_assignments: Whether multiple simultaneous assignments allowed
- payroll_in_scope: Oracle Payroll in scope Yes/No/Future
- payroll_freq: Payroll frequency
- salary_basis: Salary bases with annualization factors
- elements: ALL earning elements as comma-separated list
- payroll_int: Payroll interface requirements
- employee_count: Total active employees
- legacy_system: Legacy HR system being replaced

DOCUMENTS:
{documents}

Return ONLY valid JSON with string values (never arrays or nested objects):
{"legislation":"...","enterprise":"..."}"""


PROMPT_2 = """You are a senior Oracle HCM Cloud Core HR consultant with 15+ years experience.
Read these Oracle HCM implementation documents and extract the requested fields.
Return ONLY valid JSON. No markdown. No explanation. No preamble.
Only include a field if you found clear specific evidence. Do not guess.
If the value is a list, return it as a comma-separated string, NOT an array.

FIELDS TO EXTRACT:
- absence_in_scope: Oracle Absence Management in scope Yes/No/Future
- absence_types: ALL absence types as comma-separated list
- accrual_plans: Accrual rules for PTO and sick leave
- benefits_in_scope: Oracle Benefits in scope Yes/No/Future
- benefit_plans: ALL benefit plan types as comma-separated list
- open_enrollment: Open enrollment timing
- sso: SSO requirements and identity provider
- page_customizations: HCM Design Studio page customizations needed
- hr_actions: Custom HR actions beyond Oracle standard
- action_reasons: Custom action reasons
- conversion_scope: Historical data conversion scope
- salary_conversion: Whether salary needs converting
- absence_balances: Whether absence balances need converting
- modules_enabled: Oracle modules enabled this phase
- costing: GL costing requirements

DOCUMENTS:
{documents}

Return ONLY valid JSON with string values (never arrays or nested objects):
{"absence_in_scope":"...","absence_types":"..."}"""


PROMPT_3 = """You are a senior Oracle HCM Cloud Core HR consultant with 15+ years experience.
Read these Oracle HCM implementation documents and extract ONLY the 3 fields below.
Return ONLY valid JSON with string values, never arrays.

FIELDS TO EXTRACT:
- security: ALL custom security roles as comma-separated string "Role Name (access scope), Role Name (access scope)". Look for Security Roles, HR Administrator, HR Specialist, Nurse Manager sections.
- dff: ALL Descriptive Flexfield segments as comma-separated string "Field Name (type, values)". Look for DFF, Descriptive Flexfield, Assignment DFF, Person DFF sections.
- integrations: ALL day-1 integrations as comma-separated string "System (direction, trigger)". Look for Integrations, ADP interface, Azure AD, Sterling sections.

DOCUMENTS:
{documents}

Return ONLY: {"security":"...","dff":"...","integrations":"..."}"""


def parse_json_safe(raw: str) -> dict:
    """Robustly parse JSON even if truncated."""
    m = raw.find('{')
    if m == -1:
        return {}
    js = raw[m:]
    try:
        return json.loads(js)
    except Exception:
        lc = js.rfind(',')
        lb = js.rfind('}')
        if lc > lb:
            js = js[:lc] + '}'
        try:
            return json.loads(js)
        except Exception:
            result = {}
            for match in re.finditer(r'"([a-z_]+)"\s*:\s*"([^"]{0,800})"', raw):
                result[match.group(1)] = match.group(2)
            return result


async def call_claude(prompt: str) -> dict:
    """Call Claude API securely from backend."""
    if not ANTHROPIC_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="API not configured. Contact info@modernmindsolutionsllc.com"
        )

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": CLAUDE_MODEL,
                "max_tokens": 4000,
                "messages": [{"role": "user", "content": prompt}]
            }
        )
        if resp.status_code != 200:
            raise HTTPException(
                status_code=resp.status_code,
                detail=f"AI service error: {resp.status_code}"
            )
        data = resp.json()
        raw = data["content"][0]["text"]
        return parse_json_safe(raw)


@router.post("/extract/pass1")
async def extract_pass1(req: ExtractRequest):
    """Pass 1: Extract enterprise, legal, BUs, payroll, jobs, grades."""
    check_extraction_enabled()
    prompt = PROMPT_1.format(documents=req.documents[:50000])
    result = await call_claude(prompt)
    return {"status": "ok", "extracted": result, "pass": 1}


@router.post("/extract/pass2")
async def extract_pass2(req: ExtractRequest):
    """Pass 2: Extract absence, benefits, SSO, HCM Design Studio."""
    check_extraction_enabled()
    prompt = PROMPT_2.format(documents=req.documents[:50000])
    result = await call_claude(prompt)
    return {"status": "ok", "extracted": result, "pass": 2}


@router.post("/extract/pass3")
async def extract_pass3(req: ExtractRequest):
    """Pass 3: Targeted extraction for security, DFFs, integrations."""
    check_extraction_enabled()
    prompt = PROMPT_3.format(documents=req.documents[:50000])
    result = await call_claude(prompt)
    return {"status": "ok", "extracted": result, "pass": 3}


@router.get("/extract/health")
async def extract_health():
    """Check if extraction service is configured."""
    enabled = os.getenv("EXTRACTION_ENABLED", "true").lower() == "true"
    return {
        "status": "ok",
        "api_configured": bool(ANTHROPIC_API_KEY),
        "extraction_enabled": enabled,
        "version": BACKEND_VERSION
    }
