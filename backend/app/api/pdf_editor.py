import json
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Artifact, FileAsset, Job, JobStatus
from app.pipelines.accuracy import export_pdf_from_model, model_has_changes, save_block_document
from app.pipelines.placement import compute_placement_metrics
from app.pipelines.editor_preview import render_page_without_text
from app.pipelines.model_merge import merge_pages_with_originals
from app.schemas import ModelPatchRequest
from app.storage import file_path, read_file
from app.worker import run_tool_job

router = APIRouter(prefix="/tools/pdf-editor", tags=["pdf-editor"])

_ASSET_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".bmp": "image/bmp",
}


def _latest_model_artifact(db: Session, file_id: UUID) -> Artifact | None:
    return (
        db.query(Artifact)
        .join(Job)
        .filter(Job.input_file_id == file_id, Artifact.kind == "block_model")
        .order_by(Artifact.created_at.desc())
        .first()
    )


def _page_preview_artifact(db: Session, file_id: UUID, page_index: int) -> Artifact | None:
    arts = (
        db.query(Artifact)
        .join(Job)
        .filter(Job.input_file_id == file_id, Artifact.kind == "page_preview")
        .order_by(Artifact.created_at.desc())
        .all()
    )
    for art in arts:
        if art.meta and art.meta.get("pageIndex") == page_index:
            return art
    return None


@router.get("/documents/{file_id}/pages/{page_index}/preview.png")
def get_page_preview(
    file_id: UUID,
    page_index: int,
    db: Session = Depends(get_db),
) -> Response:
    """Always render from the latest block model (reflects deleted fills / layers)."""
    asset = db.get(FileAsset, file_id)
    if not asset:
        raise HTTPException(404, "File not found")

    model_art = _latest_model_artifact(db, file_id)
    if not model_art:
        art = _page_preview_artifact(db, file_id, page_index)
        if art:
            return Response(content=read_file(art.storage_key), media_type="image/png")
        raise HTTPException(404, "Run analyze first")

    model = json.loads(read_file(model_art.storage_key))
    page_data = next((p for p in model.get("pages", []) if p["pageIndex"] == page_index), None)
    if not page_data:
        raise HTTPException(404, "Page not found")

    png = render_page_without_text(
        str(file_path(asset.storage_key)),
        page_index,
        page_data.get("blocks", []),
    )
    return Response(content=png, media_type="image/png")


@router.get("/documents/{file_id}/asset")
def get_document_asset(
    file_id: UUID,
    key: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
) -> Response:
    """Serve extracted PDF images stored under artifacts/{file_id}/."""
    asset = db.get(FileAsset, file_id)
    if not asset:
        raise HTTPException(404, "File not found")

    prefix = f"artifacts/{file_id}/"
    if ".." in key or not key.startswith(prefix):
        raise HTTPException(400, "Invalid asset key")

    try:
        data = read_file(key)
    except OSError:
        raise HTTPException(404, "Asset not found")

    mime = _ASSET_MIME.get(Path(key).suffix.lower(), "application/octet-stream")
    return Response(content=data, media_type=mime)


@router.get("/documents/{file_id}/model")
def get_model(file_id: UUID, db: Session = Depends(get_db)) -> dict:
    asset = db.get(FileAsset, file_id)
    if not asset:
        raise HTTPException(404, "File not found")
    art = _latest_model_artifact(db, file_id)
    if not art:
        raise HTTPException(404, "Model not ready — run analyze first")
    return json.loads(read_file(art.storage_key))


@router.patch("/documents/{file_id}/model")
def patch_model(
    file_id: UUID,
    body: ModelPatchRequest,
    db: Session = Depends(get_db),
) -> dict:
    asset = db.get(FileAsset, file_id)
    if not asset:
        raise HTTPException(404, "File not found")

    incoming_pages = [p.model_dump() for p in body.pages]
    art_prev = _latest_model_artifact(db, file_id)
    prev: dict = {}
    if art_prev:
        prev = json.loads(read_file(art_prev.storage_key))

    pages = (
        merge_pages_with_originals(incoming_pages, prev.get("pages", []))
        if prev
        else incoming_pages
    )
    model = {
        "fileId": str(file_id),
        "pages": pages,
    }
    if prev:
        model["nativePageRatio"] = prev.get("nativePageRatio", 1.0)
        model["diagnostics"] = prev.get("diagnostics", {})

    key = save_block_document(model, f"artifacts/{file_id}/models")
    job = Job(
        tool_slug="pdf-editor",
        status=JobStatus.completed.value,
        progress=100,
        input_file_id=file_id,
        progress_message="Model saved",
    )
    db.add(job)
    db.flush()
    db.add(Artifact(job_id=job.id, kind="block_model", storage_key=key, meta={"saved": True}))
    db.commit()
    return model


class PlacementMetricsRequest(BaseModel):
    block: dict


@router.post("/placement-metrics")
def post_placement_metrics(body: PlacementMetricsRequest) -> dict:
    """Server-computed insert rect and font size — same math as PDF export."""
    return compute_placement_metrics(body.block)


class ExportRequest(BaseModel):
    model: dict | None = None


@router.post("/documents/{file_id}/export", response_model=dict)
def export_document(
    file_id: UUID,
    body: ExportRequest,
    db: Session = Depends(get_db),
) -> dict:
    asset = db.get(FileAsset, file_id)
    if not asset:
        raise HTTPException(404, "File not found")

    options: dict = {"action": "export"}
    if body.model:
        options["model"] = body.model
    else:
        art = _latest_model_artifact(db, file_id)
        if art:
            options["model"] = json.loads(read_file(art.storage_key))

    model = options.get("model")
    if model and not model_has_changes(model):
        out_key = export_pdf_from_model(asset.storage_key, model)
        out_data = read_file(out_key)
        out_asset = FileAsset(
            filename=asset.filename,
            mime_type=asset.mime_type,
            size_bytes=len(out_data),
            storage_key=out_key,
        )
        db.add(out_asset)
        db.flush()
        job = Job(
            tool_slug="pdf-editor",
            status=JobStatus.completed.value,
            progress=100,
            input_file_id=file_id,
            output_file_id=out_asset.id,
            progress_message="Original PDF (no edits)",
            options=options,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return {
            "jobId": str(job.id),
            "status": job.status,
            "outputFileId": str(job.output_file_id),
            "unchanged": True,
        }

    job = Job(
        tool_slug="pdf-editor",
        status=JobStatus.pending.value,
        input_file_id=file_id,
        options=options,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        run_tool_job.delay(str(job.id))
    except Exception:
        run_tool_job.apply(args=[str(job.id)])

    db.refresh(job)
    return {
        "jobId": str(job.id),
        "status": job.status,
        "outputFileId": str(job.output_file_id) if job.output_file_id else None,
        "unchanged": False,
    }
