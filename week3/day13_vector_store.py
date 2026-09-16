import os
import pymupdf
import chromadb
from dotenv import load_dotenv

# Tell HuggingFace to use cached model only — no network check needed
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

from sentence_transformers import SentenceTransformer

load_dotenv()

PDF_PATH = "data/pdfs/example_3.pptx"
CHUNK_SIZE = 200
CHUNK_OVERLAP = 30
COLLECTION_NAME = "lectures"
DB_PATH = "./data/chroma_db"

# Load a local neural embedding model — no API key, no network needed
# all-MiniLM-L6-v2: small, fast, good quality (downloads once ~90MB)
model = SentenceTransformer("all-MiniLM-L6-v2")


# ── Text helpers (same as Day 12) ─────────────────────────────

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


# ── Embedding ─────────────────────────────────────────────────

def embed(texts: list[str]) -> list[list[float]]:
    """Neural embeddings via sentence-transformers — runs locally, no API."""
    return model.encode(texts, show_progress_bar=False).tolist()


# ── ChromaDB helpers ──────────────────────────────────────────

def get_or_create_collection(db_path: str, name: str) -> chromadb.Collection:
    """
    PersistentClient saves the database to disk.
    Unlike Day 12's numpy array, this survives after the script ends.
    Same idea as localStorage in the browser vs an in-memory JS object.
    """
    client = chromadb.PersistentClient(path=db_path)
    return client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},  # use cosine similarity for search
    )


def index_pdf(pdf_path: str, collection: chromadb.Collection) -> list[str]:
    """Extract, chunk, embed, and store a PDF in ChromaDB."""
    text = extract_text(pdf_path)

    if len(text.split()) < 50:
        raise ValueError(f"PDF appears to be scanned — no text extracted: {pdf_path}")

    chunks = chunk_text(text)
    print(f"  Chunked into {len(chunks)} chunks")

    print(f"  Embedding {len(chunks)} chunks...")
    embeddings = embed(chunks)

    ids = [f"{os.path.basename(pdf_path)}_chunk_{i}" for i in range(len(chunks))]

    collection.add(
        documents=chunks,
        embeddings=embeddings,
        ids=ids,
        metadatas=[{"source": os.path.basename(pdf_path), "chunk_index": i} for i in range(len(chunks))],
    )

    print(f"  Stored {len(chunks)} chunks in ChromaDB")
    return chunks


def search(query: str, collection: chromadb.Collection, n_results: int = 3) -> dict:
    """Search the collection by meaning."""
    query_embedding = embed([query])[0]
    return collection.query(
        query_embeddings=[query_embedding],
        n_results=min(n_results, collection.count()),
        include=["documents", "distances", "metadatas"],
    )


# ── Main ─────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("DAY 13 — CHROMADB VECTOR STORE")
    print("=" * 60)
    print("Embedding model: all-MiniLM-L6-v2 (local, no API)")

    # ── 1. Set up ChromaDB ───────────────────────────────────
    print(f"\nConnecting to ChromaDB at: {DB_PATH}")
    collection = get_or_create_collection(DB_PATH, COLLECTION_NAME)
    print(f"  Collection '{COLLECTION_NAME}' ready")
    print(f"  Chunks already stored: {collection.count()}")

    # ── 2. Index the PDF ─────────────────────────────────────
    print(f"\nIndexing: {PDF_PATH}")
    chunks = index_pdf(PDF_PATH, collection)
    print(f"  Total chunks in collection: {collection.count()}")

    # ── 3. Search by query ───────────────────────────────────
    print("\n" + "=" * 60)
    print("STEP 1 — SEMANTIC SEARCH")
    print("=" * 60)

    queries = [
        "What causes Parkinson's disease?",
        "What are the symptoms of Parkinson's?",
        "How is Parkinson's treated?",
    ]

    for query in queries:
        print(f"\nQuery: \"{query}\"")
        results = search(query, collection, n_results=2)

        for i, (doc, distance) in enumerate(zip(
            results["documents"][0],
            results["distances"][0]
        )):
            similarity = 1 - distance   # ChromaDB returns distance, not similarity
            preview = " ".join(doc.split()[:20])
            source = results["metadatas"][0][i]["source"]
            print(f"  #{i+1} ({similarity:.4f}) [{source}]")
            print(f"       \"{preview}...\"")

    # ── 4. Show what's stored ────────────────────────────────
    print("\n" + "=" * 60)
    print("STEP 2 — INSPECT THE DATABASE")
    print("=" * 60)
    all_data = collection.get(include=["documents", "metadatas"])
    print(f"\nTotal chunks stored: {len(all_data['ids'])}")
    print("\nFirst 3 stored chunks:")
    for i in range(min(3, len(all_data["ids"]))):
        preview = " ".join(all_data["documents"][i].split()[:12])
        print(f"  [{all_data['ids'][i]}]")
        print(f"   \"{preview}...\"")

    # ── 5. Key differences from Day 12 ───────────────────────
    print("\n" + "=" * 60)
    print("DAY 12 vs DAY 13")
    print("=" * 60)
    print("""
  Day 12 (manual numpy):
    - Vectors stored in memory only — gone when script ends
    - Similarity computed in a Python loop over all chunks
    - TF-IDF vectors — keyword based
    - You wrote all the math yourself

  Day 13 (ChromaDB):
    - Vectors persisted to disk — survive after script ends
    - ChromaDB uses HNSW index — searches 10,000 chunks as fast as 10
    - Neural embeddings — understands meaning, not just keywords
    - One line to search: collection.query(...)

  HNSW = Hierarchical Navigable Small World
  A graph-based index that finds nearest neighbors without
  checking every single vector — same idea as a binary search
  tree vs scanning every row in a database.
""")

    print("=" * 60)
    print("WHAT'S NEXT — Day 14: Semantic Search")
    print("  Ask natural language questions, get answers from your PDFs.")
    print("  ChromaDB retrieves → Claude reads chunks → answers grounded in your docs.")
    print("=" * 60)


if __name__ == "__main__":
    main()
