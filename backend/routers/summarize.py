import os
import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

import state
from config import UPLOADS_DIR
from models import SummarizeRequest

router = APIRouter()


@router.post("/summarize/stream")
async def summarize_stream(request: SummarizeRequest):
    if request.source_filter:
        result = state.pipeline._collection.get(
            where={"source": request.source_filter}, limit=10000,
            include=["documents", "metadatas"],
        )
    else:
        result = state.pipeline._collection.get(limit=10000, include=["documents", "metadatas"])

    if not result["documents"]:
        raise HTTPException(status_code=404, detail="No content found.")

    pairs = sorted(
        zip(result["documents"], result["metadatas"]),
        key=lambda x: x[1].get("chunk_index", 0),
    )
    documents = [p[0] for p in pairs]

    BATCH_SIZE = 10
    batches = [documents[i:i + BATCH_SIZE] for i in range(0, len(documents), BATCH_SIZE)]

    async def event_stream():
        try:
            batch_summaries = []

            for idx, batch in enumerate(batches):
                yield f"data: {json.dumps({'type': 'progress', 'current': idx + 1, 'total': len(batches), 'message': f'Reading section {idx + 1} of {len(batches)}…'})}\n\n"
                await asyncio.sleep(0)

                context = "\n\n---\n\n".join(batch)
                response = state.pipeline._claude.messages.create(
                    model=state.pipeline.claude_model,
                    max_tokens=1500,
                    messages=[{"role": "user", "content": f"""Extract every topic and key fact from these lecture notes. Do NOT skip or compress any topic — even if a section seems minor, include it. Capture:
- Every condition, disease, or clinical entity mentioned
- Exact numbers, thresholds, doses, and timeframes
- Drug names and their effects or interactions
- Clinical criteria, protocols, and step-by-step procedures
- Dental/clinical management points

Notes:
{context}"""}],
                )
                batch_summaries.append(response.content[0].text.strip())

            yield f"data: {json.dumps({'type': 'progress', 'current': len(batches) + 1, 'total': len(batches) + 1, 'message': 'Writing summary…'})}\n\n"
            await asyncio.sleep(0)

            if len(batch_summaries) > 1:
                combined = "\n\n---\n\n".join(f"Section {i + 1}:\n{s}" for i, s in enumerate(batch_summaries))
                final_prompt = f"""Combine ALL of the section summaries below into one comprehensive, study-friendly summary. Every topic from every section must appear — do not drop or merge away any condition or clinical entity.

Format:
- One-sentence intro naming all major topics covered
- Numbered sections (1. Topic, 2. Topic, ...) — one per major condition or theme, in lecture order
- Under each section: prose paragraphs weaving in specific facts, numbers, thresholds, drug names, protocols, and dental management points. Include markdown tables for comparisons
- A final "⭐ Exam Points to Memorise" section with concise bullet points of the highest-yield facts
- The very last line: "A useful overall concept from this lecture is: [step 1] → [step 2] → ..."

Do not truncate. Every section summary must be represented.

Section summaries:
{combined}"""
            else:
                final_prompt = f"""Format this study content as a comprehensive, study-friendly summary.

Format:
- One-sentence intro naming all major topics covered
- Numbered sections (1. Topic, 2. Topic, ...) — one per major condition or theme
- Under each: prose paragraphs with specific facts, numbers, thresholds, drug names, protocols. Include tables where helpful
- A final "⭐ Exam Points to Memorise" section
- Last line: "A useful overall concept from this lecture is: [step 1] → [step 2] → ..."

Content:
{batch_summaries[0]}"""

            with state.pipeline._claude.messages.stream(
                model=state.pipeline.claude_model,
                max_tokens=4096,
                messages=[{"role": "user", "content": final_prompt}],
            ) as stream:
                for text in stream.text_stream:
                    yield f"data: {json.dumps({'type': 'token', 'text': text})}\n\n"
                    await asyncio.sleep(0)

            total_pages: int | None = None
            unreadable_pages: list[int] = []
            if request.source_filter:
                stem = os.path.splitext(request.source_filter)[0]
                meta_path = os.path.join(UPLOADS_DIR, f"{stem}_meta.json")
                if os.path.exists(meta_path):
                    with open(meta_path) as f:
                        meta = json.load(f)
                    total_pages = meta.get("total_pages")
                    unreadable_pages = meta.get("unreadable_pages", [])
                else:
                    slides_dir = os.path.join(UPLOADS_DIR, f"{stem}_slides")
                    if os.path.exists(slides_dir):
                        for fname in sorted(os.listdir(slides_dir)):
                            if fname.startswith("page_") and fname.endswith(".png"):
                                try:
                                    unreadable_pages.append(int(fname[5:-4]))
                                except ValueError:
                                    pass

            yield f"data: {json.dumps({'type': 'done', 'chunks_processed': len(documents), 'total_pages': total_pages, 'unreadable_pages': unreadable_pages})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
