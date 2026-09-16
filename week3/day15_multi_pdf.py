import os
import anthropic
import pymupdf
import chromadb
from dotenv import load_dotenv

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

from sentence_transformers import SentenceTransformer

load_dotenv()

# ── Config ────────────────────────────────────────────────────

PDF_PATHS = [
    "data/pdfs/example_3.pptx",   # Parkinson's lecture
    "data/pdfs/example.pdf",       # resume (intentionally different topic)
]
CHUNK_SIZE = 200
CHUNK_OVERLAP = 30
COLLECTION_NAME = "multi_lectures"
DB_PATH = "./data/chroma_db"
N_RESULTS = 3

claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
embedder = SentenceTransformer("all-MiniLM-L6-v2")


# ── Text helpers ──────────────────────────────────────────────

def extract_text(pdf_path: str) -> str:
    doc = pymupdf.open(pdf_path)
    return "\n".join(page.get_text() for page in doc)


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    words = text.split()
    chunks, step = [], size - overlap
    for start in range(0, len(words), step):
        chunk = " ".join(words[start : start + size])
        if len(chunk.strip()) > 50:
            chunks.append(chunk)
    return chunks


def embed(texts: list[str]) -> list[list[float]]:
    return embedder.encode(texts, show_progress_bar=False).tolist()


# ── Indexing ──────────────────────────────────────────────────

def index_pdf(pdf_path: str, collection: chromadb.Collection) -> int:
    """Index one PDF — tag every chunk with its source filename."""
    filename = os.path.basename(pdf_path)

    # Skip if this PDF is already indexed
    existing = collection.get(where={"source": filename})
    if existing["ids"]:
        print(f"  [{filename}] already indexed ({len(existing['ids'])} chunks) — skipping")
        return len(existing["ids"])

    text = extract_text(pdf_path)
    if len(text.split()) < 50:
        print(f"  [{filename}] skipped — appears to be scanned (no text)")
        return 0

    chunks = chunk_text(text)
    embeddings = embed(chunks)
    ids = [f"{filename}_chunk_{i}" for i in range(len(chunks))]

    collection.add(
        documents=chunks,
        embeddings=embeddings,
        ids=ids,
        metadatas=[{
            "source": filename,
            "chunk_index": i,
        } for i in range(len(chunks))],
    )

    print(f"  [{filename}] indexed {len(chunks)} chunks")
    return len(chunks)


def index_all(pdf_paths: list[str], collection: chromadb.Collection) -> None:
    total = 0
    for path in pdf_paths:
        total += index_pdf(path, collection)
    print(f"\n  Total chunks in collection: {collection.count()}")


# ── RAG pipeline ──────────────────────────────────────────────

def retrieve(query: str, collection: chromadb.Collection, source_filter: str = None) -> list[dict]:
    """
    Retrieve top N chunks. Optionally filter by source PDF.
    source_filter = "example_3.pptx" to search only that file.
    """
    q_embedding = embed([query])[0]

    kwargs = dict(
        query_embeddings=[q_embedding],
        n_results=min(N_RESULTS, collection.count()),
        include=["documents", "distances", "metadatas"],
    )
    if source_filter:
        kwargs["where"] = {"source": source_filter}

    results = collection.query(**kwargs)

    return [
        {
            "text": doc,
            "score": round(1 - dist, 4),
            "source": meta.get("source", "unknown"),
        }
        for doc, dist, meta in zip(
            results["documents"][0],
            results["distances"][0],
            results["metadatas"][0],
        )
    ]


def generate(query: str, chunks: list[dict]) -> str:
    """Inject retrieved chunks and ask Claude to answer."""
    context = "\n\n---\n\n".join(
        f"[Source: {c['source']} | Relevance: {c['score']}]\n{c['text']}"
        for c in chunks
    )
    response = claude.messages.create(
        model="claude-opus-4-7",
        max_tokens=400,
        system="""You are a study assistant. Answer using ONLY the provided notes.
Cite the source filename for each key fact. If the answer is not in the notes, say so.""",
        messages=[{
            "role": "user",
            "content": f"Notes:\n{context}\n\nQuestion: {query}"
        }]
    )
    return response.content[0].text


def rag(query: str, collection: chromadb.Collection, source_filter: str = None) -> dict:
    chunks = retrieve(query, collection, source_filter)
    answer = generate(query, chunks)
    return {"query": query, "chunks": chunks, "answer": answer}


# ── Main ─────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("DAY 15 — MULTI-PDF SEARCH")
    print("=" * 60)

    # ── 1. Index all PDFs ────────────────────────────────────
    print("\nIndexing PDFs...")
    client = chromadb.PersistentClient(path=DB_PATH)
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    index_all(PDF_PATHS, collection)

    # ── 2. Show what's indexed ───────────────────────────────
    print("\n" + "=" * 60)
    print("INDEXED SOURCES")
    print("=" * 60)
    all_meta = collection.get(include=["metadatas"])
    source_counts: dict[str, int] = {}
    for meta in all_meta["metadatas"]:
        src = meta["source"]
        source_counts[src] = source_counts.get(src, 0) + 1
    for src, count in source_counts.items():
        print(f"  {src}: {count} chunks")

    # ── 3. Search across all PDFs ────────────────────────────
    print("\n" + "=" * 60)
    print("STEP 1 — SEARCH ACROSS ALL PDFS")
    print("=" * 60)

    questions = [
        "What causes Parkinson's disease?",
        "What is this person's work experience?",
        "What medications are used in treatment?",
    ]

    for question in questions:
        print(f"\nQ: {question}")
        chunks = retrieve(question, collection)
        print(f"Top {len(chunks)} results:")
        for i, c in enumerate(chunks, 1):
            preview = " ".join(c["text"].split()[:10])
            print(f"  #{i} (score: {c['score']}) [{c['source']}] \"{preview}...\"")

    # ── 4. Filter by source ──────────────────────────────────
    print("\n" + "=" * 60)
    print("STEP 2 — FILTER BY SPECIFIC PDF")
    print("=" * 60)
    print("\nSame question, filtered to Parkinson's file only:")
    query = "What causes Parkinson's disease?"
    print(f"Q: {query}")
    chunks = retrieve(query, collection, source_filter="example_3.pptx")
    for i, c in enumerate(chunks, 1):
        preview = " ".join(c["text"].split()[:10])
        print(f"  #{i} (score: {c['score']}) [{c['source']}] \"{preview}...\"")

    # ── 5. RAG with source citation ──────────────────────────
    print("\n" + "=" * 60)
    print("STEP 3 — RAG WITH SOURCE CITATION")
    print("=" * 60)

    question = "What causes Parkinson's disease and what is the treatment?"
    print(f"\nQ: {question}\n")
    result = rag(question, collection)

    print("Retrieved chunks:")
    for i, c in enumerate(result["chunks"], 1):
        preview = " ".join(c["text"].split()[:10])
        print(f"  #{i} (score: {c['score']}) [{c['source']}] \"{preview}...\"")

    print(f"\nClaude's answer:")
    print(f"  {result['answer']}")

    # ── 6. Key lesson ────────────────────────────────────────
    print("\n" + "=" * 60)
    print("WHAT MULTI-PDF SEARCH GIVES YOU")
    print("=" * 60)
    print("""
  Single collection, multiple sources:
  - One query searches ALL your PDFs at once
  - Each result tells you WHICH file it came from
  - Filter by source when you want one specific PDF
  - Scores tell you which PDF is most relevant to the query

  Medical question → Parkinson's file scores high
  Resume question  → resume file scores high
  ChromaDB figures out which source to use — you don't hardcode it

  Day 16 (Week 4): Wire this into a full RAG pipeline with
  better chunking, re-ranking, and a streaming API endpoint.
""")
    print("=" * 60)
    print("WEEK 3 COMPLETE — Embeddings & Semantic Search done.")
    print("Next: Week 4 — RAG Pipeline + Next.js Chat UI")
    print("=" * 60)


if __name__ == "__main__":
    main()
