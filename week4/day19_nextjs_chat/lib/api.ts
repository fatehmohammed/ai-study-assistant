const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8080";

// ── Types ─────────────────────────────────────────────────────

export interface Source {
  source: string;
  score: number;
  preview: string;
}

export interface HealthResponse {
  status: string;
  chunks_indexed: number;
  sources: Record<string, number>;
}

export interface IndexResponse {
  status: string;
  source: string;
  chunks: number;
  message: string;
}

// SSE event shapes
export type SSEEvent =
  | { type: "sources"; sources: Source[] }
  | { type: "token"; text: string }
  | { type: "done" }
  | { type: "error"; message: string };

// ── API calls ─────────────────────────────────────────────────

export async function checkHealth(): Promise<HealthResponse> {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error("Server unreachable");
  return res.json();
}

export type IndexEvent =
  | { type: "progress"; page: number; total: number; pct: number }
  | { type: "done"; source: string; chunks: number; message: string; total_pages?: number; unreadable_pages?: number[] }
  | { type: "error"; message: string };

export function slideImageUrl(source: string, page: number): string {
  return `${API_BASE}/files/${encodeURIComponent(source)}/slides/${page}`;
}

export async function indexWithProgress(
  file: File,
  onEvent: (event: IndexEvent) => void
): Promise<void> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/index/stream`, { method: "POST", body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Upload failed" }));
    throw new Error(err.detail ?? "Upload failed");
  }
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      try { onEvent(JSON.parse(line.slice(6))); } catch { /* skip */ }
    }
  }
}

export async function uploadPDF(file: File): Promise<IndexResponse> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/index`, { method: "POST", body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Upload failed" }));
    throw new Error(err.detail ?? "Upload failed");
  }
  return res.json();
}

export interface EvidenceChunk {
  source: string;
  score: number;
  text: string;
}

export interface QuizQuestion {
  question: string;
  options: Record<string, string>;
  correct: string;
  explanation: string;
  source: string;
  difficulty: string;
  topic: string;
  question_type: string;
  evidence: EvidenceChunk[];
}

export interface TopicPlan {
  topic: string;
  count: number;
}

export async function getTopics(sourceFilter: string, force = false): Promise<TopicPlan[]> {
  const res = await fetch(`${API_BASE}/topics`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source_filter: sourceFilter, force }),
  });
  if (!res.ok) throw new Error("Could not load topics");
  return res.json();
}

export async function generateQuiz(sourceFilter?: string, difficulty = "Medium", topic?: string, chunkIndex?: number, questionIndex?: number): Promise<QuizQuestion> {
  const res = await fetch(`${API_BASE}/quiz`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source_filter: sourceFilter ?? null, difficulty, topic: topic ?? null, chunk_index: chunkIndex ?? null, question_index: questionIndex ?? null }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Quiz generation failed" }));
    throw new Error(err.detail ?? "Quiz generation failed");
  }
  return res.json();
}

export type QuestionGenEvent =
  | { type: "progress"; current: number; total: number; message: string }
  | { type: "done"; count: number; plans: TopicPlan[] }
  | { type: "error"; message: string };

export async function streamGenerateQuestions(
  sourceFilter: string,
  onEvent: (event: QuestionGenEvent) => void,
  force = false
): Promise<void> {
  const res = await fetch(`${API_BASE}/questions/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source_filter: sourceFilter, force }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Question generation failed" }));
    throw new Error(err.detail ?? "Question generation failed");
  }
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      try { onEvent(JSON.parse(line.slice(6))); } catch { /* skip */ }
    }
  }
}

export async function deleteSource(filename: string): Promise<void> {
  const res = await fetch(`${API_BASE}/sources/${encodeURIComponent(filename)}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Delete failed" }));
    throw new Error(err.detail ?? "Delete failed");
  }
}

export type SummarizeEvent =
  | { type: "progress"; current: number; total: number; message: string }
  | { type: "token"; text: string }
  | { type: "done"; chunks_processed: number; total_pages: number | null; unreadable_pages: number[] }
  | { type: "error"; message: string };

export async function streamSummarize(
  sourceFilter: string | undefined,
  onEvent: (event: SummarizeEvent) => void
): Promise<void> {
  const res = await fetch(`${API_BASE}/summarize/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source_filter: sourceFilter ?? null }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Summarize failed" }));
    throw new Error(err.detail ?? "Summarize failed");
  }
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      try { onEvent(JSON.parse(line.slice(6))); } catch { /* skip */ }
    }
  }
}


export async function streamAsk(
  query: string,
  onEvent: (event: SSEEvent) => void,
  sourceFilter?: string,
  history?: Array<{ role: string; text: string }>
): Promise<void> {
  const res = await fetch(`${API_BASE}/ask/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query,
      source_filter: sourceFilter ?? null,
      history: history ?? [],
    }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(err.detail ?? "Request failed");
  }

  // Read the SSE stream line by line
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? ""; // keep incomplete last line

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const json = line.slice(6).trim();
      if (!json) continue;
      try {
        const event: SSEEvent = JSON.parse(json);
        onEvent(event);
      } catch {
        // malformed line — skip
      }
    }
  }
}
