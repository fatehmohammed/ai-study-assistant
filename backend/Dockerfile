FROM python:3.12-slim

# System dependencies: LibreOffice for PPTX→PDF, Tesseract for OCR
RUN apt-get update && apt-get install -y \
    libreoffice-impress \
    libreoffice-writer \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
# Install CPU-only PyTorch first to avoid pulling 1GB+ of CUDA/GPU packages
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

# Bake the embedding model into the image so there's no download at runtime
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

ENV HF_HUB_OFFLINE=1
ENV TRANSFORMERS_OFFLINE=1
ENV SOFFICE_PATH=/usr/bin/soffice
ENV DATA_DIR=/data

COPY . .

EXPOSE 8080
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
