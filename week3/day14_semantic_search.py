import os
import anthropic
import pymupdf
import chromadb
from dotenv import load_dotenv

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

from sentence_transformers import SentenceTransformer

load_dotenv()

PDF_PATH = "data/pdfs/example_3.pptx"
CHUNK_SIZE = 200
CHUNK_OVERLAP = 30
COLLECTION_NAME = "lectures"
DB_PATH = "./data/chroma_db"
EMBED_MODEL = "all-MiniLM-L6-v2"
N_RESULTS = 2   # how many chunks to retrieve per query

claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
embedder = SentenceTransformer(EMBED_MODEL)


# ── Text helpers (same as Day 13) ─────────────────────────────

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


# ── ChromaDB ──────────────────────────────────────────────────

def get_collection() -> chromadb.Collection:
    client = chromadb.PersistentClient(path=DB_PATH)
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def index_pdf_if_empty(pdf_path: str, collection: chromadb.Collection) -> None:
    """Index the PDF only if the collection is empty."""
    if collection.count() > 0:
        print(f"  Collection already has {collection.count()} chunks — skipping indexing")
        return

    text = extract_text(pdf_path)
    if len(text.split()) < 50:
        raise ValueError("PDF appears to be scanned — no text extracted")

    chunks = chunk_text(text)
    embeddings = embed(chunks)
    ids = [f"{os.path.basename(pdf_path)}_chunk_{i}" for i in range(len(chunks))]

    collection.add(
        documents=chunks,
        embeddings=embeddings,
        ids=ids,
        metadatas=[{"source": os.path.basename(pdf_path), "chunk_index": i} for i in range(len(chunks))],
    )
    print(f"  Indexed {len(chunks)} chunks into ChromaDB")


# ── RAG pipeline ──────────────────────────────────────────────

def retrieve(query: str, collection: chromadb.Collection) -> list[dict]:
    """Step 1 — find the most relevant chunks for the query."""
    q_embedding = embed([query])[0]
    results = collection.query(
        query_embeddings=[q_embedding],
        n_results=min(N_RESULTS, collection.count()),
        include=["documents", "distances", "metadatas"],
    )
    chunks = []
    for doc, distance, meta in zip(
        results["documents"][0],
        results["distances"][0],
        results["metadatas"][0],
    ):
        chunks.append({
            "text": doc,
            "score": round(1 - distance, 4),
            "source": meta.get("source", "unknown"),
        })
    return chunks


def generate(query: str, chunks: list[dict]) -> str:
    """Step 2 — inject retrieved chunks into the prompt and ask Claude."""
    context = "\n\n---\n\n".join(
        f"[Source: {c['source']} | Relevance: {c['score']}]\n{c['text']}"
        for c in chunks
    )

    response = claude.messages.create(
        model="claude-opus-4-7",
        max_tokens=512,
        system="""You are a study assistant. Answer the student's question using ONLY
the provided lecture notes. Be concise and accurate. If the answer is not
in the notes, say so clearly — do not guess.""",
        messages=[{
            "role": "user",
            "content": f"""Here are the relevant lecture notes:

{context}

Question: {query}"""
        }]
    )
    return response.content[0].text


def rag(query: str, collection: chromadb.Collection) -> dict:
    """
    Full RAG pipeline:
    Retrieve → Augment prompt → Generate answer

    This is the same pattern used in ge-ai-chatbot's search_related_topics:
    call a retrieval service → inject results → Claude answers
    """
    chunks = retrieve(query, collection)
    answer = generate(query, chunks)
    return {"query": query, "chunks": chunks, "answer": answer}


# ── Main ─────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("DAY 14 — SEMANTIC SEARCH + RAG")
    print("=" * 60)
    print("Retrieve → Augment → Generate\n")

    # ── 1. Connect to ChromaDB ───────────────────────────────
    collection = get_collection()
    print(f"Connected to ChromaDB: '{COLLECTION_NAME}'")
    index_pdf_if_empty(PDF_PATH, collection)

    # ── 2. Run RAG on several questions ─────────────────────
    questions = [
        "What causes Parkinson's disease?",
        "Why can't we treat Parkinson's with dopamine directly?",
        "What medications are contraindicated in Parkinson's patients?",
        "What do Parkinson's, strokes, and Alzheimer's have in common?",
    ]

    for question in questions:
        print("\n" + "=" * 60)
        result = rag(question, collection)

        print(f"Q: {result['query']}")
        print(f"\nRetrieved {len(result['chunks'])} chunks:")
        for i, chunk in enumerate(result['chunks'], 1):
            preview = " ".join(chunk['text'].split()[:12])
            print(f"  #{i} (score: {chunk['score']}) \"{preview}...\"")

        print(f"\nClaude's answer:")
        print(f"  {result['answer']}")

    # ── 3. Show the RAG flow clearly ────────────────────────
    print("\n" + "=" * 60)
    print("THE RAG LOOP — WHAT JUST HAPPENED")
    print("=" * 60)
    print("""
  For each question:

  1. RETRIEVE  — embed the question → search ChromaDB
                 → get top 2 most similar chunks

  2. AUGMENT   — build a prompt:
                 "Here are the lecture notes: [chunks]
                  Question: [your question]"

  3. GENERATE  — send augmented prompt to Claude
                 → Claude answers using ONLY the notes
                 → no hallucination, grounded in your PDF

  This is exactly what ge-ai-chatbot does with Endor:
    search_related_topics() = your retrieve() function
    The system prompt + context = your augment step
    Claude = the same generate step
""")

    print("=" * 60)
    print("WHAT'S NEXT — Day 15: Search Across Multiple PDFs")
    print("  Index 2+ PDFs into the same collection.")
    print("  Each answer cites which PDF it came from.")
    print("  That's the last piece before the full RAG pipeline.")
    print("=" * 60)


if __name__ == "__main__":
    main()
