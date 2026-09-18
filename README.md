# Jawar — AI Study Assistant

A RAG-powered study assistant that reads lecture PDFs/PPTXs and helps you prepare for exams through summaries, Q&A, quizzes, and semantic search.

Built from scratch over 4 weeks to learn AI fundamentals hands-on.

**Live app:** [ai-study-assistant-fatehs.vercel.app](https://ai-study-assistant-fatehs.vercel.app)

## What it does

- Upload lecture PDFs or PowerPoint files
- **Summarize** any lecture instantly (map-reduce over all content)
- **Chat** with your notes — RAG-powered Q&A with source citations
- **Quiz** yourself with auto-generated exam-style questions (recall, mechanism, application, comparison, consequence, integration types)
- Topic-based question banks with per-topic score tracking
- OCR support for scanned PDFs
- Multi-turn conversation history

## Tech Stack

| Layer | Tech |
|---|---|
| LLM | Claude (Anthropic API) |
| Embeddings | `all-MiniLM-L6-v2` via sentence-transformers |
| Vector DB | ChromaDB |
| PDF/OCR | PyMuPDF + Tesseract |
| PPTX → PDF | LibreOffice |
| Backend | FastAPI + Python |
| Frontend | Next.js 15 (App Router) + Tailwind CSS |
| Backend hosting | Railway (Docker) |
| Frontend hosting | Vercel |

## Architecture

```
Frontend (Vercel)          Backend (Railway / Docker)
─────────────────          ──────────────────────────
Next.js 15                 FastAPI
  │                          │
  │  REST + SSE              ├── /index/stream   — upload & index PDF
  └─────────────────────►    ├── /ask/stream     — RAG Q&A streaming
                             ├── /summarize/stream — full-doc summary
                             ├── /topics         — extract & assign topics
                             ├── /questions/stream — pre-generate quiz bank
                             └── /quiz           — serve questions

                           ChromaDB (persistent volume)
                           PyMuPDF + Tesseract OCR
                           LibreOffice (PPTX → PDF)
```

## Local Development

### Backend
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # add your ANTHROPIC_API_KEY
uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

### Frontend
```bash
cd week4/day19_nextjs_chat
npm install
NEXT_PUBLIC_API_URL=http://localhost:8080 npm run dev
```

## Deployment

- **Backend** — Railway, deployed from `backend/` via Dockerfile. Persistent volume mounted at `/data` for ChromaDB and uploaded files.
- **Frontend** — Vercel, deployed from `week4/day19_nextjs_chat/`. Set `NEXT_PUBLIC_API_URL` to your Railway backend URL.

## 4-Week Build Journey

### Week 1 — Prompting Fundamentals
- [x] Day 1 — PDF Reader + Summary
- [x] Day 2 — Q&A Generator
- [x] Day 3 — Flashcard Generator
- [x] Day 4 — Concept Extractor
- [x] Day 5 — Study Guide Builder

### Week 2 — Tool Use & Structured Outputs
- [x] Day 6 — Structured Output (JSON)
- [x] Day 7 — Tools Intro
- [x] Day 8 — Multi-Tool Agent
- [x] Day 9 — Streaming
- [x] Day 10 — Autonomous Agent Loop

### Week 3 — Embeddings & Semantic Search
- [x] Day 11 — First Embedding
- [x] Day 12 — Cosine Similarity
- [x] Day 13 — ChromaDB Vector Store
- [x] Day 14 — Semantic Search
- [x] Day 15 — Multi-PDF Search

### Week 4 — RAG Pipeline + Chat UI
- [x] Day 16 — Full RAG Pipeline
- [x] Day 17 — Advanced RAG (chunking + re-ranking)
- [x] Day 18 — FastAPI Backend
- [x] Day 19 — Next.js Chat UI with streaming, quiz, topics
- [x] Day 20 — Production deployment (Railway + Vercel)
