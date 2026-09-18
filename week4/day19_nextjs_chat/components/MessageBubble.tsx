import { Source } from "@/lib/api";
import { QuizQuestion } from "@/lib/api";
import QuizCard from "@/components/QuizCard";
import ReactMarkdown from "react-markdown";

export interface Message {
  id: string;
  role: "user" | "assistant";
  text: string;
  sources?: Source[];
  streaming?: boolean;
  quiz?: QuizQuestion;
  quizNumber?: number;
  unreadableSlides?: Array<{ page: number; source: string }>;
}

interface Props {
  message: Message;
  topicStats: Record<string, { correct: number; total: number }>;
  isLatestQuiz?: boolean;
  onQuizScore?: (correct: boolean, topic: string) => void;
  onQuizNext?: () => void;
  onViewSlide?: (source: string, page: number) => void;
}

function JawarAvatar() {
  return (
    <svg width="28" height="28" viewBox="0 0 128 128" fill="none" xmlns="http://www.w3.org/2000/svg" className="shrink-0 mt-0.5">
      <rect width="128" height="128" rx="8" fill="#f0fdfa"/>
      <g transform="translate(4, 6) scale(0.85)">
        <path d="M4 84C18 98 40 102 72 102C98 102 114 94 120 84H4Z" fill="#0D9488"/>
        <path d="M2 84H122" stroke="#0F172A" strokeWidth="4" strokeLinecap="round"/>
        <path d="M-2 100C12 107 30 109 52 106C74 103 96 109 114 104" stroke="#38BDF8" strokeWidth="4" strokeLinecap="round"/>
        <path d="M68 20L98 74H68V20Z" fill="#0284C7" fillOpacity="0.9"/>
        <path d="M64 32L44 74H64V32Z" fill="#14B8A6" fillOpacity="0.65"/>
        <path d="M40 26H70V38H56V66C56 73.732 49.732 80 42 80C34.268 80 28 73.732 28 66H40C40 67.1 40.9 68 42 68C43.1 68 44 67.1 44 66V38H40V26Z" fill="#0F172A"/>
      </g>
    </svg>
  );
}

export default function MessageBubble({ message, topicStats, isLatestQuiz, onQuizScore, onQuizNext, onViewSlide }: Props) {
  const isUser = message.role === "user";

  if (message.quiz && onQuizScore && onQuizNext) {
    const topicStat = topicStats[message.quiz.topic];
    return (
      <div className="flex gap-3">
        <JawarAvatar />
        <div className="flex-1 min-w-0">
          <QuizCard
            quiz={message.quiz}
            questionNumber={message.quizNumber ?? 1}
            isLatest={isLatestQuiz ?? false}
            topicStat={topicStat}
            onScore={onQuizScore}
            onNext={onQuizNext}
          />
        </div>
      </div>
    );
  }

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div
          className="max-w-[75%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap"
          style={{ background: "var(--user-bubble)", color: "var(--foreground)" }}
        >
          {message.text}
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-3">
      <JawarAvatar />
      <div className="flex-1 min-w-0 flex flex-col gap-2">
        <div className="text-sm leading-relaxed" style={{ color: "var(--foreground)" }}>
          <ReactMarkdown
            components={{
              p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
              strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
              em: ({ children }) => <em className="italic">{children}</em>,
              ul: ({ children }) => <ul className="list-disc pl-4 mb-2 space-y-1">{children}</ul>,
              ol: ({ children }) => <ol className="list-decimal pl-4 mb-2 space-y-1">{children}</ol>,
              li: ({ children }) => <li>{children}</li>,
              code: ({ children }) => (
                <code className="px-1.5 py-0.5 rounded text-xs font-mono" style={{ background: "var(--surface)" }}>
                  {children}
                </code>
              ),
              h1: ({ children }) => <h1 className="font-semibold text-base mb-1.5 mt-2">{children}</h1>,
              h2: ({ children }) => <h2 className="font-semibold mb-1.5 mt-2">{children}</h2>,
              h3: ({ children }) => <h3 className="font-medium mb-1 mt-1.5">{children}</h3>,
              table: ({ children }) => (
                <div className="overflow-x-auto mb-2">
                  <table className="text-xs border-collapse w-full">{children}</table>
                </div>
              ),
              th: ({ children }) => (
                <th className="px-3 py-1.5 text-left font-semibold" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
                  {children}
                </th>
              ),
              td: ({ children }) => (
                <td className="px-3 py-1.5" style={{ border: "1px solid var(--border)" }}>
                  {children}
                </td>
              ),
            }}
          >
            {message.text}
          </ReactMarkdown>
          {message.streaming && (
            <span
              className="inline-block w-1.5 h-3.5 ml-0.5 rounded-sm align-middle animate-pulse"
              style={{ background: "var(--secondary)" }}
            />
          )}

          {!message.streaming && message.unreadableSlides && message.unreadableSlides.length > 0 && onViewSlide && (
            <div className="flex flex-wrap gap-1.5 mt-3 pt-3" style={{ borderTop: "1px solid var(--border)" }}>
              <span className="w-full text-xs mb-0.5" style={{ color: "var(--secondary)" }}>View image-only slides:</span>
              {message.unreadableSlides.map(({ page, source }) => (
                <button
                  key={page}
                  onClick={() => onViewSlide(source, page)}
                  className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium transition-opacity hover:opacity-80"
                  style={{ background: "#fff7ed", border: "1px solid #fed7aa", color: "#c2410c" }}
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="8.5" cy="8.5" r="1.5" /><polyline points="21 15 16 10 5 21" />
                  </svg>
                  Slide {page}
                </button>
              ))}
            </div>
          )}
        </div>

        {!message.streaming && message.sources && message.sources.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {message.sources.map((s, i) => (
              <div
                key={i}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs"
                style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
                title={s.preview}
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ color: "var(--accent)", flexShrink: 0 }}>
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" />
                </svg>
                <span className="font-medium truncate max-w-[160px]" style={{ color: "var(--foreground)" }}>{s.source}</span>
                <span style={{ color: "var(--secondary)" }}>{(s.score * 100).toFixed(0)}%</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
