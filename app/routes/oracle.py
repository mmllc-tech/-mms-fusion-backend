"""
Oracle HCM REST API Connector
- Authenticate against Oracle HCM Cloud
- Upload HDL files via REST
- Trigger HCM Data Loader process
- Poll ESS for load status
- Retrieve load messages and errors
"""
import os, json, base64
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.models.database import get_db, Project, LoadRun, Evidence
import httpx

router = APIRouter()

class OracleConnection(BaseModel):
    oracle_url: str
    username: str
    password: str
    project_id: str

class LoadRequest(BaseModel):
    project_id: str
    oracle_url: str
    username: str
    password: str
    object_names: Optional[list] = None

def get_auth_header(username: str, password: str) -> str:
    credentials = f"{username}:{password}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return f"Basic {encoded}"

async def oracle_upload_hdl(
    oracle_url: str, username: str, password: str, hdl_content: str, filename: str
) -> dict:
    url = f"{oracle_url}/hcmRestApi/resources/11.13.18.05/hcmDataLoader/upload"
    auth = get_auth_header(username, password)
    async with httpx.AsyncClient(timeout=120, verify=False) as client:
        resp = await client.post(
            url,
            headers={"Authorization": auth, "Content-Type": "application/octet-stream",
                     "Metadata": f'{{"fileName": "{filename}"}}'},
            content=hdl_content.encode("utf-8")
        )
        if resp.status_code not in (200, 201, 202):
            raise HTTPException(status_code=resp.status_code,
                detail=f"Oracle upload error: {resp.text[:500]}")
        return resp.json()

async def oracle_trigger_load(
    oracle_url: str, username: str, password: str, content_id: str
) -> dict:
    url = f"{oracle_url}/hcmRestApi/resources/11.13.18.05/hcmDataLoader/import"
    auth = get_auth_header(username, password)
    async with httpx.AsyncClient(timeout=60, verify=False) as client:
        resp = await client.post(
            url,
            headers={"Authorization": auth, "Content-Type": "application/json"},
            json={"contentId": content_id}
        )
        if resp.status_code not in (200, 201, 202):
            raise HTTPException(status_code=resp.status_code,
                detail=f"Oracle load trigger error: {resp.text[:500]}")
        return resp.json()

async def oracle_get_status(
    oracle_url: str, username: str, password: str, process_id: str
) -> dict:
    url = f"{oracle_url}/hcmRestApi/resources/11.13.18.05/hcmDataLoader/{process_id}"
    auth = get_auth_header(username, password)
    async with httpx.AsyncClient(timeout=30, verify=False) as client:
        resp = await client.get(url, headers={"Authorization": auth})
        if resp.status_code != 200:
            return {"status": "unknown", "error": resp.text[:200]}
        return resp.json()

async def oracle_get_messages(
    oracle_url: str, username: str, password: str, process_id: str
) -> list:
    url = f"{oracle_url}/hcmRestApi/resources/11.13.18.05/hcmDataLoader/{process_id}/messages"
    auth = get_auth_header(username, password)
    async with httpx.AsyncClient(timeout=30, verify=False) as client:
        resp = await client.get(url, headers={"Authorization": auth})
        if resp.status_code != 200:
            return []
        data = resp.json()
        return data.get("items", [])

@router.post("/test-connection")
async def test_oracle_connection(conn: OracleConnection):
    try:
        url = f"{conn.oracle_url}/hcmRestApi/resources/11.13.18.05/workers"
        auth = get_auth_header(conn.username, conn.password)
        async with httpx.AsyncClient(timeout=15, verify=False) as client:
            resp = await client.get(
                url,
                headers={"Authorization": auth},
                params={"limit": 1}
            )
            if resp.status_code == 200:
                return {"connected": True, "message": "Oracle connection successful"}
            elif resp.status_code == 401:
                raise HTTPException(status_code=401, detail="Invalid Oracle credentials")
            else:
                raise HTTPException(status_code=resp.status_code,
                    detail=f"Oracle connection failed: {resp.status_code}")
    except httpx.ConnectError:
        raise HTTPException(status_code=400,
            detail="Cannot reach Oracle URL. Check the URL and your network connection.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Connection error: {str(e)}")

@router.post("/load")
async def start_load(
    request: LoadRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    p = db.query(Project).filter(Project.id == request.project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    query = db.query(LoadRun).filter(
        LoadRun.project_id == request.project_id,
        LoadRun.status == "ready",
        LoadRun.method == "HDL"
    ).order_by(LoadRun.sequence)

    if request.object_names:
        query = query.filter(LoadRun.object_name.in_(request.object_names))

    runs = query.all()
    if not runs:
        raise HTTPException(status_code=400, detail="No ready HDL runs found for this project")

    background_tasks.add_task(
        execute_load_sequence,
        runs=[r.id for r in runs],
        oracle_url=request.oracle_url,
        username=request.username,
        password=request.password,
        project_id=request.project_id
    )

    return {
        "started": True,
        "runs_queued": len(runs),
        "objects": [r.object_name for r in runs],
        "message": "Load sequence started. Monitor status at /api/oracle/status/{project_id}"
    }

async def execute_load_sequence(
    runs: list, oracle_url: str, username: str, password: str, project_id: str
):
    from app.models.database import SessionLocal, LoadRun, Evidence
    UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/tmp/mms_fusion_hdl")

    db = SessionLocal()
    try:
        for run_id in runs:
            run = db.query(LoadRun).filter(LoadRun.id == run_id).first()
            if not run:
                continue

            run.status = "running"
            run.started_at = datetime.utcnow()
            db.commit()

            try:
                hdl_path = os.path.join(UPLOAD_DIR, project_id, run.hdl_file_name)
                if not os.path.exists(hdl_path):
                    run.status = "error"
                    run.log_text = f"HDL file not found: {hdl_path}"
                    db.commit()
                    continue

                with open(hdl_path, "r") as f:
                    hdl_content = f.read()

                upload_result = await oracle_upload_hdl(
                    oracle_url, username, password, hdl_content, run.hdl_file_name
                )
                content_id = upload_result.get("contentId") or upload_result.get("ContentId")

                if not content_id:
                    run.status = "error"
                    run.log_text = f"No content ID returned from Oracle: {json.dumps(upload_result)}"
                    db.commit()
                    continue

                load_result = await oracle_trigger_load(oracle_url, username, password, content_id)
                process_id = load_result.get("processId") or load_result.get("ProcessId")
                run.oracle_process_id = str(process_id) if process_id else None

                import asyncio
                for attempt in range(20):
                    await asyncio.sleep(15)
                    status_data = await oracle_get_status(
                        oracle_url, username, password, str(process_id)
                    )
                    oracle_status = status_data.get("status") or status_data.get("Status", "")

                    if oracle_status in ("COMPLETED", "COMPLETED_WITH_WARNINGS", "FAILED", "ERROR"):
                        messages = await oracle_get_messages(
                            oracle_url, username, password, str(process_id)
                        )
                        errors = [m for m in messages if m.get("messageType") == "ERROR"]
                        warnings = [m for m in messages if m.get("messageType") == "WARNING"]

                        run.error_count = len(errors)
                        run.warning_count = len(warnings)
                        run.log_text = json.dumps(messages[:50])

                        if oracle_status in ("FAILED", "ERROR") or len(errors) > 0:
                            run.status = "error"
                        elif oracle_status == "COMPLETED_WITH_WARNINGS":
                            run.status = "warning"
                        else:
                            run.status = "complete"

                        run.completed_at = datetime.utcnow()

                        ev = Evidence(
                            project_id=project_id,
                            evidence_type="load_log",
                            file_name=f"load_log_{run.object_name}_{run_id}.json",
                            notes=f"Oracle process {process_id} — {run.status} — {len(errors)} errors, {len(warnings)} warnings"
                        )
                        db.add(ev)
                        db.commit()
                        break
                else:
                    run.status = "timeout"
                    run.log_text = "Load timed out after 5 minutes"
                    run.completed_at = datetime.utcnow()
                    db.commit()

            except Exception as e:
                run.status = "error"
                run.log_text = str(e)
                run.completed_at = datetime.utcnow()
                db.commit()
    finally:
        db.close()

@router.get("/status/{project_id}")
def get_load_status(project_id: str, db: Session = Depends(get_db)):
    runs = db.query(LoadRun).filter(
        LoadRun.project_id == project_id
    ).order_by(LoadRun.sequence).all()

    summary = {
        "queued": len([r for r in runs if r.status == "queued"]),
        "ready": len([r for r in runs if r.status == "ready"]),
        "running": len([r for r in runs if r.status == "running"]),
        "complete": len([r for r in runs if r.status == "complete"]),
        "warning": len([r for r in runs if r.status == "warning"]),
        "error": len([r for r in runs if r.status == "error"]),
    }

    return {
        "summary": summary,
        "runs": [{
            "id": r.id,
            "object": r.object_name,
            "method": r.method,
            "sequence": r.sequence,
            "status": r.status,
            "oracle_process_id": r.oracle_process_id,
            "error_count": r.error_count,
            "warning_count": r.warning_count,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        } for r in runs]
    }

@router.get("/messages/{run_id}")
def get_run_messages(run_id: int, db: Session = Depends(get_db)):
    run = db.query(LoadRun).filter(LoadRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    messages = json.loads(run.log_text or "[]")
    return {"run_id": run_id, "object": run.object_name, "messages": messages}
