import os
import math
import pymupdf
import numpy as np
from collections import Counter
from dotenv import load_dotenv

load_dotenv()

PDF_PATH = "data/pdfs/example_3.pptx"
CHUNK_SIZE = 200   # words per chunk
CHUNK_OVERLAP = 30 # words to share between consecutive chunks


# ── Text helpers ──────────────────────────────────────────────

def extract_text(pdf_path: str) -> str:
    doc = pymupdf.open(pdf_path)
    return "\n".join(page.get_text() for page in doc)


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping word-window chunks.

    Overlap prevents concepts from being split across boundaries —
    same idea as React's windowed list with buffer rows above/below.
    """
    words = text.split()
    chunks, step = [], size - overlap
    for start in range(0, len(words), step):
        chunk = " ".join(words[start : start + size])
        if len(chunk.strip()) > 50:
            chunks.append(chunk)
    return chunks


# ── TF-IDF embedding (no API required) ───────────────────────

STOPWORDS = {
    "the", "a", "an", "is", "in", "on", "at", "to", "of", "and",
    "or", "it", "its", "are", "was", "be", "as", "by", "for",
    "that", "this", "with", "from", "which", "they", "have",
}


def tokenize(text: str) -> list[str]:
    return [
        w.lower().strip(".,;:!?\"'()")
        for w in text.split()
        if w.lower().strip(".,;:!?\"'()") not in STOPWORDS and len(w) > 1
    ]


def build_vocabulary(chunks: list[str]) -> list[str]:
    all_words: set[str] = set()
    for chunk in chunks:
        all_words.update(tokenize(chunk))
    return sorted(all_words)


def tfidf_embed(chunks: list[str], vocab: list[str]) -> np.ndarray:
    """
    Turn each chunk into a TF-IDF vector.

    TF  = how often a word appears in THIS chunk
    IDF = log(total chunks / chunks containing this word)  — rare words score higher
    TF-IDF = TF * IDF

    Neural embeddings (Voyage AI, OpenAI) learn richer representations,
    but cosine similarity works identically on any vector.
    """
    n = len(chunks)
    word_to_idx = {w: i for i, w in enumerate(vocab)}

    # IDF — computed across all chunks
    doc_freq = np.zeros(len(vocab))
    for chunk in chunks:
        seen = set(tokenize(chunk))
        for w in seen:
            if w in word_to_idx:
                doc_freq[word_to_idx[w]] += 1
    idf = np.log((n + 1) / (doc_freq + 1)) + 1  # smoothed

    # TF-IDF matrix
    matrix = np.zeros((n, len(vocab)), dtype=np.float32)
    for i, chunk in enumerate(chunks):
        tokens = tokenize(chunk)
        counts = Counter(tokens)
        for word, count in counts.items():
            if word in word_to_idx:
                j = word_to_idx[word]
                tf = count / len(tokens)
                matrix[i, j] = tf * idf[j]

    return matrix   # shape: (n_chunks, vocab_size)


# ── Similarity math ──────────────────────────────────────────

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """
    Cosine similarity = dot(a, b) / (|a| * |b|)

    Ranges -1 (opposite) → +1 (identical).
    Measures the ANGLE between two vectors, not their magnitude.
    Two short and long chunks about the same topic score high
    because their direction is the same even if sizes differ.
    """
    norm_a, norm_b = np.linalg.norm(a), np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def similarity_matrix(embeddings: np.ndarray) -> np.ndarray:
    """All pairwise cosine similarities — (N, N) symmetric matrix."""
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1e-9, norms)   # avoid div-by-zero
    normed = embeddings / norms
    return normed @ normed.T


def rank_by_query(
    query: str, embeddings: np.ndarray, chunks: list[str], vocab: list[str]
) -> list[tuple[float, str]]:
    """Embed a query the same way and rank chunks by cosine similarity."""
    q_vec = tfidf_embed([query], vocab)[0]
    scores = [cosine_similarity(q_vec, emb) for emb in embeddings]
    return sorted(zip(scores, chunks), reverse=True)


# ── ASCII heatmap ────────────────────────────────────────────

def ascii_heatmap(matrix: np.ndarray) -> None:
    """Print a similarity heatmap. Darker = more similar."""
    blocks = " ░▒▓█"
    header = "    " + " ".join(f"{i:2d}" for i in range(len(matrix)))
    print(header)
    for i, row in enumerate(matrix):
        cells = " ".join(blocks[min(int((v + 1) / 2 * (len(blocks) - 1)), len(blocks) - 1)] for v in row)
        print(f"{i:2d}  {cells}  C{i}")


# ── Main ─────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("DAY 12 — COSINE SIMILARITY BETWEEN CHUNKS")
    print("=" * 60)
    print("(Using TF-IDF vectors — same math as neural embeddings)")

    # ── 1. Load and chunk ────────────────────────────────────
    print(f"\nLoading: {PDF_PATH}")
    text = extract_text(PDF_PATH)

    if len(text.split()) < 50:
        print("\n  ERROR: PDF appears to be scanned (image-based) — no text could be extracted.")
        print("  Use a text-based PDF. Try: data/pdfs/example.pdf")
        return

    all_chunks = chunk_text(text)
    chunks = all_chunks[:10]
    print(f"  {len(text.split())} words → {len(all_chunks)} chunks, using first {len(chunks)}")

    if len(chunks) < 2:
        print("\n  ERROR: Need at least 2 chunks to compare. Use a longer PDF.")
        return

    # ── 2. Embed (TF-IDF, no API) ────────────────────────────
    print("\nBuilding TF-IDF vectors...")
    vocab = build_vocabulary(chunks)
    embeddings = tfidf_embed(chunks, vocab)
    print(f"  Vocabulary: {len(vocab)} unique words")
    print(f"  Each chunk → vector of {embeddings.shape[1]} numbers")
    print(f"  Matrix shape: {embeddings.shape}  (chunks × vocab)")

    # ── 3. Manual spot-check ─────────────────────────────────
    print("\n" + "=" * 60)
    print("STEP 1 — MANUAL SIMILARITY (chunk 0 vs chunk 1)")
    print("=" * 60)
    sim_01 = cosine_similarity(embeddings[0], embeddings[1])
    preview = lambda c: " ".join(c.split()[:12])
    print(f"\nChunk 0: \"{preview(chunks[0])}...\"")
    print(f"Chunk 1: \"{preview(chunks[1])}...\"")
    print(f"\nCosine similarity: {sim_01:.4f}")
    print("  > 0.70  → same topic")
    print("  0.30–0.70 → loosely related")
    print("  < 0.30  → different topics")
    print("  (TF-IDF is keyword-based, not semantic — expect lower scores than neural embeddings)")

    # ── 4. Pairwise heatmap ───────────────────────────────────
    print("\n" + "=" * 60)
    print("STEP 2 — PAIRWISE SIMILARITY HEATMAP")
    print("=" * 60)
    print("Darker block = more similar\n")
    matrix = similarity_matrix(embeddings)
    ascii_heatmap(matrix)

    # ── 5. Most / least similar pairs ────────────────────────
    print("\n" + "=" * 60)
    print("STEP 3 — MOST & LEAST SIMILAR PAIRS")
    print("=" * 60)
    pairs = [
        (matrix[i][j], i, j)
        for i in range(len(chunks))
        for j in range(i + 1, len(chunks))
    ]
    pairs.sort(reverse=True)

    print("\nTop 3 most similar pairs:")
    for score, i, j in pairs[:3]:
        print(f"  Chunk {i} ↔ Chunk {j}:  {score:.4f}")
        print(f"    [{i}] \"{' '.join(chunks[i].split()[:8])}...\"")
        print(f"    [{j}] \"{' '.join(chunks[j].split()[:8])}...\"")

    print("\nTop 3 least similar pairs:")
    for score, i, j in pairs[-3:][::-1]:
        print(f"  Chunk {i} ↔ Chunk {j}:  {score:.4f}")
        print(f"    [{i}] \"{' '.join(chunks[i].split()[:8])}...\"")
        print(f"    [{j}] \"{' '.join(chunks[j].split()[:8])}...\"")

    # ── 6. Query ranking ─────────────────────────────────────
    print("\n" + "=" * 60)
    print("STEP 4 — RANK CHUNKS BY A NATURAL-LANGUAGE QUERY")
    print("=" * 60)
    query = "What are the main topics covered in this lecture?"
    print(f"\nQuery: \"{query}\"\n")
    ranked = rank_by_query(query, embeddings, chunks, vocab)
    for rank, (score, chunk) in enumerate(ranked[:5], 1):
        print(f"  #{rank} ({score:.4f})  \"{' '.join(chunk.split()[:15])}...\"")

    # ── 7. Why neural embeddings beat TF-IDF ─────────────────
    print("\n" + "=" * 60)
    print("TF-IDF vs NEURAL EMBEDDINGS")
    print("=" * 60)
    print("""
  TF-IDF (what you just ran):
    - Keyword frequency counts → vectors
    - "car" and "automobile" score 0 similarity (different words)
    - Fast, no API, deterministic
    - Works well for exact keyword matching

  Neural embeddings (Voyage AI / OpenAI):
    - Learned from billions of documents
    - "car" and "automobile" score ~0.92 (same meaning)
    - Captures synonyms, context, and relationships
    - Cosine similarity math is IDENTICAL — only the vectors differ

  Takeaway: The cosine similarity formula never changes.
  The only thing Day 13 upgrades is HOW you generate the vectors.
""")

    print("=" * 60)
    print("WHAT'S NEXT — Day 13: Store these embeddings in ChromaDB")
    print("  ChromaDB = a database that indexes vectors for fast search.")
    print("  Today you computed similarity over 10 chunks in a loop.")
    print("  ChromaDB does it over 10,000 chunks in milliseconds.")
    print("=" * 60)


if __name__ == "__main__":
    main()
