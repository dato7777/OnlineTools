import mimetypes
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import FileAsset
from app.schemas import FileAssetOut
from app.storage import file_path, save_upload

router = APIRouter(prefix="/files", tags=["files"])


@router.post("", response_model=FileAssetOut)
async def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> FileAsset:
    data = await file.read()
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, "File too large")
    if not data:
        raise HTTPException(400, "Empty file")

    filename = file.filename or "upload.bin"
    mime = file.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    storage_key, checksum = save_upload(data, filename)

    asset = FileAsset(
        filename=filename,
        mime_type=mime,
        size_bytes=len(data),
        storage_key=storage_key,
        checksum=checksum,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


@router.get("/{file_id}", response_model=FileAssetOut)
def get_file_meta(file_id: UUID, db: Session = Depends(get_db)) -> FileAsset:
    asset = db.get(FileAsset, file_id)
    if not asset:
        raise HTTPException(404, "File not found")
    return asset


@router.get("/{file_id}/download")
def download_file(file_id: UUID, db: Session = Depends(get_db)) -> FileResponse:
    asset = db.get(FileAsset, file_id)
    if not asset:
        raise HTTPException(404, "File not found")
    path = file_path(asset.storage_key)
    if not path.exists():
        raise HTTPException(404, "File missing from storage")
    return FileResponse(
        path,
        media_type=asset.mime_type,
        filename=asset.filename,
    )
