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
  const [chunkProgress, setChunkProgress] = useState<Record<string, Record<string, number>>>({});
  const [questionProgress, setQuestionProgress] = useState<Record<string, Record<string, number>>>({});
  const [questionsReady, setQuestionsReady] = useState<Record<string, boolean>>({});
  const [questionGenProgress, setQuestionGenProgress] = useState<{ current: number; total: number } | null>(null);
  const [sourceFilter, setSourceFilter] = useState<string>("");
  const [serverOnline, setServerOnline] = useState<boolean | null>(null);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pdfName, setPdfName] = useState<string | null>(null);
  const [pdfIsImage, setPdfIsImage] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

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

  function handleUploaded(source: string, chunks: number, unreadablePages: number[]) {
    setIndexedSources((prev) => prev.includes(source) ? prev : [...prev, source]);
    setSourceFilter(source);
    if (unreadablePages.length > 0) {
      setUnreadablePagesBySource((prev) => ({ ...prev, [source]: unreadablePages }));
    }
    const unreadableNote = unreadablePages.length > 0
      ? `\n\n⚠️ ${unreadablePages.length} slide${unreadablePages.length > 1 ? "s" : ""} had no readable text (image-only). You can view them below.`
      : "";
    setMessages((prev) => [
      ...prev,
      {
        id: crypto.randomUUID(),
        role: "assistant",
        text: `"${source}" indexed — ${chunks} chunks ready.${unreadableNote}`,
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
        className="flex items-center justify-between px-6 py-4 shrink-0"
        style={{
          background: "rgba(245,245,247,0.85)",
          backdropFilter: "blur(20px)",
          WebkitBackdropFilter: "blur(20px)",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <div className="flex items-center gap-2">
          <span className="text-lg font-semibold" style={{ color: "var(--foreground)", letterSpacing: "-0.02em" }}>
            Jawar
          </span>
          <span className="text-sm" style={{ color: "var(--secondary)" }}>Study Assistant</span>
        </div>
        <div className="flex items-center gap-3 text-xs" style={{ color: "var(--secondary)" }}>
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
              <span className="px-2 py-0.5 rounded-full font-medium" style={{ background: answeredQ >= totalQ ? "#f0fdf4" : "#f5f5f7", color: answeredQ >= totalQ ? "#16a34a" : "var(--secondary)" }}>
                Q {answeredQ}/{totalQ}
              </span>
            );
          })()}
          <span className="w-2 h-2 rounded-full" style={{ background: serverOnline === null ? "#f5a623" : serverOnline ? "#34c759" : "#ff3b30" }} />
          {serverOnline === null ? "Connecting…" : serverOnline ? "Connected" : "API offline"}
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
                <div className="flex-1 flex flex-col items-center justify-center gap-2 px-6 text-center">
                  <p className="text-xs" style={{ color: "var(--secondary)" }}>Preview not available for this file type.</p>
                </div>
              )}
            </>
          )}
        </div>

        {/* Right: Chat */}
        <div className="flex flex-col flex-1 overflow-hidden">
          <ChatWindow messages={messages} topicStats={topicStats} onQuizScore={handleQuizScore} onQuizNext={handleQuiz} onViewSlide={handleViewSlide} />

          {/* Input bar */}
          <div
            className="px-4 pb-4 pt-3 flex flex-col items-center gap-2 shrink-0"
            style={{
              background: "rgba(245,245,247,0.9)",
              backdropFilter: "blur(20px)",
              WebkitBackdropFilter: "blur(20px)",
              borderTop: "1px solid var(--border)",
            }}
          >
            <div className="w-full max-w-2xl flex flex-col gap-2">
              {/* Question generation progress */}
              {questionGenProgress && (
                <div className="flex items-center gap-2 text-xs" style={{ color: "var(--secondary)" }}>
                  <div className="w-3 h-3 rounded-full border-2 border-current border-t-transparent animate-spin" />
                  {questionGenProgress.total > 0
                    ? `Preparing questions… ${questionGenProgress.current}/${questionGenProgress.total} chunks`
                    : "Preparing questions…"}
                </div>
              )}

              {/* Topic chips — shown when topics are loaded for the selected source */}
              {sourceFilter && sourceTopics[sourceFilter]?.length > 0 && (
                <TopicChips
                  topics={sourceTopics[sourceFilter]}
                  topicStats={topicStats}
                  onQuizTopic={(topic) => handleQuiz(topic)}
                  disabled={quizLoading || loading}
                />
              )}

              {/* Main input row */}
              <div className="flex gap-2">
                <input
                  ref={inputRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={indexedSources.length === 0 ? "Upload a PDF first…" : "Ask a question about your notes…"}
                  disabled={loading || !serverOnline}
                  className="flex-1 px-4 py-3 rounded-xl text-sm outline-none disabled:opacity-50"
                  style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--foreground)" }}
                />
                <button
                  onClick={handleSend}
                  disabled={loading || !input.trim() || !serverOnline}
                  className="px-5 py-3 rounded-xl text-sm font-medium transition-opacity disabled:opacity-40"
                  style={{ background: "var(--accent)", color: "#fff" }}
                >
                  {loading ? "…" : "Send"}
                </button>
              </div>

              {/* Secondary toolbar */}
              <div className="flex items-center gap-2 flex-wrap">
                <UploadButton onUploaded={handleUploaded} onFileSelected={handleFileSelected} />
                {indexedSources.length > 0 && (
                  sourceFilter ? (
                    <div
                      className="flex items-center gap-1 px-3 py-1.5 rounded-full text-xs font-medium"
                      style={{ background: "#e8f0fe", border: "1px solid #c7d8fc", color: "var(--accent)" }}
                    >
                      <span className="truncate max-w-[140px]">{sourceFilter}</span>
                      <button
                        onClick={handlePreview}
                        title={pdfUrl && pdfName === sourceFilter ? "Hide preview" : "Preview"}
                        className="ml-1 flex items-center"
                        style={{ opacity: 0.7 }}
                      >
                        <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                          <circle cx="12" cy="12" r="3"/>
                        </svg>
                      </button>
                      <button
                        onClick={() => setSourceFilter("")}
                        title="Clear filter"
                        className="ml-0.5 flex items-center"
                        style={{ opacity: 0.5 }}
                      >
                        ×
                      </button>
                    </div>
                  ) : (
                    <select
                      value={sourceFilter}
                      onChange={(e) => setSourceFilter(e.target.value)}
                      className="px-3 py-1.5 rounded-full text-xs outline-none"
                      style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--secondary)" }}
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
                  title={indexedSources.length === 0 ? "Upload a document first" : "Summarize"}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-opacity disabled:opacity-40"
                  style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--foreground)" }}
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="21" y1="10" x2="3" y2="10"/><line x1="21" y1="6" x2="3" y2="6"/><line x1="21" y1="14" x2="3" y2="14"/><line x1="21" y1="18" x2="10" y2="18"/>
                  </svg>
                  {summarizeLoading ? "Summarizing…" : "Summarize"}
                </button>
                <button
                  onClick={() => handleQuiz()}
                  disabled={quizLoading || loading || indexedSources.length === 0}
                  title={indexedSources.length === 0 ? "Upload a document first" : "Quiz me"}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-opacity disabled:opacity-40"
                  style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--foreground)" }}
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
                  </svg>
                  {quizLoading ? "Generating…" : "Quiz me"}
                </button>
                <select
                  value={difficulty}
                  onChange={(e) => setDifficulty(e.target.value)}
                  className="px-3 py-1.5 rounded-full text-xs outline-none"
                  style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--secondary)" }}
                >
                  <option>Easy</option>
                  <option>Medium</option>
                  <option>Hard</option>
                </select>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
