import os
import json

from fastapi import APIRouter, HTTPException

import state
from config import UPLOADS_DIR
from models import SummarizeRequest

router = APIRouter()


@router.post("/topics")
def get_topics(request: SummarizeRequest):
    stem = os.path.splitext(request.source_filter or "")[0]
    topics_path = os.path.join(UPLOADS_DIR, f"{stem}_topics.json") if stem else None
    chunk_assign_path = os.path.join(UPLOADS_DIR, f"{stem}_topic_chunks.json") if stem else None

    if not request.force and topics_path and chunk_assign_path and os.path.exists(topics_path) and os.path.exists(chunk_assign_path):
        with open(topics_path) as f:
            cached = json.load(f)
        if cached and isinstance(cached[0], dict) and "count" in cached[0]:
            return cached

    where_filter = {"source": request.source_filter} if request.source_filter else None
    if request.source_filter:
        result = state.pipeline._collection.get(
            where={"source": request.source_filter}, limit=10000,
            include=["documents", "metadatas"],
        )
    else:
        result = state.pipeline._collection.get(limit=10000, include=["documents", "metadatas"])

    if not result["documents"]:
        raise HTTPException(status_code=404, detail="No content found.")

    all_ids = result["ids"]
    total_chunks = len(all_ids)

    pairs = sorted(
        zip(result["ids"], result["documents"], result["metadatas"]),
        key=lambda x: x[2].get("chunk_index", 0),
    )
    sorted_docs = [p[1] for p in pairs]
    id_to_index = {p[0]: p[2].get("chunk_index", 0) for p in pairs}

    step = max(1, total_chunks // 20)
    sampled = sorted_docs[::step][:20]
    context = "\n\n---\n\n".join(sampled)

    response = state.pipeline._claude.messages.create(
        model=state.pipeline.claude_model,
        max_tokens=600,
        messages=[{"role": "user", "content": f"""Identify the distinct topics or sections in this document.
Return ONLY a JSON array of short topic names (2–5 words each). List 3–15 topics, ordered as they appear.

Rules:
- If this is a resume: list EACH job role as its own topic (e.g. "Apple Sr Engineer 2025", "Google SWE 2022"), plus top-level sections like Skills and Education. Do NOT merge multiple roles into one generic "Work Experience" entry.
- If these are lecture notes or study material: list major subject areas or concepts.

["Topic 1", "Topic 2", ...]

Document:
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
        query_result = state.pipeline._collection.query(
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
