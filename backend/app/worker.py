from uuid import UUID

from celery import Celery
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import Job, JobStatus
from app.tools.registry import get_tool

celery_app = Celery(
    "onlinetools",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_routes={"app.worker.run_tool_job": {"queue": "pdf"}},
    task_default_queue="default",
)


@celery_app.task(name="app.worker.run_tool_job", bind=True, max_retries=2)
def run_tool_job(self, job_id: str) -> dict:
    db: Session = SessionLocal()
    try:
        job = db.get(Job, UUID(job_id))
        if not job:
            return {"error": "Job not found"}

        tool = get_tool(job.tool_slug)
        if not tool:
            job.status = JobStatus.failed.value
            job.error = f"Unknown tool: {job.tool_slug}"
            db.commit()
            return {"error": job.error}

        job.status = JobStatus.running.value
        job.progress = 5
        db.commit()

        options = job.options or {}
        options = tool.validate_options(options)
        result = tool.run(db, job.input_file_id, job.id, options)
        db.refresh(job)
        return {
            "status": job.status,
            "output_file_id": str(result.output_file_id) if result.output_file_id else None,
            "message": result.message,
        }
    except Exception as exc:
        db.rollback()
        job = db.get(Job, UUID(job_id))
        if job:
            job.status = JobStatus.failed.value
            job.error = str(exc)
            db.commit()
        raise exc
    finally:
        db.close()
