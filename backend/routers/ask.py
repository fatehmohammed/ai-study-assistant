import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

import state
from models import AskRequest, AskResponse, SourceResult

router = APIRouter()


@router.post("/ask", response_model=AskResponse)
def ask(request: AskRequest):
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    if state.pipeline.chunk_count() == 0:
        raise HTTPException(status_code=400, detail="No PDFs indexed yet. Upload a PDF first.")

    try:
        result = state.pipeline.ask(request.query, request.source_filter)
        return AskResponse(
            query=result.query,
            answer=result.answer,
            sources=[SourceResult(**s) for s in result.sources],
        )
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=429, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")


@router.post("/ask/stream")
async def ask_stream(request: AskRequest):
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    if state.pipeline.chunk_count() == 0:
        raise HTTPException(status_code=400, detail="No PDFs indexed yet. Upload a PDF first.")

    chunks = state.pipeline._retrieve(request.query, request.source_filter)
    if not chunks:
        raise HTTPException(status_code=404, detail="No relevant content found for that query.")

    async def event_stream():
        sources = [
            {
                "source": c["source"],
                "score": c["score"],
                "preview": " ".join(c["text"].split()[:12]) + "...",
            }
            for c in chunks
        ]
        yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"

        context = "\n\n---\n\n".join(
            f"[Source: {c['source']} | Relevance: {c['score']}]\n{c['text']}"
            for c in chunks
        )

        claude_messages = [
            {"role": "user", "content": f"Notes:\n{context}\n\nQuestion: {request.history[0].text if request.history else request.query}"},
        ]
        if request.history:
            for i, msg in enumerate(request.history):
                if i == 0:
                    claude_messages.append({"role": "assistant", "content": "(acknowledged)"})
                    continue
                claude_messages.append({"role": msg.role, "content": msg.text})
            claude_messages.append({"role": "user", "content": request.query})

        try:
            with state.pipeline._claude.messages.stream(
                model=state.pipeline.claude_model,
                max_tokens=512,
                system="""You are a study assistant. Answer using ONLY the provided
lecture notes. Cite the source filename for each key fact.
If the answer is not in the notes, say so clearly — do not guess.""",
                messages=claude_messages,
            ) as stream:
                for text in stream.text_stream:
                    yield f"data: {json.dumps({'type': 'token', 'text': text})}\n\n"
                    await asyncio.sleep(0)
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            return

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
