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

export default function MessageBubble({ message, topicStats, isLatestQuiz, onQuizScore, onQuizNext, onViewSlide }: Props) {
  const isUser = message.role === "user";

  if (message.quiz && onQuizScore && onQuizNext) {
    const topicStat = topicStats[message.quiz.topic];
    return (
      <div className="flex justify-start">
        <QuizCard
          quiz={message.quiz}
          questionNumber={message.quizNumber ?? 1}
          isLatest={isLatestQuiz ?? false}
          topicStat={topicStat}
          onScore={onQuizScore}
          onNext={onQuizNext}
        />
      </div>
    );
  }

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[72%] flex flex-col gap-2 ${isUser ? "items-end" : "items-start"}`}>
        {/* Bubble */}
        <div
          className="px-4 py-3 rounded-2xl text-sm leading-relaxed"
          style={
            isUser
              ? { background: "var(--accent)", color: "#fff", borderBottomRightRadius: "6px" }
              : { background: "#ffffff", color: "var(--foreground)", border: "1px solid var(--border)", borderBottomLeftRadius: "6px", boxShadow: "0 1px 3px rgba(0,0,0,0.06)" }
          }
        >
          {isUser ? (
            <span className="whitespace-pre-wrap">{message.text}</span>
          ) : (
            <ReactMarkdown
              components={{
                p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
                em: ({ children }) => <em className="italic">{children}</em>,
                ul: ({ children }) => <ul className="list-disc pl-4 mb-2 space-y-1">{children}</ul>,
                ol: ({ children }) => <ol className="list-decimal pl-4 mb-2 space-y-1">{children}</ol>,
                li: ({ children }) => <li>{children}</li>,
                code: ({ children }) => <code className="px-1 rounded text-xs" style={{ background: "var(--background)" }}>{children}</code>,
                h1: ({ children }) => <h1 className="font-semibold text-base mb-1">{children}</h1>,
                h2: ({ children }) => <h2 className="font-semibold mb-1">{children}</h2>,
                h3: ({ children }) => <h3 className="font-medium mb-1">{children}</h3>,
              }}
            >
              {message.text}
            </ReactMarkdown>
          )}
          {message.streaming && (
            <span className="inline-block w-1.5 h-3.5 ml-0.5 rounded-sm align-middle animate-pulse" style={{ background: "var(--secondary)" }} />
          )}

          {/* Unreadable slide buttons */}
          {!isUser && message.unreadableSlides && message.unreadableSlides.length > 0 && onViewSlide && (
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
                    <rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/>
                  </svg>
                  Slide {page}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Source chips */}
        {!isUser && !message.streaming && message.sources && message.sources.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {message.sources.map((s, i) => (
              <div
                key={i}
                className="flex flex-col px-3 py-1.5 rounded-xl text-xs"
                style={{
                  background: "#f5f5f7",
                  border: "1px solid var(--border)",
                }}
                title={s.preview}
              >
                <span className="font-medium truncate max-w-[180px]" style={{ color: "var(--accent)" }}>
                  {s.source}
                </span>
                <span style={{ color: "var(--secondary)" }}>score {s.score}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
