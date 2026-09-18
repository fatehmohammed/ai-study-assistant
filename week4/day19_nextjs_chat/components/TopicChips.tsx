"use client";

import { TopicPlan } from "@/lib/api";

interface TopicStat {
  correct: number;
  total: number;
}

interface Props {
  topics: TopicPlan[];
  topicStats: Record<string, TopicStat>;
  onQuizTopic: (topic: string) => void;
  disabled: boolean;
}

function chipStyle(stat?: TopicStat): React.CSSProperties {
  if (!stat || stat.total === 0) {
    return { background: "var(--surface)", border: "1px solid var(--border)", color: "var(--secondary)" };
  }
  const pct = stat.correct / stat.total;
  if (pct >= 0.7) {
    return { background: "#f0fdf4", border: "1px solid #86efac", color: "#16a34a" };
  }
  if (pct >= 0.5) {
    return { background: "#fffbeb", border: "1px solid #fde68a", color: "#d97706" };
  }
  return { background: "#fff1f2", border: "1px solid #fecdd3", color: "#dc2626" };
}

export default function TopicChips({ topics, topicStats, onQuizTopic, disabled }: Props) {
  const totalQ = topics.reduce((s, p) => s + p.count, 0);
  const answeredQ = topics.reduce((s, p) => s + (topicStats[p.topic]?.total ?? 0), 0);

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium" style={{ color: "var(--secondary)" }}>Topics</span>
        <span className="text-xs" style={{ color: "var(--secondary)" }}>
          {answeredQ}/{totalQ} questions answered
        </span>
      </div>
      <div className="flex gap-1.5 overflow-x-auto pb-0.5" style={{ scrollbarWidth: "none" }}>
        {topics.map(({ topic, count }) => {
          const stat = topicStats[topic];
          const answered = stat?.total ?? 0;
          const style = chipStyle(stat);
          const done = answered >= count;
          return (
            <button
              key={topic}
              onClick={() => onQuizTopic(topic)}
              disabled={disabled}
              title={done ? `${topic}: all ${count} questions done` : `Quiz me on: ${topic} (${count - answered} left)`}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-opacity disabled:opacity-40 shrink-0"
              style={style}
            >
              {topic}
              <span className="opacity-70 font-normal">{answered}/{count}</span>
              {done && <span>✓</span>}
            </button>
          );
        })}
      </div>
    </div>
  );
}
