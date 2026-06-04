import json
import uuid
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import Artifact, FileAsset, Job, JobStatus
from app.pipelines.accuracy import analyze_pdf, export_pdf_from_model, save_block_document
from app.pipelines.editor_preview import render_page_full
from app.storage import file_path, read_file, save_bytes
from app.tools.base import ToolHandler, ToolResult


class PdfEditorTool:
    slug = "pdf-editor"
    title = "PDF Editor"
    description = "Edit text and images in PDFs. Recover scanned documents into editable PDFs."
    icon = "file-pen"
    input_mime_types = ["application/pdf"]

    def validate_options(self, options: dict[str, Any]) -> dict[str, Any]:
        allowed = {"action"}
        return {k: v for k, v in options.items() if k in allowed}

    def run(self, db: Session, file_id: UUID, job_id: UUID, options: dict[str, Any]) -> ToolResult:
        job = db.get(Job, job_id)
        file_asset = db.get(FileAsset, file_id)
        if not job or not file_asset:
            raise ValueError("Job or file not found")

        action = options.get("action", "analyze")

        if action == "export":
            return self._export(db, job, file_asset, options)

        job.status = JobStatus.running.value
        job.progress = 10
        job.progress_message = "Reading document layout…"
        db.commit()

        model = analyze_pdf(file_asset.storage_key, str(file_id))

        job.progress = 70
        job.progress_message = "Building editable model…"
        db.commit()

        model_key = save_block_document(model, f"artifacts/{file_id}/models")
        artifact = Artifact(
            job_id=job_id,
            kind="block_model",
            storage_key=model_key,
            meta={"nativePageRatio": model.get("nativePageRatio")},
        )
        db.add(artifact)

        job.progress = 85
        job.progress_message = "Preparing editor previews…"
        db.commit()

        src_path = str(file_path(file_asset.storage_key))
        for page_data in model.get("pages", []):
            idx = page_data["pageIndex"]
            png = render_page_full(src_path, idx)
            preview_key = save_bytes(
                png,
                f"artifacts/{file_id}/previews",
                f"_p{idx}.png",
            )
            db.add(
                Artifact(
                    job_id=job_id,
                    kind="page_preview",
                    storage_key=preview_key,
                    meta={"pageIndex": idx},
                )
            )

        job.progress = 95
        job.progress_message = "Almost ready…"
        db.commit()

        job.status = JobStatus.completed.value
        job.progress = 100
        job.progress_message = "Ready to edit"
        db.commit()

        return ToolResult(
            artifacts=[{"kind": "block_model", "storage_key": model_key, "meta": artifact.meta}],
            message="Analysis complete",
        )

    def _export(
        self, db: Session, job: Job, file_asset: FileAsset, options: dict[str, Any]
    ) -> ToolResult:
        model = options.get("model")
        if not model:
            artifact = (
                db.query(Artifact)
                .filter(Artifact.job_id == job.id, Artifact.kind == "block_model")
                .order_by(Artifact.created_at.desc())
                .first()
            )
            if artifact:
                model = json.loads(read_file(artifact.storage_key))
        if not model:
            for art in (
                db.query(Artifact)
                .filter(Artifact.kind == "block_model")
                .join(Job)
                .filter(Job.input_file_id == file_asset.id)
                .order_by(Artifact.created_at.desc())
                .all()
            ):
                model = json.loads(read_file(art.storage_key))
                break
        if not model:
            raise ValueError("No block model found for export")

        job.progress_message = "Exporting PDF…"
        job.status = JobStatus.running.value
        db.commit()

        out_key = export_pdf_from_model(file_asset.storage_key, model)
        out_data = read_file(out_key)
        out_asset = FileAsset(
            filename=f"edited-{file_asset.filename}",
            mime_type="application/pdf",
            size_bytes=len(out_data),
            storage_key=out_key,
        )
        db.add(out_asset)
        db.flush()

        job.output_file_id = out_asset.id
        job.status = JobStatus.completed.value
        job.progress = 100
        job.progress_message = "Export complete"
        db.commit()

        return ToolResult(output_file_id=out_asset.id, message="PDF exported")


pdf_editor_tool = PdfEditorTool()
