"use client";

import { useRef, useState } from "react";
import { indexWithProgress } from "@/lib/api";

interface Props {
  onUploaded: (source: string, chunks: number, totalPages: number, unreadablePages: number[]) => void;
  onFileSelected?: (file: File) => void;
  onProgress?: (p: { page: number; total: number; pct: number } | null) => void;
}

export default function UploadButton({ onUploaded, onFileSelected, onProgress }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    onFileSelected?.(file);
    setError(null);
    setUploading(true);
    onProgress?.({ page: 0, total: 0, pct: 0 });

    try {
      await indexWithProgress(file, (event) => {
        if (event.type === "progress") {
          onProgress?.({ page: event.page, total: event.total, pct: event.pct });
        } else if (event.type === "done") {
          onProgress?.(null);
          setUploading(false);
          onUploaded(event.source, event.chunks, event.total_pages ?? 0, event.unreadable_pages ?? []);
        } else if (event.type === "error") {
          onProgress?.(null);
          setUploading(false);
          setError(event.message);
        }
      });
    } catch (err) {
      onProgress?.(null);
      setUploading(false);
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <>
      <input ref={inputRef} type="file" accept=".pdf,.pptx" className="hidden" onChange={handleFile} />
      <button
        onClick={() => inputRef.current?.click()}
        disabled={uploading}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-opacity disabled:opacity-60"
        style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--foreground)" }}
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
        </svg>
        {uploading ? "Indexing…" : "Upload"}
      </button>
      {error && <p className="text-xs mt-1" style={{ color: "#dc2626" }}>{error}</p>}
    </>
  );
}
