from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import files, jobs, pdf_editor, tools
from app.config import settings
from app.db import init_db
from app.storage import ensure_storage


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_storage()
    init_db()
    yield


app = FastAPI(
    title="OnlineTools API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = "/api/v1"
app.include_router(files.router, prefix=API_PREFIX)
app.include_router(jobs.router, prefix=API_PREFIX)
app.include_router(tools.router, prefix=API_PREFIX)
app.include_router(pdf_editor.router, prefix=API_PREFIX)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
