import hashlib
import os
import uuid
from pathlib import Path

from app.config import settings


def ensure_storage() -> Path:
    root = Path(settings.storage_path)
    root.mkdir(parents=True, exist_ok=True)
    return root


def save_upload(data: bytes, filename: str) -> tuple[str, str | None]:
    root = ensure_storage()
    file_id = uuid.uuid4()
    ext = Path(filename).suffix or ""
    storage_key = f"uploads/{file_id}{ext}"
    path = root / storage_key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    checksum = hashlib.sha256(data).hexdigest()
    return storage_key, checksum


def save_bytes(data: bytes, prefix: str, suffix: str = "") -> str:
    root = ensure_storage()
    storage_key = f"{prefix}/{uuid.uuid4()}{suffix}"
    path = root / storage_key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return storage_key


def read_file(storage_key: str) -> bytes:
    path = ensure_storage() / storage_key
    return path.read_bytes()


def file_path(storage_key: str) -> Path:
    return ensure_storage() / storage_key


def delete_file(storage_key: str) -> None:
    path = ensure_storage() / storage_key
    if path.exists():
        os.remove(path)
