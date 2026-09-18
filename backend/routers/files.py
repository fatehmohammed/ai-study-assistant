import os
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

import state
from config import UPLOADS_DIR, convert_pptx_to_pdf
from models import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(
        status="ok",
        chunks_indexed=state.pipeline.chunk_count(),
        sources=state.pipeline.list_sources(),
    )


@router.get("/sources")
def list_sources():
    return {
        "sources": state.pipeline.list_sources(),
        "total_chunks": state.pipeline.chunk_count(),
    }


@router.delete("/sources/{filename}")
def delete_source(filename: str):
    existing = state.pipeline._collection.get(where={"source": filename})
    if not existing["ids"]:
        raise HTTPException(status_code=404, detail=f"'{filename}' not found in index")
    state.pipeline._collection.delete(where={"source": filename})
    return {"status": "deleted", "source": filename, "chunks_removed": len(existing["ids"])}


@router.get("/files/{filename}")
def get_file(filename: str):
    if filename.lower().endswith(".pptx"):
        pdf_name = os.path.splitext(filename)[0] + ".pdf"
        path = os.path.join(UPLOADS_DIR, pdf_name)
        if not os.path.exists(path):
            pptx_path = os.path.join(UPLOADS_DIR, filename)
            if os.path.exists(pptx_path):
                try:
                    convert_pptx_to_pdf(pptx_path)
                except Exception as e:
                    raise HTTPException(status_code=500, detail=f"Conversion failed: {e}")
            else:
                raise HTTPException(status_code=404, detail=f"'{filename}' not found")
        return FileResponse(path, media_type="application/pdf")

    path = os.path.join(UPLOADS_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"'{filename}' not found")
    return FileResponse(path)


@router.get("/files/{filename}/slides/{page_num}")
def get_slide_image(filename: str, page_num: int):
    stem = os.path.splitext(filename)[0]
    path = os.path.join(UPLOADS_DIR, f"{stem}_slides", f"page_{page_num}.png")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Slide {page_num} not found for '{filename}'")
    return FileResponse(path, media_type="image/png")
