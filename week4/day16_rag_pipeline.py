import os
import anthropic
import pymupdf
import chromadb
from dataclasses import dataclass
from dotenv import load_dotenv

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

from sentence_transformers import SentenceTransformer

load_dotenv()


# ── Result type ───────────────────────────────────────────────

@dataclass
class RAGResult:
    """
    Structured return type from pipeline.ask()
    — same idea as a TypeScript interface.

    Instead of returning a plain string you get:
      result.answer   — Claude's response
      result.sources  — which files/chunks were used
      result.query    — the original question
    """
    query: str
    answer: str
    sources: list[dict]   # [{"source": filename, "score": float, "preview": str}]


# ── Pipeline class ────────────────────────────────────────────

class RAGPipeline:
    """
    Full RAG pipeline in one reusable class.

    Usage:
        pipeline = RAGPipeline()
        pipeline.index("data/pdfs/lecture.pdf")
        result = pipeline.ask("What causes Parkinson's?")
        print(result.answer)
        print(result.sources)
    """

    def __init__(
        self,
        db_path: str = "./data/chroma_db",
        collection_name: str = "jawar",
        embed_model: str = "all-MiniLM-L6-v2",
        claude_model: str = "claude-opus-4-7",
        chunk_size: int = 200,
        chunk_overlap: int = 30,
        n_results: int = 3,
    ):
        self.db_path = db_path
        self.collection_name = collection_name
        self.claude_model = claude_model
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.n_results = n_results

        self._claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self._embedder = SentenceTransformer(embed_model)
        self._collection = self._get_collection()

    # ── Setup ─────────────────────────────────────────────────

    def _get_collection(self) -> chromadb.Collection:
        client = chromadb.PersistentClient(path=self.db_path)
        return client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    # ── Text helpers ──────────────────────────────────────────

    def _extract_text(self, pdf_path: str) -> str:
        doc = pymupdf.open(pdf_path)
        pages_text = []
        for page in doc:
            text = page.get_text()
            if len(text.split()) < 10:
                # Page has little text — likely scanned, try OCR
                tp = page.get_textpage_ocr(flags=3, language="eng", dpi=300)
                text = page.get_text(textpage=tp)
            pages_text.append(text)
        return "\n".join(pages_text)

    def _chunk_text(self, text: str) -> list[str]:
        words = text.split()
        chunks, step = [], self.chunk_size - self.chunk_overlap
        for start in range(0, len(words), step):
            chunk = " ".join(words[start : start + self.chunk_size])
            if len(chunk.strip()) > 50:
                chunks.append(chunk)
        return chunks

    def _embed(self, texts: list[str]) -> list[list[float]]:
        return self._embedder.encode(texts, show_progress_bar=False).tolist()

    # ── Public API ────────────────────────────────────────────

    def index(self, pdf_path: str) -> dict:
        """
        Index a PDF into ChromaDB.
        Safe to call multiple times — skips if already indexed.
        Returns a summary of what happened.
        """
        filename = os.path.basename(pdf_path)

        # ⚠️ Edge case: file doesn't exist
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        # ⚠️ Edge case: already indexed — skip, don't duplicate
        existing = self._collection.get(where={"source": filename})
        if existing["ids"]:
            return {
                "status": "skipped",
                "source": filename,
                "chunks": len(existing["ids"]),
                "message": "Already indexed",
            }

        text = self._extract_text(pdf_path)

        # ⚠️ Edge case: scanned PDF with no text even after OCR
        if len(text.split()) < 20:
            raise ValueError(
                f"'{filename}' appears to be a scanned PDF — no text could be extracted. "
                "Use a text-based PDF."
            )

        chunks = self._chunk_text(text)
        embeddings = self._embed(chunks)
        ids = [f"{filename}_chunk_{i}" for i in range(len(chunks))]

        self._collection.add(
            documents=chunks,
            embeddings=embeddings,
            ids=ids,
            metadatas=[{
                "source": filename,
                "chunk_index": i,
            } for i in range(len(chunks))],
        )

        return {
            "status": "indexed",
            "source": filename,
            "chunks": len(chunks),
            "message": f"Indexed {len(chunks)} chunks",
        }

    def ask(self, query: str, source_filter: str = None) -> RAGResult:
        """
        Full RAG: retrieve relevant chunks → ask Claude → return result.

        query         — the user's question
        source_filter — optional filename to search only one PDF
        """
        # ⚠️ Edge case: empty query
        if not query.strip():
            raise ValueError("Query cannot be empty")

        # ── Retrieve ──────────────────────────────────────────
        chunks = self._retrieve(query, source_filter)

        # ⚠️ Edge case: nothing indexed yet
        if not chunks:
            return RAGResult(
                query=query,
                answer="No relevant content found. Make sure you have indexed at least one PDF first.",
                sources=[],
            )

        # ── Generate ──────────────────────────────────────────
        try:
            answer = self._generate(query, chunks)
        except anthropic.APIConnectionError:
            raise ConnectionError("Could not reach Claude API. Check your internet connection.")
        except anthropic.AuthenticationError:
            raise ValueError("Invalid ANTHROPIC_API_KEY. Check your .env file.")
        except anthropic.RateLimitError:
            raise RuntimeError("Claude API rate limit hit. Wait a moment and try again.")

        sources = [
            {
                "source": c["source"],
                "score": c["score"],
                "preview": " ".join(c["text"].split()[:12]) + "...",
            }
            for c in chunks
        ]

        return RAGResult(query=query, answer=answer, sources=sources)

    def list_sources(self) -> dict[str, int]:
        """Return all indexed PDFs and their chunk counts."""
        all_meta = self._collection.get(include=["metadatas"])
        counts: dict[str, int] = {}
        for meta in all_meta["metadatas"]:
            src = meta["source"]
            counts[src] = counts.get(src, 0) + 1
        return counts

    def chunk_count(self) -> int:
        return self._collection.count()

    # ── Private helpers ───────────────────────────────────────

    def _retrieve(self, query: str, source_filter: str = None) -> list[dict]:
        if self._collection.count() == 0:
            return []

        # Count only the documents that match the filter
        if source_filter:
            filtered = self._collection.get(where={"source": source_filter})
            available = len(filtered["ids"])
        else:
            available = self._collection.count()

        if available == 0:
            return []

        q_embedding = self._embed([query])[0]
        kwargs = dict(
            query_embeddings=[q_embedding],
            n_results=min(self.n_results, available),
            include=["documents", "distances", "metadatas"],
        )
        if source_filter:
            kwargs["where"] = {"source": source_filter}

        results = self._collection.query(**kwargs)
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

    def _generate(self, query: str, chunks: list[dict]) -> str:
        context = "\n\n---\n\n".join(
            f"[Source: {c['source']} | Relevance: {c['score']}]\n{c['text']}"
            for c in chunks
        )
        response = self._claude.messages.create(
            model=self.claude_model,
            max_tokens=512,
            system="""You are a study assistant. Answer using ONLY the provided
lecture notes. Cite the source filename for each key fact.
If the answer is not in the notes, say so clearly — do not guess.""",
            messages=[{
                "role": "user",
                "content": f"Notes:\n{context}\n\nQuestion: {query}"
            }]
        )
        return response.content[0].text


# ── Demo ──────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("DAY 16 — FULL RAG PIPELINE (CLASS-BASED)")
    print("=" * 60)

    pipeline = RAGPipeline(collection_name="jawar")

    # ── 1. Index PDFs ────────────────────────────────────────
    print("\nIndexing PDFs...")
    pdfs = [
        "data/pdfs/example_3.pptx",
        "data/pdfs/example.pdf",
    ]
    for pdf in pdfs:
        result = pipeline.index(pdf)
        print(f"  [{result['status']}] {result['source']} — {result['message']}")

    # ── 2. Show what's indexed ───────────────────────────────
    print(f"\nIndexed sources:")
    for source, count in pipeline.list_sources().items():
        print(f"  {source}: {count} chunks")
    print(f"  Total: {pipeline.chunk_count()} chunks")

    # ── 3. Ask questions ─────────────────────────────────────
    print("\n" + "=" * 60)
    print("ASKING QUESTIONS")
    print("=" * 60)

    questions = [
        "What causes Parkinson's disease?",
        "Why can't dopamine cross the blood brain barrier?",
        "What is this person's most recent job?",
    ]

    for question in questions:
        print(f"\nQ: {question}")
        result = pipeline.ask(question)

        print(f"\nSources used:")
        for s in result.sources:
            print(f"  [{s['source']}] (score: {s['score']}) \"{s['preview']}\"")

        print(f"\nAnswer:")
        print(f"  {result.answer}")
        print("-" * 60)

    # ── 4. Test edge cases ───────────────────────────────────
    print("\n" + "=" * 60)
    print("EDGE CASE HANDLING")
    print("=" * 60)

    # Re-index same PDF — should skip
    print("\nRe-indexing same PDF:")
    result = pipeline.index("data/pdfs/example_3.pptx")
    print(f"  Status: {result['status']} — {result['message']}")

    # Non-existent file
    print("\nIndexing non-existent file:")
    try:
        pipeline.index("data/pdfs/doesnt_exist.pdf")
    except FileNotFoundError as e:
        print(f"  Caught: {e}")

    # Empty query
    print("\nEmpty query:")
    try:
        pipeline.ask("")
    except ValueError as e:
        print(f"  Caught: {e}")

    print("\n" + "=" * 60)
    print("DAY 16 COMPLETE — RAGPipeline is now a reusable module")
    print("  Day 17: Better chunking + re-ranking")
    print("  Day 18: Wrap this in a FastAPI server")
    print("  Day 19: Connect to Next.js chat UI")
    print("=" * 60)


if __name__ == "__main__":
    main()
