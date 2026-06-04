import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Artifact, Job
from app.schemas import ArtifactOut, JobOut
from app.storage import read_file

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: UUID, db: Session = Depends(get_db)) -> Job:
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@router.get("/{job_id}/artifacts", response_model=list[ArtifactOut])
def list_artifacts(job_id: UUID, db: Session = Depends(get_db)) -> list[ArtifactOut]:
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    out: list[ArtifactOut] = []
    for art in job.artifacts:
        item = ArtifactOut.model_validate(art)
        if art.kind == "block_model":
            item.download_url = f"/api/v1/artifacts/{art.id}/content"
        out.append(item)
    return out


@router.get("/artifacts/{artifact_id}/content")
def get_artifact_content(artifact_id: UUID, db: Session = Depends(get_db)):
    from fastapi.responses import JSONResponse, Response

    art = db.get(Artifact, artifact_id)
    if not art:
        raise HTTPException(404, "Artifact not found")
    raw = read_file(art.storage_key)
    if art.kind == "block_model":
        return JSONResponse(content=json.loads(raw))
    return Response(content=raw, media_type="application/octet-stream")
