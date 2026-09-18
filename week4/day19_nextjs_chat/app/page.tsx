"use client";

import { useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import ChatWindow from "@/components/ChatWindow";
import UploadButton from "@/components/UploadButton";
import { Message } from "@/components/MessageBubble";
import { Source, checkHealth, streamAsk, deleteSource, generateQuiz, slideImageUrl, streamSummarize, getTopics, TopicPlan, streamGenerateQuestions } from "@/lib/api";
import TopicChips from "@/components/TopicChips";

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [quizLoading, setQuizLoading] = useState(false);
  const [summarizeLoading, setSummarizeLoading] = useState(false);
  const [difficulty, setDifficulty] = useState("Medium");
  const [quizCount, setQuizCount] = useState(0);
  const [score, setScore] = useState({ correct: 0, total: 0 });
  const [topicStats, setTopicStats] = useState<Record<string, { correct: number; total: number }>>({});
  const [indexedSources, setIndexedSources] = useState<string[]>([]);
  const [unreadablePagesBySource, setUnreadablePagesBySource] = useState<Record<string, number[]>>({});
  const [sourceTopics, setSourceTopics] = useState<Record<string, TopicPlan[]>>({});
  const [chunkProgress, setChunkProgress] = useState<Record<string, Record<string, number>>>(() => {
    if (typeof window === "undefined") return {};
    try { return JSON.parse(localStorage.getItem("jawar_chunk_progress") ?? "{}"); } catch { return {}; }
  });
  const [questionProgress, setQuestionProgress] = useState<Record<string, Record<string, number>>>(() => {
    if (typeof window === "undefined") return {};
    try { return JSON.parse(localStorage.getItem("jawar_question_progress") ?? "{}"); } catch { return {}; }
  });
  const [questionsReady, setQuestionsReady] = useState<Record<string, boolean>>({});
  const [questionGenProgress, setQuestionGenProgress] = useState<{ current: number; total: number } | null>(null);
  const [sourceFilter, setSourceFilter] = useState<string>("");
  const [serverOnline, setServerOnline] = useState<boolean | null>(null);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pdfName, setPdfName] = useState<string | null>(null);
  const [pdfIsImage, setPdfIsImage] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<{ page: number; total: number; pct: number } | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Persist quiz progress across page reloads so questions don't repeat
  useEffect(() => {
    localStorage.setItem("jawar_question_progress", JSON.stringify(questionProgress));
  }, [questionProgress]);

  useEffect(() => {
    localStorage.setItem("jawar_chunk_progress", JSON.stringify(chunkProgress));
  }, [chunkProgress]);

  useEffect(() => {
    checkHealth()
      .then((h) => {
        setServerOnline(true);
        setIndexedSources(Object.keys(h.sources));
      })
      .catch(() => setServerOnline(false));
  }, []);

  // Reset source filter if the selected source was removed
  useEffect(() => {
    if (sourceFilter && !indexedSources.includes(sourceFilter)) {
      setSourceFilter("");
    }
  }, [indexedSources]);

  // Fetch topics then auto-generate all questions (cached after first run)
  useEffect(() => {
    if (!sourceFilter || sourceTopics[sourceFilter]) return;
    getTopics(sourceFilter)
      .then((topics) => {
        setSourceTopics((prev) => ({ ...prev, [sourceFilter]: topics }));
        // Auto-generate questions if not already done
        if (!questionsReady[sourceFilter]) {
          setQuestionGenProgress({ current: 0, total: 0 });
          streamGenerateQuestions(sourceFilter, (event) => {
            if (event.type === "progress") {
              setQuestionGenProgress({ current: event.current, total: event.total });
            } else if (event.type === "done") {
              setSourceTopics((prev) => ({ ...prev, [sourceFilter]: event.plans }));
              setQuestionsReady((prev) => ({ ...prev, [sourceFilter]: true }));
              setQuestionGenProgress(null);
            } else if (event.type === "error") {
              setQuestionGenProgress(null);
            }
          }).catch(() => setQuestionGenProgress(null));
        }
      })
      .catch(() => {});
  }, [sourceFilter]);

  const [topicsRefreshing, setTopicsRefreshing] = useState(false);

  async function refreshTopics() {
    if (!sourceFilter || topicsRefreshing) return;
    setTopicsRefreshing(true);
    try {
      const topics = await getTopics(sourceFilter, true);
      setSourceTopics((prev) => ({ ...prev, [sourceFilter]: topics }));
      setQuestionsReady((prev) => ({ ...prev, [sourceFilter]: false }));
      setQuestionProgress((prev) => ({ ...prev, [sourceFilter]: {} }));
      // Regenerate questions with the updated topics
      setQuestionGenProgress({ current: 0, total: 0 });
      await streamGenerateQuestions(sourceFilter, (event) => {
        if (event.type === "progress") {
          setQuestionGenProgress({ current: event.current, total: event.total });
        } else if (event.type === "done") {
          setSourceTopics((prev) => ({ ...prev, [sourceFilter]: event.plans }));
          setQuestionsReady((prev) => ({ ...prev, [sourceFilter]: true }));
          setQuestionGenProgress(null);
        } else if (event.type === "error") {
          setQuestionGenProgress(null);
        }
      }, true);
    } catch {
      setQuestionGenProgress(null);
    } finally {
      setTopicsRefreshing(false);
    }
  }

  function getLeastCoveredTopic(plans: TopicPlan[]): string | undefined {
    if (plans.length === 0) return undefined;
    const progress = questionsReady[sourceFilter]
      ? questionProgress[sourceFilter]
      : chunkProgress[sourceFilter];
    const untouched = plans.find((p) => !topicStats[p.topic] || topicStats[p.topic].total === 0);
    if (untouched) return untouched.topic;
    const incomplete = plans.find((p) => (progress?.[p.topic] ?? 0) < p.count);
    return incomplete?.topic;
  }

  function detectQuizIntent(query: string): { isQuiz: boolean; rawTopic?: string } {
    const q = query.toLowerCase().trim();
    const patterns: [RegExp, number | null][] = [
      [/^quiz\s+me\s+(?:on|about)\s+(.+)$/, 1],
      [/^ask\s+me\s+(?:some\s+)?questions?\s+(?:on|about)\s+(.+)$/, 1],
      [/^ask\s+me\s+(?:a\s+)?question\s+(?:on|about)\s+(.+)$/, 1],
      [/^test\s+me\s+(?:on|about)\s+(.+)$/, 1],
      [/^give\s+me\s+(?:a\s+)?(?:quiz|questions?)\s+(?:on|about)\s+(.+)$/, 1],
      [/^(?:quiz|test)\s+me\s+on\s+(.+)$/, 1],
      [/^(?:quiz|test)\s+me\s*$/, null],
      [/^ask\s+me\s+(?:some\s+)?questions?\s*$/, null],
    ];
    for (const [pattern, group] of patterns) {
      const match = q.match(pattern);
      if (match) return { isQuiz: true, rawTopic: group !== null ? match[group]?.trim() : undefined };
    }
    return { isQuiz: false };
  }

  function matchTopic(rawTopic: string, topics: TopicPlan[]): string | undefined {
    if (!rawTopic || !topics.length) return undefined;
    const lower = rawTopic.toLowerCase();
    const exact = topics.find((t) => t.topic.toLowerCase() === lower);
    if (exact) return exact.topic;
    const partial = topics.find(
      (t) => t.topic.toLowerCase().includes(lower) || lower.includes(t.topic.toLowerCase())
    );
    return partial?.topic;
  }

  // When source filter changes, load that file's PDF preview from the server
  function handlePreview() {
    if (!sourceFilter) return;
    if (pdfUrl && pdfName === sourceFilter) {
      setPdfUrl(null);
      setPdfName(null);
      setPdfIsImage(false);
    } else {
      setPdfUrl(`http://127.0.0.1:8080/files/${encodeURIComponent(sourceFilter)}`);
      setPdfName(sourceFilter);
      setPdfIsImage(false);
    }
  }

  function handleFileSelected(_file: File) {
    // Preview is on-demand via the eye icon — no auto-open on select
  }

  async function handleDelete(source: string) {
    try {
      await deleteSource(source);
      setIndexedSources((prev) => prev.filter((s) => s !== source));
      if (sourceFilter === source) setSourceFilter("");
      if (pdfName === source) { setPdfUrl(null); setPdfName(null); setPdfIsImage(false); }
      setQuestionProgress((prev) => { const next = { ...prev }; delete next[source]; return next; });
      setChunkProgress((prev) => { const next = { ...prev }; delete next[source]; return next; });
      setMessages((prev) => [
        ...prev,
        { id: crypto.randomUUID(), role: "assistant", text: `"${source}" removed from index.` },
      ]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Delete failed";
      setMessages((prev) => [
        ...prev,
        { id: crypto.randomUUID(), role: "assistant", text: `Error: ${msg}` },
      ]);
    }
  }

  async function handleQuiz(topic?: string) {
    if (quizLoading) return;
    setQuizLoading(true);
    try {
      const plans = sourceTopics[sourceFilter] ?? [];
      const selectedTopic = topic ?? getLeastCoveredTopic(plans);
      const usingPreGenerated = questionsReady[sourceFilter];

      if (usingPreGenerated) {
        // Serve from pre-generated question bank
        const localIndex = selectedTopic ? (questionProgress[sourceFilter]?.[selectedTopic] ?? 0) : undefined;
        const plan = plans.find((p) => p.topic === selectedTopic);

        if (selectedTopic && localIndex !== undefined && plan && localIndex >= plan.count) {
          setMessages((prev) => [
            ...prev,
            { id: crypto.randomUUID(), role: "assistant", text: `All ${plan.count} questions for **${selectedTopic}** are done! Pick another topic or try a different difficulty.` },
          ]);
          setQuizLoading(false);
          return;
        }

        const q = await generateQuiz(sourceFilter || undefined, difficulty, selectedTopic, undefined, localIndex);

        if (selectedTopic && localIndex !== undefined) {
          setQuestionProgress((prev) => ({
            ...prev,
            [sourceFilter]: { ...(prev[sourceFilter] ?? {}), [selectedTopic]: localIndex + 1 },
          }));
        }

        const next = quizCount + 1;
        setQuizCount(next);
        setMessages((prev) => [
          ...prev,
          { id: crypto.randomUUID(), role: "assistant", text: "", quiz: q, quizNumber: next },
        ]);
      } else {
        // Fall back to chunk-based generation while questions are still being prepared
        const currentIndex = selectedTopic ? (chunkProgress[sourceFilter]?.[selectedTopic] ?? 0) : undefined;
        const plan = plans.find((p) => p.topic === selectedTopic);

        if (selectedTopic && currentIndex !== undefined && plan && currentIndex >= plan.count) {
          setMessages((prev) => [
            ...prev,
            { id: crypto.randomUUID(), role: "assistant", text: `All ${plan.count} questions for **${selectedTopic}** are done! Pick another topic.` },
          ]);
          setQuizLoading(false);
          return;
        }

        const q = await generateQuiz(sourceFilter || undefined, difficulty, selectedTopic, currentIndex);

        if (selectedTopic && currentIndex !== undefined) {
          setChunkProgress((prev) => ({
            ...prev,
            [sourceFilter]: { ...(prev[sourceFilter] ?? {}), [selectedTopic]: currentIndex + 1 },
          }));
        }

        const next = quizCount + 1;
        setQuizCount(next);
        setMessages((prev) => [
          ...prev,
          { id: crypto.randomUUID(), role: "assistant", text: "", quiz: q, quizNumber: next },
        ]);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Quiz generation failed";
      setMessages((prev) => [
        ...prev,
        { id: crypto.randomUUID(), role: "assistant", text: `Error: ${msg}` },
      ]);
    } finally {
      setQuizLoading(false);
    }
  }

  function handleQuizScore(correct: boolean, topic: string) {
    setScore((s) => ({ correct: s.correct + (correct ? 1 : 0), total: s.total + 1 }));
    setTopicStats((prev) => {
      const curr = prev[topic] ?? { correct: 0, total: 0 };
      return { ...prev, [topic]: { correct: curr.correct + (correct ? 1 : 0), total: curr.total + 1 } };
    });
  }

  function handleViewSlide(source: string, page: number) {
    setPdfUrl(slideImageUrl(source, page));
    setPdfName(`${source} — Slide ${page}`);
    setPdfIsImage(true);
  }

  function handleUploaded(source: string, chunks: number, totalPages: number, unreadablePages: number[]) {
    setIndexedSources((prev) => prev.includes(source) ? prev : [...prev, source]);
    setSourceFilter(source);
    if (unreadablePages.length > 0) {
      setUnreadablePagesBySource((prev) => ({ ...prev, [source]: unreadablePages }));
    }

    const readablePages = totalPages - unreadablePages.length;
    const coverageLine = totalPages > 0
      ? `Scanned **${totalPages} pages** — **${readablePages} readable**, ${unreadablePages.length} skipped.`
      : `Indexed ${chunks} chunks.`;
    const skippedLine = unreadablePages.length > 0
      ? `\n\nSkipped pages (image-only or no text): **${unreadablePages.join(", ")}**`
      : "";

    setMessages((prev) => [
      ...prev,
      {
        id: crypto.randomUUID(),
        role: "assistant",
        text: `"${source}" indexed. ${coverageLine}${skippedLine}`,
        unreadableSlides: unreadablePages.map((page) => ({ page, source })),
      },
    ]);
  }

  async function handleSummarize() {
    if (summarizeLoading) return;
    setSummarizeLoading(true);

    const assistantId = crypto.randomUUID();
    setMessages((prev) => [...prev, { id: assistantId, role: "assistant", text: "Reading all sections…", streaming: true }]);

    let hasStartedStreaming = false;
    try {
      await streamSummarize(sourceFilter || undefined, (event) => {
        if (event.type === "progress") {
          flushSync(() => {
            setMessages((prev) => prev.map((m) => m.id === assistantId ? { ...m, text: event.message } : m));
          });
        } else if (event.type === "token") {
          flushSync(() => {
            setMessages((prev) => prev.map((m) =>
              m.id === assistantId
                ? { ...m, text: hasStartedStreaming ? m.text + event.text : event.text }
                : m
            ));
          });
          hasStartedStreaming = true;
        } else if (event.type === "done") {
          const { chunks_processed, total_pages, unreadable_pages: skipped } = event;
          const readable = total_pages != null ? total_pages - skipped.length : null;
          const coverageLine = total_pages != null
            ? `**${total_pages} pages total** · ${readable} readable · ${skipped.length} image-only`
            : `**${chunks_processed} chunks** processed`;
          const skippedLine = skipped.length > 0
            ? `\n⚠️ Image-only slides not included: ${skipped.join(", ")} — use the slide buttons from the upload message to view them.`
            : "";
          const note = `\n\n---\n*Coverage: ${coverageLine}.${skippedLine}*`;
          setMessages((prev) => prev.map((m) =>
            m.id === assistantId ? { ...m, streaming: false, text: m.text + note } : m
          ));
        } else if (event.type === "error") {
          setMessages((prev) => prev.map((m) => m.id === assistantId ? { ...m, text: `Error: ${event.message}`, streaming: false } : m));
        }
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Summarize failed";
      setMessages((prev) => prev.map((m) => m.id === assistantId ? { ...m, text: `Error: ${msg}`, streaming: false } : m));
    } finally {
      setSummarizeLoading(false);
    }
  }

  async function handleSend() {
    const query = input.trim();
    if (!query || loading) return;

    // Intercept quiz-intent phrases and route to quiz mode
    const { isQuiz, rawTopic } = detectQuizIntent(query);
    if (isQuiz) {
      setInput("");
      const topics = sourceTopics[sourceFilter] ?? [];
      const topic = rawTopic ? matchTopic(rawTopic, topics) : undefined;
      setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: "user", text: query }]);
      handleQuiz(topic);
      return;
    }

    // Build history — include quiz cards as text so Claude has context for follow-up questions
    const history = messages
      .filter((m) => m.text.trim() || m.quiz)
      .slice(-6)
      .map((m) => {
        if (m.quiz) {
          const opts = Object.entries(m.quiz.options).map(([k, v]) => `${k}: ${v}`).join(" | ");
          return {
            role: "assistant" as const,
            text: `Quiz — ${m.quiz.question} Options: ${opts} Correct: ${m.quiz.correct} (${m.quiz.options[m.quiz.correct]}) Explanation: ${m.quiz.explanation}`,
          };
        }
        return { role: m.role as "user" | "assistant", text: m.text };
      });

    setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: "user", text: query }]);
    setInput("");
    setLoading(true);

    const assistantId = crypto.randomUUID();
    setMessages((prev) => [...prev, { id: assistantId, role: "assistant", text: "", streaming: true }]);

    let collectedSources: Source[] = [];

    try {
      await streamAsk(query, (event) => {
        if (event.type === "sources") {
          collectedSources = event.sources;
        } else if (event.type === "token") {
          flushSync(() => {
            setMessages((prev) =>
              prev.map((m) => m.id === assistantId ? { ...m, text: m.text + event.text } : m)
            );
          });
        } else if (event.type === "done") {
          setMessages((prev) =>
            prev.map((m) => m.id === assistantId ? { ...m, streaming: false, sources: collectedSources } : m)
          );
        } else if (event.type === "error") {
          setMessages((prev) =>
            prev.map((m) => m.id === assistantId ? { ...m, text: `Error: ${event.message}`, streaming: false } : m)
          );
        }
      }, sourceFilter || undefined, history);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Something went wrong";
      setMessages((prev) =>
        prev.map((m) => m.id === assistantId ? { ...m, text: `Error: ${msg}`, streaming: false } : m)
      );
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <div className="h-screen flex flex-col" style={{ background: "var(--background)" }}>

      {/* Header */}
      <header
        className="relative shrink-0 flex items-center justify-between px-6 py-3.5"
        style={{ background: "#fff", borderBottom: "1px solid var(--border)" }}
      >
        <div className="flex items-center">
          <svg width="210" height="64" viewBox="0 0 460 140" fill="none" xmlns="http://www.w3.org/2000/svg" aria-label="Jawar Study Assistant">
            <g transform="translate(16, 14)">
              <path d="M4 84C18 98 40 102 72 102C98 102 114 94 120 84H4Z" fill="#0D9488"/>
              <path d="M2 84H122" stroke="#0F172A" strokeWidth="3" strokeLinecap="round"/>
              <path d="M-2 100C12 107 30 109 52 106C74 103 96 109 114 104" stroke="#38BDF8" strokeWidth="3" strokeLinecap="round"/>
              <path d="M68 20L98 74H68V20Z" fill="#0284C7" fillOpacity="0.9"/>
              <path d="M64 32L44 74H64V32Z" fill="#14B8A6" fillOpacity="0.65"/>
              <path d="M40 26H70V38H56V66C56 73.732 49.732 80 42 80C34.268 80 28 73.732 28 66H40C40 67.1 40.9 68 42 68C43.1 68 44 67.1 44 66V38H40V26Z" fill="#0F172A"/>
            </g>
            <g transform="translate(126, 28)">
              <text x="0" y="66" fontFamily="var(--font-plus-jakarta), 'Plus Jakarta Sans', system-ui, sans-serif" fontWeight="800" fontSize="68" fill="#0F172A" letterSpacing="-0.035em">awar</text>
              <text x="2" y="96" fontFamily="var(--font-plus-jakarta), 'Plus Jakarta Sans', system-ui, sans-serif" fontWeight="600" fontSize="22" fill="#64748B" letterSpacing="0.22em">STUDY ASSISTANT</text>
            </g>
          </svg>
        </div>

        <div className="flex items-center gap-3 text-xs" style={{ color: "var(--secondary)" }}>
          {uploadProgress && (
            <span style={{ color: "var(--secondary)" }}>
              {uploadProgress.total > 0
                ? `Indexing… ${uploadProgress.page}/${uploadProgress.total} pages`
                : "Indexing…"}
            </span>
          )}
          {score.total > 0 && (
            <span className="px-2 py-0.5 rounded-full font-medium" style={{ background: "#e8f0fe", color: "var(--accent)" }}>
              {score.correct}/{score.total} correct
            </span>
          )}
          {sourceFilter && sourceTopics[sourceFilter]?.length > 0 && (() => {
            const plans = sourceTopics[sourceFilter];
            const totalQ = plans.reduce((s, p) => s + p.count, 0);
            const answeredQ = Object.values(topicStats).reduce((s, t) => s + t.total, 0);
            return (
              <span className="px-2 py-0.5 rounded-full font-medium" style={{ background: answeredQ >= totalQ ? "#f0fdf4" : "var(--surface)", color: answeredQ >= totalQ ? "#16a34a" : "var(--secondary)" }}>
                Q {answeredQ}/{totalQ}
              </span>
            );
          })()}
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full" style={{ background: serverOnline === null ? "#f59e0b" : serverOnline ? "#22c55e" : "#ef4444" }} />
            {serverOnline === null ? "Connecting…" : serverOnline ? "Connected" : "Offline"}
          </span>
        </div>

        {/* Upload progress bar — replaces the bottom border while indexing */}
        <div className="absolute bottom-0 left-0 right-0 overflow-hidden" style={{ height: "2px", background: "var(--border)" }}>
          {uploadProgress && (
            <div
              className="h-full transition-all duration-200"
              style={{ width: `${uploadProgress.pct}%`, background: "var(--accent)" }}
            />
          )}
        </div>
      </header>

      {/* Body — split panel */}
      <div className="flex-1 flex overflow-hidden">

        {/* Left: PDF viewer */}
        <div
          className="flex flex-col"
          style={{
            width: pdfUrl ? "45%" : "0",
            transition: "width 0.3s ease",
            borderRight: pdfUrl ? "1px solid var(--border)" : "none",
            overflow: "hidden",
          }}
        >
          {pdfUrl && (
            <>
              <div
                className="flex items-center justify-between px-4 py-2 shrink-0 text-xs"
                style={{ borderBottom: "1px solid var(--border)", color: "var(--secondary)", background: "var(--surface)" }}
              >
                <span className="truncate font-medium" style={{ color: "var(--foreground)" }}>{pdfName}</span>
                <button onClick={() => { setPdfUrl(null); setPdfName(null); setPdfIsImage(false); }} style={{ color: "var(--secondary)" }}>✕</button>
              </div>
              {pdfIsImage ? (
                <div className="flex-1 overflow-auto flex items-start justify-center p-4" style={{ background: "#f0f0f0" }}>
                  <img src={pdfUrl!} alt={pdfName ?? "Slide"} className="max-w-full rounded shadow-md" />
                </div>
              ) : pdfName?.toLowerCase().endsWith(".pdf") || pdfName?.toLowerCase().endsWith(".pptx") ? (
                <iframe src={pdfUrl} className="flex-1 w-full" style={{ border: "none" }} />
              ) : (
                <div className="flex-1 flex flex-col items-center justify-center px-6 text-center">
                  <p className="text-xs" style={{ color: "var(--secondary)" }}>Preview not available.</p>
                </div>
              )}
            </>
          )}
        </div>

        {/* Right: Chat */}
        <div className="flex-1 flex flex-col overflow-hidden">
          <ChatWindow messages={messages} topicStats={topicStats} onQuizScore={handleQuizScore} onQuizNext={handleQuiz} onViewSlide={handleViewSlide} />

          {/* Bottom panel: topics + input */}
          <div className="shrink-0" style={{ borderTop: "1px solid var(--border)", background: "#fff" }}>

            {/* Topic chips — full width */}
            {sourceFilter && sourceTopics[sourceFilter]?.length > 0 && (
              <div className="flex items-center gap-2">
                <div className="flex-1 min-w-0">
                  <TopicChips
                    topics={sourceTopics[sourceFilter]}
                    topicStats={topicStats}
                    onQuizTopic={(topic) => handleQuiz(topic)}
                    disabled={quizLoading || loading}
                  />
                </div>
                <button
                  onClick={refreshTopics}
                  disabled={topicsRefreshing || quizLoading || loading}
                  title="Refresh topics"
                  className="shrink-0 mr-2 text-xs px-2 py-1 rounded"
                  style={{ color: "var(--secondary)", opacity: topicsRefreshing ? 0.5 : 1 }}
                >
                  {topicsRefreshing ? "…" : "↺"}
                </button>
              </div>
            )}

            {/* Input area */}
            <div className="max-w-3xl mx-auto px-4 pb-4 pt-2">

              {/* Question generation progress */}
              {questionGenProgress && (
                <div className="flex items-center gap-2 text-xs mb-2" style={{ color: "var(--secondary)" }}>
                  <div className="w-3 h-3 rounded-full border-2 border-current border-t-transparent animate-spin shrink-0" />
                  {questionGenProgress.total > 0
                    ? `Preparing questions… ${questionGenProgress.current}/${questionGenProgress.total} topics`
                    : "Preparing questions…"}
                </div>
              )}

              {/* Input card */}
              <div
                className="rounded-2xl flex flex-col"
                style={{ background: "var(--surface)", border: "1px solid var(--border)", boxShadow: "0 2px 12px rgba(0,0,0,0.06)" }}
              >
                <input
                  ref={inputRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={indexedSources.length === 0 ? "Upload a PDF first…" : "Ask a question about your notes…"}
                  disabled={loading || !serverOnline}
                  className="px-4 py-3.5 text-sm bg-transparent outline-none disabled:opacity-50 rounded-t-2xl"
                  style={{ color: "var(--foreground)" }}
                />

                {/* Card toolbar */}
                <div className="flex items-center justify-between px-3 pb-3 pt-0.5 gap-2 flex-wrap">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <UploadButton onUploaded={handleUploaded} onFileSelected={handleFileSelected} onProgress={setUploadProgress} />

                    {indexedSources.length > 0 && (
                      sourceFilter ? (
                        <div
                          className="flex items-center gap-1 px-2.5 py-1.5 rounded-full text-xs font-medium"
                          style={{ background: "#e8f0fe", border: "1px solid #c7d8fc", color: "var(--accent)" }}
                        >
                          <span className="truncate max-w-[120px]">{sourceFilter}</span>
                          <button
                            onClick={handlePreview}
                            title={pdfUrl && pdfName === sourceFilter ? "Hide preview" : "Preview"}
                            className="ml-1 flex items-center opacity-70 hover:opacity-100"
                          >
                            <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                              <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" />
                            </svg>
                          </button>
                          <button onClick={() => setSourceFilter("")} className="ml-0.5 opacity-50 hover:opacity-100">×</button>
                        </div>
                      ) : (
                        <select
                          value={sourceFilter}
                          onChange={(e) => setSourceFilter(e.target.value)}
                          className="px-2.5 py-1.5 rounded-full text-xs outline-none"
                          style={{ background: "var(--background)", border: "1px solid var(--border)", color: "var(--secondary)" }}
                        >
                          <option value="">All sources</option>
                          {indexedSources.map((s) => (
                            <option key={s} value={s}>{s}</option>
                          ))}
                        </select>
                      )
                    )}

                    <button
                      onClick={handleSummarize}
                      disabled={summarizeLoading || loading || indexedSources.length === 0}
                      className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-full text-xs font-medium transition-opacity disabled:opacity-40"
                      style={{ background: "var(--background)", border: "1px solid var(--border)", color: "var(--foreground)" }}
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <line x1="21" y1="10" x2="3" y2="10" /><line x1="21" y1="6" x2="3" y2="6" /><line x1="21" y1="14" x2="3" y2="14" /><line x1="21" y1="18" x2="10" y2="18" />
                      </svg>
                      {summarizeLoading ? "Summarizing…" : "Summarize"}
                    </button>
                  </div>

                  <div className="flex items-center gap-1.5">
                    <select
                      value={difficulty}
                      onChange={(e) => setDifficulty(e.target.value)}
                      className="px-2.5 py-1.5 rounded-full text-xs outline-none"
                      style={{ background: "var(--background)", border: "1px solid var(--border)", color: "var(--secondary)" }}
                    >
                      <option>Easy</option>
                      <option>Medium</option>
                      <option>Hard</option>
                    </select>

                    <button
                      onClick={() => handleQuiz()}
                      disabled={quizLoading || loading || indexedSources.length === 0}
                      className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-full text-xs font-medium transition-opacity disabled:opacity-40"
                      style={{ background: "var(--background)", border: "1px solid var(--border)", color: "var(--foreground)" }}
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
                      </svg>
                      {quizLoading ? "…" : "Quiz"}
                    </button>

                    <button
                      onClick={handleSend}
                      disabled={loading || !input.trim() || !serverOnline}
                      className="flex items-center gap-1.5 px-4 py-1.5 rounded-full text-xs font-semibold transition-opacity disabled:opacity-40"
                      style={{ background: "var(--accent)", color: "#fff" }}
                    >
                      {loading ? (
                        <div className="w-3 h-3 rounded-full border-2 border-white border-t-transparent animate-spin" />
                      ) : (
                        <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                          <line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" />
                        </svg>
                      )}
                      {loading ? "…" : "Send"}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
