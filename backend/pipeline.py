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


@dataclass
class RAGResult:
    query: str
    answer: str
    sources: list[dict]


class RAGPipeline:
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
        self.claude_model = os.getenv("CLAUDE_MODEL", claude_model)
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.n_results = n_results

        self._claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self._embedder = SentenceTransformer(embed_model)
        self._collection = self._get_collection()

    def _get_collection(self) -> chromadb.Collection:
        client = chromadb.PersistentClient(path=self.db_path)
        return client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def _extract_text(self, pdf_path: str) -> str:
        doc = pymupdf.open(pdf_path)
        pages_text = []
        for page in doc:
            text = page.get_text()
            if len(text.split()) < 10:
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

    def index(self, pdf_path: str) -> dict:
        filename = os.path.basename(pdf_path)

        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        existing = self._collection.get(where={"source": filename})
        if existing["ids"]:
            return {
                "status": "skipped",
                "source": filename,
                "chunks": len(existing["ids"]),
                "message": "Already indexed",
            }

        text = self._extract_text(pdf_path)

        if len(text.split()) < 20:
            raise ValueError(
                f"'{filename}' appears to be a scanned PDF — no text could be extracted."
            )

        chunks = self._chunk_text(text)
        embeddings = self._embed(chunks)
        ids = [f"{filename}_chunk_{i}" for i in range(len(chunks))]

        self._collection.add(
            documents=chunks,
            embeddings=embeddings,
            ids=ids,
            metadatas=[{"source": filename, "chunk_index": i} for i in range(len(chunks))],
        )

        return {
            "status": "indexed",
            "source": filename,
            "chunks": len(chunks),
            "message": f"Indexed {len(chunks)} chunks",
        }

    def ask(self, query: str, source_filter: str = None) -> RAGResult:
        if not query.strip():
            raise ValueError("Query cannot be empty")

        chunks = self._retrieve(query, source_filter)

        if not chunks:
            return RAGResult(
                query=query,
                answer="No relevant content found. Make sure you have indexed at least one PDF first.",
                sources=[],
            )

        try:
            answer = self._generate(query, chunks)
        except anthropic.APIConnectionError:
            raise ConnectionError("Could not reach Claude API. Check your internet connection.")
        except anthropic.AuthenticationError:
            raise ValueError("Invalid ANTHROPIC_API_KEY.")
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
        all_meta = self._collection.get(include=["metadatas"])
        counts: dict[str, int] = {}
        for meta in all_meta["metadatas"]:
            src = meta["source"]
            counts[src] = counts.get(src, 0) + 1
        return counts

    def chunk_count(self) -> int:
        return self._collection.count()

    def _retrieve(self, query: str, source_filter: str = None) -> list[dict]:
        if self._collection.count() == 0:
            return []

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
            messages=[{"role": "user", "content": f"Notes:\n{context}\n\nQuestion: {query}"}],
        )
        return response.content[0].text
