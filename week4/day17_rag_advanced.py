import os
import re
import anthropic
import pymupdf
import chromadb
from dotenv import load_dotenv

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

from sentence_transformers import SentenceTransformer

# Import Day 16's pipeline — Day 17 extends it, doesn't replace it
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from week4.day16_rag_pipeline import RAGPipeline, RAGResult

load_dotenv()


# ── Improvement 1: Sentence-aware chunking ────────────────────
#
# Day 16 problem:
#   Word-window chunking cuts anywhere — mid-sentence, mid-thought.
#   "The substantia nigra produces dopa-" ← chunk boundary here
#   "-mine which controls motor function" ← next chunk starts here
#
# Day 17 fix:
#   Split on sentence boundaries first, then group sentences
#   into chunks. Never cuts mid-sentence.

def sentence_chunk(text: str, max_words: int = 200, overlap_sentences: int = 2) -> list[str]:
    """
    Split text into chunks that respect sentence boundaries.

    max_words         — target chunk size in words
    overlap_sentences — how many sentences to share between chunks
                        (like word overlap but at the sentence level)
    """
    # Split into sentences on . ? ! followed by whitespace
    raw_sentences = re.split(r'(?<=[.?!])\s+', text.strip())
    sentences = [s.strip() for s in raw_sentences if len(s.strip()) > 10]

    chunks = []
    current_sentences = []
    current_word_count = 0

    for sentence in sentences:
        word_count = len(sentence.split())

        # If adding this sentence exceeds the limit, save current chunk
        if current_word_count + word_count > max_words and current_sentences:
            chunks.append(" ".join(current_sentences))

            # Overlap: keep last N sentences as the start of the next chunk
            current_sentences = current_sentences[-overlap_sentences:]
            current_word_count = sum(len(s.split()) for s in current_sentences)

        current_sentences.append(sentence)
        current_word_count += word_count

    # Don't forget the last chunk
    if current_sentences:
        chunks.append(" ".join(current_sentences))

    return [c for c in chunks if len(c.split()) > 20]


# ── Improvement 2: Re-ranking ─────────────────────────────────
#
# Day 16 problem:
#   ChromaDB ranks chunks purely by embedding similarity.
#   Embedding similarity is good but not perfect —
#   a chunk can be semantically close but missing the key term.
#
# Day 17 fix:
#   Retrieve 2x more candidates than needed.
#   Re-rank them using TWO signals:
#     1. Embedding score  (semantic similarity)
#     2. Keyword overlap  (does the chunk contain query words?)
#   Combine scores → take top N.
#
#   This is a simplified version of what production systems
#   do with cross-encoder models.

def keyword_overlap_score(query: str, chunk: str) -> float:
    """
    Score how many query words appear in the chunk.
    Returns 0.0 – 1.0.
    """
    stopwords = {"what", "is", "are", "the", "a", "an", "how", "why",
                 "does", "do", "in", "of", "to", "and", "or", "it"}

    query_words = {
        w.lower().strip(".,?!")
        for w in query.split()
        if w.lower() not in stopwords and len(w) > 2
    }
    if not query_words:
        return 0.0

    chunk_lower = chunk.lower()
    matches = sum(1 for w in query_words if w in chunk_lower)
    return matches / len(query_words)


def rerank(query: str, chunks: list[dict], top_n: int) -> list[dict]:
    """
    Re-rank retrieved chunks using embedding score + keyword overlap.

    embedding_weight + keyword_weight = 1.0
    Tune these to favour one signal over the other.
    """
    EMBEDDING_WEIGHT = 0.7
    KEYWORD_WEIGHT = 0.3

    for chunk in chunks:
        keyword_score = keyword_overlap_score(query, chunk["text"])
        chunk["keyword_score"] = round(keyword_score, 4)
        chunk["combined_score"] = round(
            EMBEDDING_WEIGHT * chunk["score"] + KEYWORD_WEIGHT * keyword_score,
            4
        )

    return sorted(chunks, key=lambda c: c["combined_score"], reverse=True)[:top_n]


# ── Improvement 3: Context window guard ───────────────────────
#
# ⚠️ Edge case we flagged on Day 16:
#   If you retrieve too many large chunks, the total context
#   sent to Claude can exceed the model's context window.
#
# Fix: Estimate token count and trim if needed.
# Rule of thumb: 1 token ≈ 0.75 words

MAX_CONTEXT_WORDS = 2000   # ~2,700 tokens — safe for claude-opus-4-7

def trim_to_context_limit(chunks: list[dict], max_words: int = MAX_CONTEXT_WORDS) -> list[dict]:
    """Drop chunks once we'd exceed the context word limit."""
    total, kept = 0, []
    for chunk in chunks:
        word_count = len(chunk["text"].split())
        if total + word_count > max_words:
            break
        kept.append(chunk)
        total += word_count
    return kept


# ── Advanced pipeline (extends Day 16) ───────────────────────

class AdvancedRAGPipeline(RAGPipeline):
    """
    Extends RAGPipeline with:
    - Sentence-aware chunking (no mid-sentence cuts)
    - Re-ranking (embedding score + keyword overlap)
    - Context window guard (no token overflow)
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("collection_name", "jawar_advanced")
        kwargs.setdefault("n_results", 3)
        self._candidates = (kwargs["n_results"] if "n_results" in kwargs else 3) * 2
        super().__init__(**kwargs)

    def _chunk_text(self, text: str) -> list[str]:
        """Override Day 16's word-window with sentence-aware chunking."""
        return sentence_chunk(text, max_words=self.chunk_size)

    def _retrieve(self, query: str, source_filter: str = None) -> list[dict]:
        """Override Day 16's retrieve to add re-ranking."""
        if self._collection.count() == 0:
            return []

        q_embedding = self._embed([query])[0]
        kwargs = dict(
            query_embeddings=[q_embedding],
            # Fetch 2x candidates so re-ranker has more to work with
            n_results=min(self._candidates, self._collection.count()),
            include=["documents", "distances", "metadatas"],
        )
        if source_filter:
            kwargs["where"] = {"source": source_filter}

        results = self._collection.query(**kwargs)
        candidates = [
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

        # Re-rank candidates
        reranked = rerank(query, candidates, top_n=self.n_results)

        # Guard against context overflow
        return trim_to_context_limit(reranked)


# ── Demo ──────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("DAY 17 — ADVANCED RAG: BETTER CHUNKING + RE-RANKING")
    print("=" * 60)

    # ── 1. Compare chunking strategies ───────────────────────
    print("\n" + "=" * 60)
    print("IMPROVEMENT 1 — SENTENCE-AWARE CHUNKING")
    print("=" * 60)

    sample = """The substantia nigra is a critical region of the midbrain.
It produces dopamine, which controls motor movements. In Parkinson's
disease, the neurons in this region degenerate. This leads to reduced
dopamine levels. The result is the characteristic motor symptoms of
Parkinson's: tremor, rigidity, and bradykinesia. Treatment with
L-DOPA can help replenish dopamine levels in the brain."""

    word_chunks = []
    words = sample.split()
    step = 30 - 5
    for start in range(0, len(words), step):
        chunk = " ".join(words[start: start + 30])
        if len(chunk.strip()) > 10:
            word_chunks.append(chunk)

    sentence_chunks = sentence_chunk(sample, max_words=40, overlap_sentences=1)

    print("\nWord-window chunks (Day 16 approach):")
    for i, c in enumerate(word_chunks[:3]):
        print(f"  [{i}] \"{c}\"")

    print("\nSentence-aware chunks (Day 17 approach):")
    for i, c in enumerate(sentence_chunks):
        print(f"  [{i}] \"{c}\"")

    print("\n  Notice: sentence chunks never cut mid-sentence.")

    # ── 2. Set up advanced pipeline ──────────────────────────
    print("\n" + "=" * 60)
    print("IMPROVEMENT 2 — RE-RANKING")
    print("=" * 60)

    pipeline = AdvancedRAGPipeline()

    print("\nIndexing PDFs with sentence-aware chunking...")
    for pdf in ["data/pdfs/example_3.pptx", "data/pdfs/example.pdf"]:
        result = pipeline.index(pdf)
        print(f"  [{result['status']}] {result['source']} — {result['message']}")

    # ── 3. Show re-ranking in action ─────────────────────────
    query = "What medications are contraindicated in Parkinson's patients?"
    print(f"\nQuery: \"{query}\"")

    # Show raw embedding scores vs re-ranked scores
    raw_chunks = pipeline._retrieve.__wrapped__(pipeline, query) if hasattr(pipeline._retrieve, '__wrapped__') else None

    result = pipeline.ask(query)
    print(f"\nAfter re-ranking (embedding × 0.7 + keyword × 0.3):")
    for s in result.sources:
        print(f"  [{s['source']}] combined: {s['score']} \"{s['preview']}\"")

    print(f"\nAnswer:")
    print(f"  {result.answer}")

    # ── 4. Context window guard ───────────────────────────────
    print("\n" + "=" * 60)
    print("IMPROVEMENT 3 — CONTEXT WINDOW GUARD")
    print("=" * 60)
    print(f"""
  Max context: {MAX_CONTEXT_WORDS} words (~{int(MAX_CONTEXT_WORDS / 0.75)} tokens)
  If retrieved chunks exceed this, trailing chunks are dropped.

  Why this matters:
    Claude has a context window limit.
    Exceeding it causes an API error or truncated responses.
    The guard ensures we never send more than the model can handle.
""")

    # ── 5. Summary ───────────────────────────────────────────
    print("=" * 60)
    print("DAY 16 vs DAY 17")
    print("=" * 60)
    print("""
  Chunking:
    Day 16 — word window, may cut mid-sentence
    Day 17 — sentence-aware, always complete thoughts

  Retrieval:
    Day 16 — top N by embedding similarity only
    Day 17 — retrieve 2N candidates, re-rank by
              embedding (70%) + keyword overlap (30%)

  Safety:
    Day 16 — no context limit check
    Day 17 — trims chunks if context would overflow

  Architecture:
    Day 16 — RAGPipeline base class
    Day 17 — AdvancedRAGPipeline extends it (inheritance)
              Day 18 will import whichever pipeline it needs
""")
    print("=" * 60)
    print("NEXT — Day 18: Wrap RAGPipeline in a FastAPI server")
    print("  Your Python RAG becomes an HTTP API.")
    print("  Next.js will call it on Day 19.")
    print("=" * 60)


if __name__ == "__main__":
    main()
