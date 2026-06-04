from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Job, JobStatus
from app.schemas import JobOut, JobRunRequest, ToolInfo
from app.tools.registry import get_tool, list_tools
from app.worker import run_tool_job

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("", response_model=list[ToolInfo])
def get_tools() -> list[ToolInfo]:
    return list_tools()


@router.post("/{slug}/run", response_model=JobOut)
def run_tool(
    slug: str,
    body: JobRunRequest,
    db: Session = Depends(get_db),
) -> Job:
    tool = get_tool(slug)
    if not tool:
        raise HTTPException(404, f"Tool '{slug}' not found or not enabled")

    job = Job(
        tool_slug=slug,
        status=JobStatus.pending.value,
        input_file_id=body.file_id,
        options=tool.validate_options(body.options),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        run_tool_job.delay(str(job.id))
    except Exception:
        run_tool_job.apply(args=[str(job.id)])

    return job
