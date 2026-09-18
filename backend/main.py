import os
import json
import asyncio
import tempfile
import shutil
import subprocess
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from pipeline import RAGPipeline

# ── Config from environment ───────────────────────────────────

DATA_DIR = os.getenv("DATA_DIR", os.path.join(os.path.dirname(__file__), "../data"))
UPLOADS_DIR = os.path.join(DATA_DIR, "uploads")
DB_PATH = os.path.join(DATA_DIR, "chroma_db")
SOFFICE = os.getenv("SOFFICE_PATH", "/usr/bin/soffice")

_raw_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001")
CORS_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(DB_PATH, exist_ok=True)


def convert_pptx_to_pdf(pptx_path: str) -> str:
    subprocess.run(
        [SOFFICE, "--headless", "--convert-to", "pdf", "--outdir", UPLOADS_DIR, pptx_path],
        check=True,
        capture_output=True,
    )
    pdf_name = os.path.splitext(os.path.basename(pptx_path))[0] + ".pdf"
    return os.path.join(UPLOADS_DIR, pdf_name)


# ── Startup / shutdown ────────────────────────────────────────

pipeline: RAGPipeline = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY environment variable is not set")
    global pipeline
    pipeline = RAGPipeline(collection_name="jawar", db_path=DB_PATH)
    print("RAG pipeline ready")
    yield
    print("Server shutting down")


# ── App ───────────────────────────────────────────────────────

app = FastAPI(
    title="Jawar API",
    description="RAG-powered study assistant API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response models ─────────────────────────────────

class HistoryMessage(BaseModel):
    role: str
    text: str


class AskRequest(BaseModel):
    query: str
    source_filter: str | None = None
    history: list[HistoryMessage] = []


class QuizRequest(BaseModel):
    source_filter: str | None = None
    difficulty: str = "Medium"
    topic: str | None = None
    chunk_index: int | None = None
    question_index: int | None = None


class EvidenceChunk(BaseModel):
    source: str
    score: float
    text: str


class QuizQuestion(BaseModel):
    question: str
    options: dict[str, str]
    correct: str
    explanation: str
    source: str
    difficulty: str
    topic: str
    question_type: str = "recall"
    evidence: list[EvidenceChunk] = []


class SummarizeRequest(BaseModel):
    source_filter: str | None = None


class SourceResult(BaseModel):
    source: str
    score: float
    preview: str


class AskResponse(BaseModel):
    query: str
    answer: str
    sources: list[SourceResult]


class IndexResponse(BaseModel):
    status: str
    source: str
    chunks: int
    message: str


class HealthResponse(BaseModel):
    status: str
    chunks_indexed: int
    sources: dict[str, int]


# ── Routes ────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(
        status="ok",
        chunks_indexed=pipeline.chunk_count(),
        sources=pipeline.list_sources(),
    )


@app.post("/index", response_model=IndexResponse)
async def index_pdf(file: UploadFile = File(...)):
    if not file.filename.lower().endswith((".pdf", ".pptx")):
        raise HTTPException(status_code=400, detail="Only PDF and PPTX files are supported")

    MAX_SIZE = 50 * 1024 * 1024
    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 50MB.")

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=os.path.splitext(file.filename)[1]
        ) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        named_path = os.path.join(os.path.dirname(tmp_path), file.filename)
        os.rename(tmp_path, named_path)
        tmp_path = named_path

        result = pipeline.index(tmp_path)
        result["source"] = file.filename
        saved_path = os.path.join(UPLOADS_DIR, file.filename)
        shutil.copy2(tmp_path, saved_path)
        if file.filename.lower().endswith(".pptx"):
            try:
                convert_pptx_to_pdf(saved_path)
            except Exception:
                pass
        return IndexResponse(**result)

    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Indexing failed: {str(e)}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@app.post("/index/stream")
async def index_pdf_stream(file: UploadFile = File(...)):
    if not file.filename.lower().endswith((".pdf", ".pptx")):
        raise HTTPException(status_code=400, detail="Only PDF and PPTX files are supported")

    MAX_SIZE = 50 * 1024 * 1024
    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 50MB.")

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=os.path.splitext(file.filename)[1]
        ) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        named_path = os.path.join(os.path.dirname(tmp_path), file.filename)
        os.rename(tmp_path, named_path)
        tmp_path = named_path
        saved_path = os.path.join(UPLOADS_DIR, file.filename)
        shutil.copy2(tmp_path, saved_path)
        if file.filename.lower().endswith(".pptx"):
            try:
                convert_pptx_to_pdf(saved_path)
            except Exception:
                pass
    except Exception as e:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise HTTPException(status_code=500, detail=str(e))

    async def event_stream():
        import pymupdf
        try:
            filename = file.filename
            existing = pipeline._collection.get(where={"source": filename})
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

            chunks = pipeline._chunk_text(full_text)
            embeddings = pipeline._embed(chunks)
            ids = [f"{filename}_chunk_{i}" for i in range(len(chunks))]
            pipeline._collection.add(
                documents=chunks,
                embeddings=embeddings,
                ids=ids,
                metadatas=[{"source": filename, "chunk_index": i} for i in range(len(chunks))],
            )
            yield f"data: {json.dumps({'type': 'done', 'source': filename, 'chunks': len(chunks), 'message': f'Indexed {len(chunks)} chunks', 'unreadable_pages': unreadable_pages})}\n\n"

            meta = {"total_pages": total_pages, "unreadable_pages": unreadable_pages}
            meta_path = os.path.join(UPLOADS_DIR, f"{os.path.splitext(filename)[0]}_meta.json")
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


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest):
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    if pipeline.chunk_count() == 0:
        raise HTTPException(status_code=400, detail="No PDFs indexed yet. Upload a PDF first.")

    try:
        result = pipeline.ask(request.query, request.source_filter)
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


@app.post("/topics")
def get_topics(request: SummarizeRequest):
    stem = os.path.splitext(request.source_filter or "")[0]
    topics_path = os.path.join(UPLOADS_DIR, f"{stem}_topics.json") if stem else None
    chunk_assign_path = os.path.join(UPLOADS_DIR, f"{stem}_topic_chunks.json") if stem else None

    if topics_path and chunk_assign_path and os.path.exists(topics_path) and os.path.exists(chunk_assign_path):
        with open(topics_path) as f:
            cached = json.load(f)
        if cached and isinstance(cached[0], dict) and "count" in cached[0]:
            return cached

    where_filter = {"source": request.source_filter} if request.source_filter else None
    if request.source_filter:
        result = pipeline._collection.get(
            where={"source": request.source_filter}, limit=10000,
            include=["documents", "metadatas"],
        )
    else:
        result = pipeline._collection.get(limit=10000, include=["documents", "metadatas"])

    if not result["documents"]:
        raise HTTPException(status_code=404, detail="No content found.")

    all_ids = result["ids"]
    total_chunks = len(all_ids)

    pairs = sorted(
        zip(result["ids"], result["documents"], result["metadatas"]),
        key=lambda x: x[2].get("chunk_index", 0),
    )
    sorted_ids = [p[0] for p in pairs]
    sorted_docs = [p[1] for p in pairs]
    id_to_index = {p[0]: p[2].get("chunk_index", 0) for p in pairs}

    step = max(1, total_chunks // 20)
    sampled = sorted_docs[::step][:20]
    context = "\n\n---\n\n".join(sampled)

    response = pipeline._claude.messages.create(
        model=pipeline.claude_model,
        max_tokens=400,
        messages=[{"role": "user", "content": f"""Identify the distinct major topics covered in these lecture notes.
Return ONLY a JSON array of short topic names (2–5 words each). List 5–15 topics maximum, ordered as they appear. Major sections only — not sub-points.

["Topic 1", "Topic 2", ...]

Notes:
{context}"""}],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    try:
        topic_names = json.loads(raw)
        if not isinstance(topic_names, list):
            raise ValueError("Expected array")
        topic_names = [t for t in topic_names if isinstance(t, str)]
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(status_code=500, detail="Could not extract topics. Try again.")

    if not topic_names:
        raise HTTPException(status_code=500, detail="No topics found.")

    chunk_best: dict[str, tuple[str, float]] = {}

    for topic in topic_names:
        query_result = pipeline._collection.query(
            query_texts=[topic],
            where=where_filter,
            n_results=min(total_chunks, 500),
            include=["distances"],
        )
        for chunk_id, distance in zip(query_result["ids"][0], query_result["distances"][0]):
            score = 1.0 / (1.0 + float(distance))
            if chunk_id not in chunk_best or score > chunk_best[chunk_id][1]:
                chunk_best[chunk_id] = (topic, score)

    for chunk_id in all_ids:
        if chunk_id not in chunk_best:
            chunk_best[chunk_id] = (topic_names[0], 0.0)

    topic_chunks: dict[str, list[str]] = {t: [] for t in topic_names}
    for chunk_id, (topic, _) in chunk_best.items():
        topic_chunks[topic].append(chunk_id)
    for topic in topic_chunks:
        topic_chunks[topic].sort(key=lambda cid: id_to_index.get(cid, 0))

    result_list = [
        {"topic": t, "count": len(ids)}
        for t, ids in topic_chunks.items()
        if ids
    ]

    if topics_path:
        with open(topics_path, "w") as f:
            json.dump(result_list, f)
    if chunk_assign_path:
        with open(chunk_assign_path, "w") as f:
            json.dump(topic_chunks, f)

    return result_list


@app.get("/sources")
def list_sources():
    return {
        "sources": pipeline.list_sources(),
        "total_chunks": pipeline.chunk_count(),
    }


@app.get("/files/{filename}")
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


@app.get("/files/{filename}/slides/{page_num}")
def get_slide_image(filename: str, page_num: int):
    stem = os.path.splitext(filename)[0]
    path = os.path.join(UPLOADS_DIR, f"{stem}_slides", f"page_{page_num}.png")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Slide {page_num} not found for '{filename}'")
    return FileResponse(path, media_type="image/png")


@app.delete("/sources/{filename}")
def delete_source(filename: str):
    existing = pipeline._collection.get(where={"source": filename})
    if not existing["ids"]:
        raise HTTPException(status_code=404, detail=f"'{filename}' not found in index")
    pipeline._collection.delete(where={"source": filename})
    return {"status": "deleted", "source": filename, "chunks_removed": len(existing["ids"])}


@app.post("/quiz", response_model=QuizQuestion)
def generate_quiz(request: QuizRequest):
    import random

    if pipeline.chunk_count() == 0:
        raise HTTPException(status_code=400, detail="No PDFs indexed yet.")

    if request.question_index is not None and request.source_filter and request.topic:
        stem = os.path.splitext(request.source_filter)[0]
        questions_path = os.path.join(UPLOADS_DIR, f"{stem}_questions.json")
        topic_questions_path = os.path.join(UPLOADS_DIR, f"{stem}_topic_questions.json")
        if os.path.exists(questions_path) and os.path.exists(topic_questions_path):
            with open(questions_path) as f:
                all_questions = json.load(f)
            with open(topic_questions_path) as f:
                topic_questions = json.load(f)
            topic_indices = topic_questions.get(request.topic, [])
            if request.question_index < len(topic_indices):
                global_idx = topic_indices[request.question_index]
                if global_idx < len(all_questions):
                    q = all_questions[global_idx]
                    return QuizQuestion(
                        question=q["question"],
                        options=q["options"],
                        correct=q["correct"],
                        explanation=q["explanation"],
                        source=q["source"],
                        difficulty=q.get("difficulty", "Medium"),
                        topic=q["topic"],
                        question_type=q.get("question_type", "recall"),
                        evidence=[EvidenceChunk(**e) for e in q.get("evidence", [])],
                    )

    context = None
    source = None
    evidence_chunks = []

    if request.chunk_index is not None and request.topic and request.source_filter:
        stem = os.path.splitext(request.source_filter)[0]
        chunk_assign_path = os.path.join(UPLOADS_DIR, f"{stem}_topic_chunks.json")
        if os.path.exists(chunk_assign_path):
            with open(chunk_assign_path) as f:
                topic_chunks = json.load(f)
            chunk_ids = topic_chunks.get(request.topic, [])
            if request.chunk_index < len(chunk_ids):
                chunk_id = chunk_ids[request.chunk_index]
                chunk_result = pipeline._collection.get(ids=[chunk_id], include=["documents", "metadatas"])
                if chunk_result["documents"]:
                    context = chunk_result["documents"][0]
                    source = chunk_result["metadatas"][0].get("source", request.source_filter)
                    evidence_chunks = [{"source": source, "score": 1.0, "text": context}]

    if context is None:
        query = request.topic if request.topic else random.choice([
            "key concept", "important fact", "mechanism", "treatment",
            "diagnosis", "cause", "symptom", "definition"
        ])
        chunks = pipeline._retrieve(query, request.source_filter)
        if not chunks:
            raise HTTPException(status_code=404, detail="No content found.")
        context = "\n\n---\n\n".join(
            f"[Source: {c['source']}]\n{c['text']}" for c in chunks
        )
        source = chunks[0]["source"]
        evidence_chunks = chunks

    difficulty_guide = {
        "Easy":   "straightforward recall, 75–90% of students would answer correctly",
        "Medium": "requires understanding and application, 50–70% would answer correctly",
        "Hard":   "requires synthesis and clinical reasoning, 25–45% would answer correctly",
    }
    diff_hint = difficulty_guide.get(request.difficulty, difficulty_guide["Medium"])
    topic_line = f"Focus the question specifically on: {request.topic}." if request.topic else ""

    prompt = f"""You are a medical exam question writer.

Based ONLY on the notes below, generate ONE {request.difficulty}-level multiple choice question.
{request.difficulty} means: {diff_hint}.
{topic_line}

Return ONLY valid JSON — no markdown, no explanation outside the JSON:
{{
  "question": "...",
  "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
  "correct": "A",
  "explanation": "One sentence citing the exact note that supports the answer.",
  "difficulty": "{request.difficulty}",
  "topic": "Short concept name (2–4 words) that this question tests"
}}

Rules:
- Correct answer must be directly supported by the notes
- Distractors must be plausible but wrong
- Do not use options like "All of the above"
- Return ONLY the JSON object

Notes:
{context}"""

    response = pipeline._claude.messages.create(
        model=pipeline.claude_model,
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Claude returned invalid JSON. Try again.")

    return QuizQuestion(
        question=data["question"],
        options=data["options"],
        correct=data["correct"],
        explanation=data["explanation"],
        source=source,
        difficulty=data.get("difficulty", request.difficulty),
        topic=data.get("topic", "General"),
        evidence=[EvidenceChunk(source=c["source"], score=c["score"], text=c["text"]) for c in evidence_chunks],
    )


@app.post("/questions/stream")
async def generate_questions_stream(request: SummarizeRequest):
    if not request.source_filter:
        raise HTTPException(status_code=400, detail="source_filter is required")

    stem = os.path.splitext(request.source_filter)[0]
    questions_path = os.path.join(UPLOADS_DIR, f"{stem}_questions.json")
    topic_questions_path = os.path.join(UPLOADS_DIR, f"{stem}_topic_questions.json")
    chunk_assign_path = os.path.join(UPLOADS_DIR, f"{stem}_topic_chunks.json")

    async def event_stream():
        try:
            if os.path.exists(questions_path) and os.path.exists(topic_questions_path):
                with open(questions_path) as f:
                    questions = json.load(f)
                with open(topic_questions_path) as f:
                    topic_questions = json.load(f)
                plans = [{"topic": t, "count": len(idxs)} for t, idxs in topic_questions.items() if idxs]
                yield f"data: {json.dumps({'type': 'done', 'count': len(questions), 'plans': plans})}\n\n"
                return

            if not os.path.exists(chunk_assign_path):
                yield f"data: {json.dumps({'type': 'error', 'message': 'Load topics first before generating questions.'})}\n\n"
                return

            with open(chunk_assign_path) as f:
                topic_chunks = json.load(f)

            all_pairs: list[tuple[str, str]] = []
            for topic, chunk_ids in topic_chunks.items():
                for cid in chunk_ids:
                    all_pairs.append((cid, topic))

            total = len(all_pairs)
            all_questions: list[dict] = []
            topic_question_map: dict[str, list[int]] = {t: [] for t in topic_chunks.keys()}

            for i, (chunk_id, topic) in enumerate(all_pairs):
                yield f"data: {json.dumps({'type': 'progress', 'current': i + 1, 'total': total, 'message': f'Generating questions for chunk {i + 1} of {total}…'})}\n\n"
                await asyncio.sleep(0)

                chunk_result = pipeline._collection.get(ids=[chunk_id], include=["documents", "metadatas"])
                if not chunk_result["documents"]:
                    continue

                chunk_text = chunk_result["documents"][0]
                source = chunk_result["metadatas"][0].get("source", request.source_filter)

                prompt = f"""You are a medical educator creating questions that build genuine understanding — not surface memorisation.

Read this lecture content and generate a comprehensive set of multiple-choice questions. The goal: a student who answers all of these correctly should understand the material deeply enough to answer any exam question on this topic, even ones phrased differently.

For each key concept, vary the question type:
- **Recall** — "What is the definition / value / name of X?" (1 per concept, keep brief)
- **Mechanism** — "Why does X happen?" / "What is the underlying process that causes Y?"
- **Application** — "A patient presents with [signs from the notes]. What is the most likely explanation?"
- **Comparison** — "What is the key difference between X and Y?" (when multiple similar concepts exist)
- **Consequence** — "What happens if X is left untreated?" / "What is the result of Y?"
- **Integration** — "How does concept X contribute to condition Y?"

Rules:
- Cover every distinct concept — do NOT skip any
- Generate 1 question for minor points, 2–4 for rich or complex sections
- Every question must be directly supported by the lecture text — no outside knowledge
- No duplicate questions within this response
- Distractors must be plausible but clearly wrong based on the notes
- Each question must have exactly 4 options (A, B, C, D)
- Do not use "All of the above" or "None of the above"
- Explanation must state the underlying reason, not just repeat the answer
- Return ONLY a JSON array — no markdown, no preamble

Format:
[
  {{
    "question": "...",
    "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
    "correct": "A",
    "explanation": "Explain WHY this is correct — the mechanism or reasoning, not just what the slide says.",
    "difficulty": "Easy|Medium|Hard",
    "question_type": "recall|mechanism|application|comparison|consequence|integration"
  }}
]

Topic area: {topic}

Lecture content:
{chunk_text}"""

                try:
                    response = pipeline._claude.messages.create(
                        model=pipeline.claude_model,
                        max_tokens=2000,
                        messages=[{"role": "user", "content": prompt}],
                    )
                    raw = response.content[0].text.strip()
                    if raw.startswith("```"):
                        raw = raw.split("```")[1]
                        if raw.startswith("json"):
                            raw = raw[4:]
                    questions_batch = json.loads(raw)
                    if not isinstance(questions_batch, list):
                        questions_batch = []
                except Exception:
                    questions_batch = []

                for q in questions_batch:
                    if not isinstance(q, dict) or not q.get("question"):
                        continue
                    q_index = len(all_questions)
                    all_questions.append({
                        "question": q.get("question", ""),
                        "options": q.get("options", {}),
                        "correct": q.get("correct", "A"),
                        "explanation": q.get("explanation", ""),
                        "difficulty": q.get("difficulty", "Medium"),
                        "question_type": q.get("question_type", "recall"),
                        "topic": topic,
                        "source": source,
                        "evidence": [{"source": source, "score": 1.0, "text": chunk_text}],
                    })
                    topic_question_map[topic].append(q_index)

            with open(questions_path, "w") as f:
                json.dump(all_questions, f)
            with open(topic_questions_path, "w") as f:
                json.dump(topic_question_map, f)

            plans = [{"topic": t, "count": len(idxs)} for t, idxs in topic_question_map.items() if idxs]
            yield f"data: {json.dumps({'type': 'done', 'count': len(all_questions), 'plans': plans})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/summarize/stream")
async def summarize_stream(request: SummarizeRequest):
    if request.source_filter:
        result = pipeline._collection.get(
            where={"source": request.source_filter}, limit=10000,
            include=["documents", "metadatas"],
        )
    else:
        result = pipeline._collection.get(limit=10000, include=["documents", "metadatas"])

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
                response = pipeline._claude.messages.create(
                    model=pipeline.claude_model,
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

            with pipeline._claude.messages.stream(
                model=pipeline.claude_model,
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


@app.post("/ask/stream")
async def ask_stream(request: AskRequest):
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    if pipeline.chunk_count() == 0:
        raise HTTPException(status_code=400, detail="No PDFs indexed yet. Upload a PDF first.")

    chunks = pipeline._retrieve(request.query, request.source_filter)

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
            with pipeline._claude.messages.stream(
                model=pipeline.claude_model,
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
