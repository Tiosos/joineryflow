"use client";

import { useEffect, useRef, useState } from "react";
import jsQR from "jsqr";

interface Props {
  /** Any of these item numbers scanned (or typed) confirms the cutlist. */
  expectedItemNumbers: number[];
  onConfirmed: (itemNumber: number) => void;
}

/**
 * Q519: Packing is "a tracked stage, with scanning." Plan V1 ties scanning
 * to a dedicated native site app (Q532) this repo does not have — see
 * CLAUDE.md's QC / Rework / Packing section for why this uses the browser
 * camera (getUserMedia + jsQR) instead of waiting on that separate project.
 * Scanning ANY one item's label on the cutlist is enough — Shop Floor has
 * no per-item completion state to scan against; one action completes the
 * whole cutlist, same as every other stage.
 */
export function PackingScanner({ expectedItemNumbers, onConfirmed }: Props) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [manualValue, setManualValue] = useState("");
  const [manualError, setManualError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let rafId: number;

    async function start() {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "environment" },
        });
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play();
        }
        scanLoop();
      } catch {
        setCameraError(
          "Camera unavailable. Type the item number below instead.",
        );
      }
    }

    function scanLoop() {
      const video = videoRef.current;
      const canvas = canvasRef.current;
      if (!video || !canvas || video.readyState !== video.HAVE_ENOUGH_DATA) {
        rafId = requestAnimationFrame(scanLoop);
        return;
      }
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      const ctx = canvas.getContext("2d");
      if (!ctx) {
        rafId = requestAnimationFrame(scanLoop);
        return;
      }
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      const frame = ctx.getImageData(0, 0, canvas.width, canvas.height);
      const code = jsQR(frame.data, frame.width, frame.height);
      if (code) {
        const n = Number(code.data.trim());
        if (!cancelled && expectedItemNumbers.includes(n)) {
          onConfirmed(n);
          return;
        }
      }
      rafId = requestAnimationFrame(scanLoop);
    }

    void start();
    return () => {
      cancelled = true;
      cancelAnimationFrame(rafId);
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function submitManual(e: React.FormEvent) {
    e.preventDefault();
    const n = Number(manualValue.trim());
    if (!Number.isFinite(n) || !expectedItemNumbers.includes(n)) {
      setManualError("That number isn't on this cutlist.");
      return;
    }
    setManualError(null);
    onConfirmed(n);
  }

  return (
    <div className="grid gap-3">
      {cameraError ? (
        <p className="text-sm text-amber-700">{cameraError}</p>
      ) : (
        <div className="relative overflow-hidden rounded-lg border border-h-line bg-black">
          {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
          <video ref={videoRef} className="w-full" muted playsInline />
        </div>
      )}
      <canvas ref={canvasRef} className="hidden" />

      <form onSubmit={submitManual} className="flex gap-2">
        <input
          type="text"
          inputMode="numeric"
          value={manualValue}
          onChange={(e) => setManualValue(e.target.value)}
          placeholder="Or type the item number"
          className="flex-1 rounded border border-h-line bg-h-surface px-3 py-2 text-base text-h-ink"
        />
        <button
          type="submit"
          className="rounded border border-h-line px-4 py-2 text-sm text-h-ink hover:bg-h-surface"
        >
          Confirm
        </button>
      </form>
      {manualError && <p className="text-xs text-red-700">{manualError}</p>}
    </div>
  );
}
