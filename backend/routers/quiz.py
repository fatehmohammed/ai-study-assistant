import os
import json
import random

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import asyncio

import state
from config import UPLOADS_DIR
from models import EvidenceChunk, QuizQuestion, QuizRequest, SummarizeRequest

router = APIRouter()


@router.post("/quiz", response_model=QuizQuestion)
def generate_quiz(request: QuizRequest):
    if state.pipeline.chunk_count() == 0:
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
                    retrieved = state.pipeline._retrieve(q["question"], request.source_filter)
                    evidence = [
                        EvidenceChunk(source=c["source"], score=c["score"], text=c["text"])
                        for c in retrieved
                    ]
                    return QuizQuestion(
                        question=q["question"],
                        options=q["options"],
                        correct=q["correct"],
                        explanation=q["explanation"],
                        source=q["source"],
                        difficulty=q.get("difficulty", "Medium"),
                        topic=q["topic"],
                        question_type=q.get("question_type", "recall"),
                        evidence=evidence,
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
                chunk_result = state.pipeline._collection.get(ids=[chunk_id], include=["documents", "metadatas"])
                if chunk_result["documents"]:
                    context = chunk_result["documents"][0]
                    source = chunk_result["metadatas"][0].get("source", request.source_filter)
                    evidence_chunks = [{"source": source, "score": 1.0, "text": context}]

    if context is None:
        query = request.topic if request.topic else random.choice([
            "key concept", "important fact", "mechanism", "treatment",
            "diagnosis", "cause", "symptom", "definition"
        ])
        chunks = state.pipeline._retrieve(query, request.source_filter)
        if not chunks:
            raise HTTPException(status_code=404, detail="No content found.")
        context = "\n\n---\n\n".join(f"[Source: {c['source']}]\n{c['text']}" for c in chunks)
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

    response = state.pipeline._claude.messages.create(
        model=state.pipeline.claude_model,
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


@router.post("/questions/stream")
async def generate_questions_stream(request: SummarizeRequest):
    if not request.source_filter:
        raise HTTPException(status_code=400, detail="source_filter is required")

    stem = os.path.splitext(request.source_filter)[0]
    questions_path = os.path.join(UPLOADS_DIR, f"{stem}_questions.json")
    topic_questions_path = os.path.join(UPLOADS_DIR, f"{stem}_topic_questions.json")
    chunk_assign_path = os.path.join(UPLOADS_DIR, f"{stem}_topic_chunks.json")

    async def event_stream():
        try:
            if not request.force and os.path.exists(questions_path) and os.path.exists(topic_questions_path):
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

            topics = list(topic_chunks.keys())
            total_topics = len(topics)
            all_questions: list[dict] = []
            topic_question_map: dict[str, list[int]] = {t: [] for t in topics}

            for topic_idx, topic in enumerate(topics):
                chunk_ids = topic_chunks.get(topic, [])
                if not chunk_ids:
                    continue

                yield f"data: {json.dumps({'type': 'progress', 'current': topic_idx + 1, 'total': total_topics, 'message': f'Generating questions for topic {topic_idx + 1} of {total_topics}: {topic}…'})}\n\n"
                await asyncio.sleep(0)

                chunk_texts = []
                source = request.source_filter
                for chunk_id in chunk_ids:
                    chunk_result = state.pipeline._collection.get(ids=[chunk_id], include=["documents", "metadatas"])
                    if chunk_result["documents"]:
                        chunk_texts.append(chunk_result["documents"][0])
                        source = chunk_result["metadatas"][0].get("source", request.source_filter)

                if not chunk_texts:
                    continue

                topic_content = "\n\n---\n\n".join(chunk_texts)
                target_questions = min(max(len(chunk_texts), len(chunk_texts) * 3), 30)

                prompt = f"""You are a medical educator building an exam question bank for the topic: **{topic}**

The lecture content below is divided into sections separated by "---". Each section represents one page or slide.

Work in two steps:

**Step 1 — Identify testable concepts per section**
For EACH section, list every distinct concept worth testing. Note the section number. You MUST cover every section — do not skip any.

**Step 2 — Generate questions**
For the concepts you identified, generate multiple-choice questions using this distribution:
- **Recall** (25%) — definitions, values, names, classifications
- **Mechanism** (15%) — why/how a process works
- **Application** (25%) — patient presents with X, what is most likely / what do you do
- **Comparison** (10%) — key difference between X and Y (only when two similar concepts exist)
- **Consequence** (10%) — what happens if untreated / result of Y
- **Integration** (15%) — how concept X connects to or causes concept Y

Rules:
- Generate at LEAST 1 question per section — every section must have at least one question
- Generate at most ONE question per distinct concept — do not test the same concept twice
- Target approximately {target_questions} questions total, scaled to content richness
- Every question must be directly supported by the lecture text — no outside knowledge
- Each question must have exactly 4 options (A, B, C, D)
- Do not use "All of the above" or "None of the above"
- Distractors must be plausible but clearly wrong based on the notes
- Explanation must state the underlying reason — not just repeat the answer
- Return ONLY a JSON array — no markdown, no Step 1 output, no preamble

Format:
[
  {{
    "question": "...",
    "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
    "correct": "A",
    "explanation": "Explain WHY — the mechanism or reasoning.",
    "difficulty": "Easy|Medium|Hard",
    "question_type": "recall|mechanism|application|comparison|consequence|integration"
  }}
]

Lecture content for topic "{topic}":
{topic_content}"""

                try:
                    response = state.pipeline._claude.messages.create(
                        model=state.pipeline.claude_model,
                        max_tokens=4000,
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
                        "evidence": [{"source": source, "score": 1.0, "text": topic_content[:500]}],
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
