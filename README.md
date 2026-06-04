# OnlineTools

Self-hosted document platform: **PDF Editor** (native edit + scan recovery) first, with a pluggable architecture for more conversion tools later.

## Stack

- **Frontend:** Next.js 15, Tailwind, Framer Motion, PDF.js, Konva
- **Backend:** FastAPI, Celery, SQLAlchemy, PyMuPDF, pikepdf, pdfplumber
- **Infra:** PostgreSQL, Redis, MinIO (Docker Compose)

## Quick start (local)

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
mkdir -p storage
uvicorn app.main:app --reload --port 8000
```

**Tesseract (for scanned PDFs)** — required for OCR on image-only pages:

```bash
# macOS (Homebrew)
brew install tesseract

# Ubuntu/Debian
sudo apt install tesseract-ocr
```

Verify: `tesseract --version`. If Homebrew installs to a non-default path, set in `backend/.env`:

```
TESSERACT_CMD=/opt/homebrew/bin/tesseract
```

Without Tesseract, native PDFs still work; scanned pages get image blocks only and a warning in the editor diagnostics.

Optional worker (uses sync fallback if Redis unavailable):

```bash
celery -A app.worker.celery_app worker -l info -Q default,pdf
```

Uses **SQLite** by default (`./onlinetools.db`). For PostgreSQL, set `DATABASE_URL` in `.env` (see `.env.example`).

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). API: [http://localhost:8000](http://localhost:8000).

## Docker Compose

```bash
docker compose up --build
```

- Frontend: http://localhost:3000  
- API: http://localhost:8000  
- MinIO console: http://localhost:9001  

## PDF Editor flow

1. **Tools hub** → PDF Editor  
2. Upload PDF → analyze job builds a **block model** (text + image bboxes)  
3. **Editor** — select blocks, edit text, drag positions, download export  
4. Scanned pages use Tesseract OCR when native text is sparse (install `tesseract-ocr`)

## Accuracy pipeline (tiers)

| Tier | Library | Use |
|------|---------|-----|
| 0 | PyMuPDF, pikepdf | Inspect, render, export |
| 1 | PyMuPDF, pdfplumber | Native text blocks |
| 2 | OpenDataLoader PDF (optional, JDK 11+) | Layout JSON |
| 3 | PaddleOCR / Surya (optional) | High-accuracy OCR |
| 4 | OCRmyPDF | Searchable PDF tool (planned) |

Install optional deps as you scale; core MVP runs on PyMuPDF + Tesseract.

**Edited text export:** Native PDF text uses [pdf-edit-engine](https://github.com/AryanBV/pdf-edit-engine) to replace words in-place (fonts/layout preserved). Scanned pages use OCR blocks + overlay fallback. Re-upload after pulling latest code so blocks include `originalContent`.

## Adding a new tool

1. Implement `ToolHandler` in `backend/app/tools/your_tool.py`  
2. Register in `backend/app/tools/registry.py`  
3. Add a **Coming soon** or live card via `GET /tools`  
4. Add `frontend/src/app/tools/[slug]/page.tsx` or reuse shared upload flow  

## Environment

| Variable | Default |
|----------|---------|
| `DATABASE_URL` | `sqlite:///./onlinetools.db` |
| `STORAGE_PATH` | `./storage` |
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` |
| `CORS_ORIGINS` | `http://localhost:3000` |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` |

## Limitations (v1)

- Scan font matching is approximate (Helvetica fallback on export).  
- Complex tables may export as images or simplified text.  
- OpenDataLoader / PaddleOCR are optional upgrades for harder documents.
