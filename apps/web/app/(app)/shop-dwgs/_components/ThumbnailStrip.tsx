"use client";

import { useEffect, useRef, useState } from "react";

// Only the types are imported statically; the library itself is loaded on
// demand in the browser (it touches DOM globals, so it must never run in SSR).
import type { PDFDocumentLoadingTask, PDFDocumentProxy } from "pdfjs-dist";

interface Props {
  /** URL of the PDF to thumbnail. */
  url: string;
  /** The page the main viewer was last sent to (1-based). */
  page: number;
  onPage: (page: number) => void;
}

const THUMB_WIDTH = 96; // CSS px

/** Vertical strip of page thumbnails for a PDF. pdf.js renders the thumbnails
 *  only; the drawing itself is still the browser's own PDF viewer, which the
 *  viewer re-points at `#page=N` when a thumbnail is clicked. The current page
 *  therefore reflects the last click, not scrolling inside the embedded viewer
 *  (the app cannot see that). */
export default function ThumbnailStrip({ url, page, onPage }: Props) {
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null);
  const [error, setError] = useState(false);
  const canvases = useRef<(HTMLCanvasElement | null)[]>([]);

  useEffect(() => {
    let cancelled = false;
    let loadingTask: PDFDocumentLoadingTask | null = null;
    setDoc(null);
    setError(false);
    (async () => {
      try {
        // The legacy build: the modern one needs very recent JS features
        // (e.g. Map.getOrInsertComputed) and silently draws nothing without them.
        const pdfjs = await import("pdfjs-dist/legacy/build/pdf.mjs");
        pdfjs.GlobalWorkerOptions.workerSrc = new URL(
          "pdfjs-dist/legacy/build/pdf.worker.min.mjs",
          import.meta.url,
        ).toString();
        // useSystemFonts: a PDF that names a standard font without embedding it
        // (common for generated PDFs) would otherwise draw no text at all.
        loadingTask = pdfjs.getDocument({ url, useSystemFonts: true });
        const loaded = await loadingTask.promise;
        if (cancelled) { void loadingTask.destroy(); return; }
        setDoc(loaded);
      } catch {
        // An unparseable or unreachable file: the main viewer will say so
        // itself, and the strip just stays out of the way.
        if (!cancelled) setError(true);
      }
    })();
    return () => {
      cancelled = true;
      // Frees the document and its worker (a still-loading task is aborted).
      if (loadingTask) void loadingTask.destroy();
    };
  }, [url]);

  // Render each page once the document is in, one after another so a long
  // drawing set doesn't hog the main thread.
  useEffect(() => {
    if (!doc) return;
    let cancelled = false;
    (async () => {
      for (let n = 1; n <= doc.numPages; n++) {
        if (cancelled) return;
        try {
          const p = await doc.getPage(n);
          const canvas = canvases.current[n - 1];
          if (!canvas || cancelled) return;
          const base = p.getViewport({ scale: 1 });
          const dpr = window.devicePixelRatio || 1;
          const scale = (THUMB_WIDTH * dpr) / base.width;
          const viewport = p.getViewport({ scale });
          canvas.width = Math.floor(viewport.width);
          canvas.height = Math.floor(viewport.height);
          canvas.style.width = `${THUMB_WIDTH}px`;
          canvas.style.height = `${Math.floor(viewport.height / dpr)}px`;
          await p.render({ canvas, viewport }).promise;
        } catch (e) {
          // A page that fails to render leaves a blank thumbnail; the rest go on.
          console.error("thumbnail render failed", n, e);
        }
      }
    })();
    return () => { cancelled = true; };
  }, [doc]);

  if (error) return null;

  return (
    <nav
      data-testid="thumbnail-strip"
      aria-label="Page thumbnails"
      className="hidden w-32 shrink-0 overflow-y-auto border-r border-h-line bg-h-surface-alt p-2 lg:block"
    >
      {!doc && <p className="text-center text-[11px] text-h-muted">Loading pages…</p>}
      {doc && (
        <>
          <p data-testid="page-count" className="mb-2 text-center text-[11px] text-h-muted">
            {doc.numPages} page{doc.numPages === 1 ? "" : "s"}
          </p>
          <ol className="space-y-3">
            {Array.from({ length: doc.numPages }, (_, i) => i + 1).map((n) => (
              <li key={n} className="flex flex-col items-center">
                <button
                  type="button"
                  data-testid="thumbnail"
                  aria-label={`Go to page ${n}`}
                  aria-current={page === n ? "page" : undefined}
                  onClick={() => onPage(n)}
                  className={`rounded border-2 bg-white p-0.5 ${
                    page === n ? "border-h-accent" : "border-transparent hover:border-h-line"
                  }`}
                >
                  <canvas ref={(el) => { canvases.current[n - 1] = el; }} />
                </button>
                <span className="mt-1 text-[11px] text-h-ink2">{n}</span>
              </li>
            ))}
          </ol>
        </>
      )}
    </nav>
  );
}
