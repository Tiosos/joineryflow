import type { FileBlob } from "./shop-drawings-types";

/**
 * Upload one file to /files via multipart/form-data.
 * Returns the FileBlob record (deduped flag included).
 *
 * Throws on non-2xx — callers should catch and surface a toast.
 */
export async function uploadFile(file: File): Promise<FileBlob> {
  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch("/api/files", { method: "POST", body: fd });
  if (!r.ok) {
    let msg = "upload failed";
    try {
      const body = await r.json();
      if (body?.detail) msg = body.detail;
    } catch {}
    throw new Error(`${r.status}: ${msg}`);
  }
  return r.json();
}
