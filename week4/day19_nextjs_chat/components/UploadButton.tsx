"use client";

import { useRef, useState } from "react";
import { indexWithProgress } from "@/lib/api";

interface Props {
  onUploaded: (source: string, chunks: number, unreadablePages: number[]) => void;
  onFileSelected?: (file: File) => void;
}

export default function UploadButton({ onUploaded, onFileSelected }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [progress, setProgress] = useState<{ page: number; total: number; pct: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    onFileSelected?.(file);
    setError(null);
    setProgress({ page: 0, total: 0, pct: 0 });

    try {
      await indexWithProgress(file, (event) => {
        if (event.type === "progress") {
          setProgress({ page: event.page, total: event.total, pct: event.pct });
        } else if (event.type === "done") {
          setProgress(null);
          onUploaded(event.source, event.chunks, event.unreadable_pages ?? []);
        } else if (event.type === "error") {
          setProgress(null);
          setError(event.message);
        }
      });
    } catch (err) {
      setProgress(null);
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  const uploading = progress !== null;

  return (
    <div className="flex flex-col gap-1.5">
      <input ref={inputRef} type="file" accept=".pdf,.pptx" className="hidden" onChange={handleFile} />

      <button
        onClick={() => inputRef.current?.click()}
        disabled={uploading}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-opacity disabled:opacity-60"
        style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--foreground)" }}
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>
        </svg>
        {uploading ? "Indexing…" : "Upload"}
      </button>

      {uploading && progress && (
        <div className="flex flex-col gap-1 min-w-[200px]">
          <div className="flex justify-between text-xs" style={{ color: "var(--secondary)" }}>
            <span>
              {progress.total > 0
                ? `Page ${progress.page} of ${progress.total}`
                : "Starting…"}
            </span>
            <span>{progress.pct}%</span>
          </div>
          <div className="w-full h-1.5 rounded-full overflow-hidden" style={{ background: "var(--border)" }}>
            <div
              className="h-full rounded-full transition-all duration-200"
              style={{ width: `${progress.pct}%`, background: "var(--accent)" }}
            />
          </div>
        </div>
      )}

      {error && <p className="text-xs" style={{ color: "#ff3b30" }}>{error}</p>}
    </div>
  );
}
