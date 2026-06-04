from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy.orm import Session


@dataclass
class ToolResult:
    output_file_id: UUID | None = None
    artifacts: list[dict[str, Any]] | None = None
    message: str | None = None


class ToolHandler(Protocol):
    slug: str
    title: str
    description: str
    icon: str
    input_mime_types: list[str]

    def validate_options(self, options: dict[str, Any]) -> dict[str, Any]: ...

    def run(self, db: Session, file_id: UUID, job_id: UUID, options: dict[str, Any]) -> ToolResult: ...
