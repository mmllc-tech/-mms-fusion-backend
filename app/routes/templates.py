"""Templates route — generate scoped client Excel templates"""
import io, os, json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.models.database import get_db, Project

router = APIRouter()

@router.get("/{project_id}/generate/{template_name}")
def generate_template(project_id: str, template_name: str, db: Session = Depends(get_db)):
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        from app.services.template_generator import build_config_template, CONFIG_TEMPLATES
    except ImportError:
        raise HTTPException(status_code=500, detail="Template generator not available")

    if template_name not in CONFIG_TEMPLATES:
        raise HTTPException(status_code=404, detail=f"Template '{template_name}' not found")

    output = io.BytesIO()
    cfg = CONFIG_TEMPLATES[template_name]
    build_config_template(p.name, template_name, cfg, output)
    output.seek(0)

    safe_name = template_name.replace(" ", "_")
    filename = f"{safe_name}_{p.name.replace(' ', '_')}.xlsx"

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.get("/{project_id}/list")
def list_templates(project_id: str, db: Session = Depends(get_db)):
    try:
        from app.services.template_generator import CONFIG_TEMPLATES
        return {
            "templates": [
                {"key": k, "phase": v["phase"], "seq": v["seq"], "oracle": v["oracle"]}
                for k, v in CONFIG_TEMPLATES.items()
            ]
        }
    except ImportError:
        return {"templates": []}
