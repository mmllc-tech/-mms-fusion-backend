"""Evidence pack — compile and download project audit trail"""
import io, json, zipfile
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.models.database import get_db, Project, LoadRun, Evidence

router = APIRouter()

@router.get("/{project_id}/summary")
def get_evidence_summary(project_id: str, db: Session = Depends(get_db)):
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    runs = db.query(LoadRun).filter(LoadRun.project_id == project_id).all()
    evidence = db.query(Evidence).filter(Evidence.project_id == project_id).all()
    answers = json.loads(p.answers or "{}")
    return {
        "project": p.name,
        "completion": p.completion,
        "total_runs": len(runs),
        "completed_runs": len([r for r in runs if r.status == "complete"]),
        "error_runs": len([r for r in runs if r.status == "error"]),
        "total_evidence_items": len(evidence),
        "evidence_types": list(set(e.evidence_type for e in evidence)),
        "blueprint_answers": len(answers),
        "generated_at": datetime.utcnow().isoformat()
    }

@router.get("/{project_id}/download")
def download_evidence_pack(project_id: str, db: Session = Depends(get_db)):
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    runs = db.query(LoadRun).filter(LoadRun.project_id == project_id).order_by(LoadRun.sequence).all()
    answers = json.loads(p.answers or "{}")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:

        blueprint_lines = [
            f"MMS FUSION AI ACCELERATOR — PROJECT EVIDENCE PACK",
            f"{'='*60}",
            f"Project: {p.name}",
            f"Consultant: {p.consultant or 'N/A'}",
            f"Go-Live: {p.golive or 'TBD'}",
            f"Blueprint Completion: {p.completion}%",
            f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
            f"",
            f"CONFIRMED IMPLEMENTATION DECISIONS",
            f"{'-'*40}",
        ]
        for k, v in answers.items():
            blueprint_lines.append(f"{k}: {v}")

        zf.writestr("01_Blueprint_Summary.txt", "\n".join(blueprint_lines))

        run_lines = [
            "ORACLE HCM LOAD EXECUTION LOG",
            f"{'='*60}",
            f"Project: {p.name}",
            f"",
        ]
        for r in runs:
            run_lines.extend([
                f"[{r.sequence:02d}] {r.object_name}",
                f"  Method: {r.method}",
                f"  Status: {r.status.upper()}",
                f"  Oracle Process: {r.oracle_process_id or 'N/A'}",
                f"  Errors: {r.error_count} | Warnings: {r.warning_count}",
                f"  Started: {r.started_at or 'N/A'}",
                f"  Completed: {r.completed_at or 'N/A'}",
                f"  HDL File: {r.hdl_file_name or 'N/A'}",
                f"",
            ])
        zf.writestr("02_Load_Execution_Log.txt", "\n".join(run_lines))

        error_runs = [r for r in runs if r.status == "error" and r.log_text]
        if error_runs:
            error_lines = ["ORACLE LOAD ERROR DETAILS", f"{'='*60}", ""]
            for r in error_runs:
                error_lines.append(f"Object: {r.object_name}")
                try:
                    messages = json.loads(r.log_text)
                    for m in messages:
                        if isinstance(m, dict):
                            error_lines.append(f"  [{m.get('messageType','INFO')}] {m.get('messageText','')}")
                except:
                    error_lines.append(f"  {r.log_text[:500]}")
                error_lines.append("")
            zf.writestr("03_Error_Details.txt", "\n".join(error_lines))

        uat_lines = [
            "UAT READINESS CHECKLIST",
            f"{'='*60}",
            f"Project: {p.name}",
            f"",
            "CONFIGURATION VERIFICATION",
            f"{'-'*40}",
        ]
        for r in runs:
            status_icon = "✓" if r.status == "complete" else ("⚠" if r.status == "warning" else "✗")
            uat_lines.append(f"  {status_icon} [{r.sequence:02d}] {r.object_name} — {r.status.upper()}")

        completed = len([r for r in runs if r.status == "complete"])
        total = len(runs)
        uat_lines.extend([
            "",
            f"SUMMARY: {completed}/{total} objects loaded successfully",
            f"Status: {'READY FOR UAT' if completed == total else 'NOT READY — resolve errors first'}",
        ])
        zf.writestr("04_UAT_Readiness_Checklist.txt", "\n".join(uat_lines))

    zip_buffer.seek(0)
    filename = f"Evidence_Pack_{p.name.replace(' ','_')}_{datetime.utcnow().strftime('%Y%m%d')}.zip"
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
