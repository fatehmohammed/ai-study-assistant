import os
import asyncio
import json
import shutil
import tempfile

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

import state
from config import UPLOADS_DIR, convert_pptx_to_pdf
from models import IndexResponse

router = APIRouter()

MAX_SIZE = 50 * 1024 * 1024


def _validate_upload(filename: str, content: bytes) -> None:
    if not filename.lower().endswith((".pdf", ".pptx")):
        raise HTTPException(status_code=400, detail="Only PDF and PPTX files are supported")
    if len(content) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 50MB.")


def _save_upload(filename: str, content: bytes) -> tuple[str, str]:
    """Write content to a named temp file and copy to uploads dir. Returns (tmp_path, saved_path)."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    named_path = os.path.join(os.path.dirname(tmp_path), filename)
    os.rename(tmp_path, named_path)
    saved_path = os.path.join(UPLOADS_DIR, filename)
    shutil.copy2(named_path, saved_path)
    if filename.lower().endswith(".pptx"):
        try:
            convert_pptx_to_pdf(saved_path)
        except Exception:
            pass
    return named_path, saved_path


@router.post("/index", response_model=IndexResponse)
async def index_pdf(file: UploadFile = File(...)):
    content = await file.read()
    _validate_upload(file.filename, content)

    tmp_path = None
    try:
        tmp_path, _ = _save_upload(file.filename, content)
        result = state.pipeline.index(tmp_path)
        result["source"] = file.filename
        return IndexResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Indexing failed: {str(e)}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@router.post("/index/stream")
async def index_pdf_stream(file: UploadFile = File(...)):
    content = await file.read()
    _validate_upload(file.filename, content)

    tmp_path = None
    try:
        tmp_path, _ = _save_upload(file.filename, content)
    except Exception as e:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise HTTPException(status_code=500, detail=str(e))

    async def event_stream():
        import pymupdf
        try:
            filename = file.filename
            existing = state.pipeline._collection.get(where={"source": filename})
            if existing["ids"]:
                yield f"data: {json.dumps({'type': 'done', 'source': filename, 'chunks': len(existing['ids']), 'message': 'Already indexed', 'unreadable_pages': []})}\n\n"
                return

            doc = pymupdf.open(tmp_path)
            total_pages = len(doc)
            all_text_parts = []
            unreadable_pages = []
            stem = os.path.splitext(filename)[0]
            slides_dir = os.path.join(UPLOADS_DIR, f"{stem}_slides")

            for i, page in enumerate(doc):
                text = page.get_text()
                if len(text.split()) < 10:
                    tp = page.get_textpage_ocr(flags=3, language="eng", dpi=300)
                    text = page.get_text(textpage=tp)
                if len(text.split()) < 10:
                    unreadable_pages.append(i + 1)
                    os.makedirs(slides_dir, exist_ok=True)
                    pix = page.get_pixmap(dpi=150)
                    pix.save(os.path.join(slides_dir, f"page_{i + 1}.png"))
                all_text_parts.append(text)
                pct = round((i + 1) / total_pages * 100)
                yield f"data: {json.dumps({'type': 'progress', 'page': i + 1, 'total': total_pages, 'pct': pct})}\n\n"
                await asyncio.sleep(0)

            full_text = "\n".join(all_text_parts)
            if len(full_text.split()) < 20:
                yield f"data: {json.dumps({'type': 'error', 'message': 'No text could be extracted.'})}\n\n"
                return

            chunks = state.pipeline._chunk_text(full_text)
            embeddings = state.pipeline._embed(chunks)
            ids = [f"{filename}_chunk_{i}" for i in range(len(chunks))]
            state.pipeline._collection.add(
                documents=chunks,
                embeddings=embeddings,
                ids=ids,
                metadatas=[{"source": filename, "chunk_index": i} for i in range(len(chunks))],
            )
            yield f"data: {json.dumps({'type': 'done', 'source': filename, 'chunks': len(chunks), 'message': f'Indexed {len(chunks)} chunks', 'unreadable_pages': unreadable_pages})}\n\n"

            meta = {"total_pages": total_pages, "unreadable_pages": unreadable_pages}
            meta_path = os.path.join(UPLOADS_DIR, f"{stem}_meta.json")
            with open(meta_path, "w") as f:
                json.dump(meta, f)

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
