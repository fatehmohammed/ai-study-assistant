# AI Study Assistant

A RAG-powered study assistant that reads lecture PDFs and helps you prepare for exams through summaries, Q&A, flashcards, and semantic search.

Built from scratch over 4 weeks to learn AI fundamentals hands-on.

## What it does

- Summarize any lecture PDF instantly
- Generate exam-style Q&A from lecture content
- Create flashcards for key concepts
- Search across multiple PDFs by meaning, not keywords
- Chat with all your lecture notes at once (Week 4)

## Tech Stack

- **Python** — core language
- **Claude API (Anthropic)** — LLM for summarization, Q&A, and RAG
- **PyMuPDF** — PDF text extraction
- **ChromaDB** — vector database for semantic search
- **Next.js** — chat UI (Week 4)

## Setup

1. Clone the repo
   ```bash
   git clone https://github.com/YOUR_USERNAME/ai-study-assistant.git
   cd ai-study-assistant
   ```

2. Install dependencies
   ```bash
   pip3 install anthropic pymupdf python-dotenv numpy chromadb
   ```

3. Add your API key
   ```bash
   cp .env.example .env
   # Edit .env and add your Anthropic API key
   # Get one at console.anthropic.com
   ```

## 4-Week Build Plan

### Week 1 — Prompting Fundamentals
| Day | Script | What it does |
|-----|--------|-------------|
| 1 | `week1/day1_pdf_reader.py` | Read a PDF and summarize it |
| 2 | `week1/day2_qa_generator.py` | Generate exam Q&A from lecture content |
| 3 | `week1/day3_flashcards.py` | Auto-generate flashcards |
| 4 | `week1/day4_concept_extractor.py` | Extract key concepts and definitions |
| 5 | `week1/day5_study_guide.py` | Chain prompts into a full study guide |

### Week 2 — Tool Use & Structured Outputs
| Day | Script | What it does |
|-----|--------|-------------|
| 6 | `week2/day6_structured_output.py` | Get JSON-formatted responses |
| 7 | `week2/day7_tools_intro.py` | Define tools Claude can call |
| 8 | `week2/day8_multi_tool.py` | Multi-tool agent |
| 9 | `week2/day9_streaming.py` | Stream responses in real time |
| 10 | `week2/day10_agent_loop.py` | Autonomous agent loop |

### Week 3 — Embeddings & Semantic Search
| Day | Script | What it does |
|-----|--------|-------------|
| 11 | `week3/day11_embeddings.py` | Generate your first embedding |
| 12 | `week3/day12_similarity.py` | Cosine similarity between chunks |
| 13 | `week3/day13_vector_store.py` | Store embeddings in ChromaDB |
| 14 | `week3/day14_semantic_search.py` | Search PDFs by meaning |
| 15 | `week3/day15_multi_pdf.py` | Search across 10 lectures at once |

### Week 4 — RAG Pipeline + Chat UI
| Day | Script | What it does |
|-----|--------|-------------|
| 16 | `week4/day16_rag_pipeline.py` | Full RAG pipeline |
| 17 | `week4/day17_rag_advanced.py` | Better chunking and re-ranking |
| 18 | `week4/day18_nextjs_setup/` | Wire backend to Next.js |
| 19 | `week4/day19_chat_ui/` | Chat UI with PDF upload |
| 20 | `week4/day20_final_app/` | Final polish and deploy |

## Usage

**Summarize a lecture:**
```bash
python3 week1/day1_pdf_reader.py
```

**Generate exam Q&A:**
```bash
python3 week1/day2_qa_generator.py
```

## Progress

- [x] Day 1 — PDF Reader + Summary
- [x] Day 2 — Q&A Generator
- [ ] Day 3 — Flashcard Generator
- [ ] Day 4 — Concept Extractor
- [ ] Day 5 — Study Guide Builder
