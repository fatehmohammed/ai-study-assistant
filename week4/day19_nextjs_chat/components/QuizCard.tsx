"use client";

import { useState } from "react";
import { QuizQuestion } from "@/lib/api";

interface Props {
  quiz: QuizQuestion;
  questionNumber: number;
  isLatest: boolean;
  topicStat?: { correct: number; total: number };
  onScore: (correct: boolean, topic: string) => void;
  onNext: () => void;
}

const DIFFICULTY_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  Easy:   { bg: "#f0fdf4", text: "#16a34a", border: "#bbf7d0" },
  Medium: { bg: "#fffbeb", text: "#d97706", border: "#fde68a" },
  Hard:   { bg: "#fff1f2", text: "#e11d48", border: "#fecdd3" },
};

const TYPE_LABELS: Record<string, string> = {
  recall:      "Recall",
  mechanism:   "Mechanism",
  application: "Application",
  comparison:  "Comparison",
  consequence: "Consequence",
  integration: "Integration",
};

export default function QuizCard({ quiz, questionNumber, isLatest, topicStat, onScore, onNext }: Props) {
  const [selected, setSelected] = useState<string | null>(null);
  const [showEvidence, setShowEvidence] = useState(false);
  const answered = selected !== null;
  const diff = DIFFICULTY_COLORS[quiz.difficulty] ?? DIFFICULTY_COLORS.Medium;

  function handleSelect(key: string) {
    if (answered) return;
    setSelected(key);
    onScore(key === quiz.correct, quiz.topic);
  }

  function optionStyle(key: string): { wrapper: React.CSSProperties; letter: React.CSSProperties } {
    if (!answered) {
      return {
        wrapper: { background: "#fff", border: "1px solid #e5e7eb", cursor: "pointer" },
        letter: { background: "#f3f4f6", color: "#374151" },
      };
    }
    if (key === quiz.correct) {
      return {
        wrapper: { background: "#f0fdf4", border: "1px solid #86efac" },
        letter: { background: "#16a34a", color: "#fff" },
      };
    }
    if (key === selected) {
      return {
        wrapper: { background: "#fff1f2", border: "1px solid #fca5a5" },
        letter: { background: "#dc2626", color: "#fff" },
      };
    }
    return {
      wrapper: { background: "#fafafa", border: "1px solid #e5e7eb", opacity: 0.6 },
      letter: { background: "#f3f4f6", color: "#9ca3af" },
    };
  }

  return (
    <div
      className="rounded-2xl overflow-hidden w-full max-w-[680px]"
      style={{ background: "#fff", border: "1px solid #e5e7eb", boxShadow: "0 2px 8px rgba(0,0,0,0.08)" }}
    >
      {/* Card header */}
      <div
        className="flex items-center justify-between px-5 py-3"
        style={{ background: "#f8fafc", borderBottom: "1px solid #e5e7eb" }}
      >
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold" style={{ color: "#64748b" }}>
            Q{questionNumber}
          </span>
          <span className="text-xs" style={{ color: "#94a3b8" }}>·</span>
          <span className="text-xs" style={{ color: "#64748b" }}>{quiz.source}</span>
          {quiz.question_type && quiz.question_type !== "recall" && (
            <>
              <span className="text-xs" style={{ color: "#94a3b8" }}>·</span>
              <span className="text-xs font-medium px-2 py-0.5 rounded-full" style={{ background: "#f1f5f9", color: "#475569" }}>
                {TYPE_LABELS[quiz.question_type] ?? quiz.question_type}
              </span>
            </>
          )}
        </div>
        <span
          className="text-xs font-semibold px-2.5 py-1 rounded-full"
          style={{ background: diff.bg, color: diff.text, border: `1px solid ${diff.border}` }}
        >
          {quiz.difficulty}
        </span>
      </div>

      {/* Question */}
      <div className="px-5 py-4">
        <p className="text-sm font-medium leading-relaxed" style={{ color: "#0f172a" }}>
          {quiz.question}
        </p>
      </div>

      {/* Options */}
      <div className="px-5 pb-4 flex flex-col gap-2">
        {Object.entries(quiz.options).map(([key, text]) => {
          const s = optionStyle(key);
          return (
            <button
              key={key}
              onClick={() => handleSelect(key)}
              className="flex items-center gap-3 px-4 py-3 rounded-xl text-sm text-left transition-all w-full"
              style={s.wrapper}
            >
              <span
                className="flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold shrink-0"
                style={s.letter}
              >
                {key}
              </span>
              <span style={{ color: answered && key !== quiz.correct && key !== selected ? "#9ca3af" : "#1e293b" }}>
                {text}
              </span>
              {answered && key === quiz.correct && (
                <span className="ml-auto text-xs font-semibold" style={{ color: "#16a34a" }}>✓ Correct</span>
              )}
              {answered && key === selected && key !== quiz.correct && (
                <span className="ml-auto text-xs font-semibold" style={{ color: "#dc2626" }}>✗ Incorrect</span>
              )}
            </button>
          );
        })}
      </div>

      {/* Post-answer sections */}
      {answered && (
        <div style={{ borderTop: "1px solid #e5e7eb" }}>
          {/* Explanation */}
          <div className="px-5 py-4" style={{ background: "#f8fafc" }}>
            <p className="text-xs font-semibold mb-1" style={{ color: selected === quiz.correct ? "#16a34a" : "#dc2626" }}>
              {selected === quiz.correct ? "✓ Correct" : "✗ Incorrect"} · Key Takeaway
            </p>
            <p className="text-sm leading-relaxed" style={{ color: "#334155" }}>
              {quiz.explanation}
            </p>
          </div>

          {/* Topic performance */}
          <div className="px-5 py-3 flex items-center justify-between" style={{ borderTop: "1px solid #e5e7eb" }}>
            <div className="flex items-center gap-2">
              <span className="text-xs" style={{ color: "#64748b" }}>Topic</span>
              <span
                className="text-xs font-semibold px-2.5 py-0.5 rounded-full"
                style={{ background: "#f1f5f9", color: "#0f172a", border: "1px solid #e2e8f0" }}
              >
                {quiz.topic}
              </span>
            </div>
            {topicStat && topicStat.total > 0 && (
              <div className="flex items-center gap-1.5 text-xs">
                <span style={{ color: "#64748b" }}>Your score:</span>
                <span
                  className="font-semibold"
                  style={{
                    color: topicStat.correct / topicStat.total >= 0.7 ? "#16a34a"
                         : topicStat.correct / topicStat.total >= 0.5 ? "#d97706"
                         : "#dc2626",
                  }}
                >
                  {topicStat.correct}/{topicStat.total}
                </span>
                {topicStat.correct / topicStat.total < 0.5 && topicStat.total >= 2 && (
                  <span style={{ color: "#dc2626" }}>· review this topic</span>
                )}
              </div>
            )}
          </div>

          {/* Evidence */}
          <div style={{ borderTop: "1px solid #e5e7eb" }}>
            <button
              onClick={() => setShowEvidence((v) => !v)}
              className="w-full flex items-center justify-between px-5 py-3 text-xs font-medium"
              style={{ color: "#64748b", background: "#f8fafc" }}
            >
              <span>Source notes used to generate this question</span>
              <span>{showEvidence ? "▲ Hide" : "▼ Show evidence"}</span>
            </button>
            {showEvidence && (
              <div className="px-5 pb-4 flex flex-col gap-3" style={{ background: "#f8fafc" }}>
                {quiz.evidence.map((chunk, i) => (
                  <div
                    key={i}
                    className="rounded-xl p-3 text-xs leading-relaxed"
                    style={{ background: "#fff", border: "1px solid #e5e7eb" }}
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="font-semibold" style={{ color: "var(--accent)" }}>{chunk.source}</span>
                      <span className="px-1.5 py-0.5 rounded text-xs" style={{ background: "#f1f5f9", color: "#64748b" }}>
                        score {chunk.score}
                      </span>
                    </div>
                    <p style={{ color: "#334155" }}>{chunk.text}</p>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Next button — only on the most recent card */}
          {isLatest && (
            <div className="px-5 py-3 flex justify-end" style={{ borderTop: "1px solid #e5e7eb" }}>
              <button
                onClick={() => onNext()}
                className="px-5 py-2 rounded-lg text-sm font-medium"
                style={{ background: "var(--accent)", color: "#fff", cursor: "pointer" }}
              >
                Next Question →
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
