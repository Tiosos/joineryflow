import type {
  CvCommitIn,
  CvCommitOut,
  CvImportRunOut,
  CvPreviewOut,
} from "./cv-types";

export async function previewCvImport(
  itemId: number,
  formData: FormData,
): Promise<CvPreviewOut> {
  const res = await fetch(`/api/items/${itemId}/cv-imports/preview`, {
    method: "POST",
    credentials: "include",
    body: formData,
  });
  if (!res.ok) {
    const detail = await res.text();
    const err = new Error(`previewCvImport: ${res.status}`) as Error & {
      status: number;
      detail: string;
    };
    err.status = res.status;
    err.detail = detail;
    throw err;
  }
  return res.json();
}

export async function commitCvImport(
  itemId: number,
  runId: number,
  body: CvCommitIn,
  mode?: "replace",
): Promise<CvCommitOut> {
  const url = mode === "replace"
    ? `/api/items/${itemId}/cv-imports/${runId}/commit?mode=replace`
    : `/api/items/${itemId}/cv-imports/${runId}/commit`;
  const res = await fetch(url, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail: unknown = await res.text();
    try {
      detail = JSON.parse(detail as string);
    } catch {
      // keep as text
    }
    const err = new Error(`commitCvImport: ${res.status}`) as Error & {
      status: number;
      detail: unknown;
    };
    err.status = res.status;
    err.detail = detail;
    throw err;
  }
  return res.json();
}

export async function listCvImports(
  itemId: number,
): Promise<CvImportRunOut[]> {
  const res = await fetch(`/api/items/${itemId}/cv-imports`, {
    credentials: "include",
  });
  if (!res.ok) throw new Error(`listCvImports: ${res.status}`);
  return res.json();
}
