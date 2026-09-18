"use client";

import { useEffect, useRef } from "react";
import MessageBubble, { Message } from "@/components/MessageBubble";

interface Props {
  messages: Message[];
  topicStats: Record<string, { correct: number; total: number }>;
  onQuizScore: (correct: boolean, topic: string) => void;
  onQuizNext: () => void;
  onViewSlide: (source: string, page: number) => void;
}

export default function ChatWindow({ messages, topicStats, onQuizScore, onQuizNext, onViewSlide }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-2">
        <p className="text-sm" style={{ color: "var(--secondary)" }}>
          Upload a PDF or PPTX to get started
        </p>
      </div>
    );
  }

  const lastQuizId = [...messages].reverse().find((m) => m.quiz)?.id;

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6 flex flex-col gap-4">
      {messages.map((msg) => (
        <MessageBubble
          key={msg.id}
          message={msg}
          topicStats={topicStats}
          isLatestQuiz={msg.quiz ? msg.id === lastQuizId : undefined}
          onQuizScore={onQuizScore}
          onQuizNext={onQuizNext}
          onViewSlide={onViewSlide}
        />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
