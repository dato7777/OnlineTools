FROM python:3.11-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    ghostscript \
    qpdf \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app
ENV STORAGE_PATH=/data/storage

RUN mkdir -p /data/storage

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
