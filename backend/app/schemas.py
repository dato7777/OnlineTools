from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ToolInfo(BaseModel):
    slug: str
    title: str
    description: str
    icon: str
    input_mime_types: list[str]
    enabled: bool = True
    coming_soon: bool = False


class FileAssetOut(BaseModel):
    id: UUID
    filename: str
    mime_type: str
    size_bytes: int
    created_at: datetime

    model_config = {"from_attributes": True}


class JobOut(BaseModel):
    id: UUID
    tool_slug: str
    status: str
    progress: int
    progress_message: str | None
    error: str | None
    input_file_id: UUID
    output_file_id: UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class JobRunRequest(BaseModel):
    file_id: UUID
    options: dict[str, Any] = Field(default_factory=dict)


class ArtifactOut(BaseModel):
    id: UUID
    kind: str
    meta: dict[str, Any] | None
    download_url: str | None = None

    model_config = {"from_attributes": True}


class BlockText(BaseModel):
    id: str
    type: str = "text"
    bbox: list[float]
    content: str
    fontSize: float = 12
    fontFamily: str = "Helvetica"
    source: str = "native"


class BlockImage(BaseModel):
    id: str
    type: str = "image"
    bbox: list[float]
    assetId: str | None = None
    source: str = "extracted"


class PageModel(BaseModel):
    pageIndex: int
    pageType: str
    width: float
    height: float
    blocks: list[dict[str, Any]]
    tierUsed: str = "native"


class BlockDocument(BaseModel):
    fileId: str
    pages: list[PageModel]
    nativePageRatio: float = 1.0
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class ModelPatchRequest(BaseModel):
    pages: list[PageModel]
