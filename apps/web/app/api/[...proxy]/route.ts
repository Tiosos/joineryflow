import { NextRequest, NextResponse } from "next/server";

const API = process.env.API_URL ?? "http://api:8000";

// Text the API sends in volume (lists, JSON); PDFs, spreadsheets and images are
// already compact or streamed as files, so they pass through untouched.
const COMPRESSIBLE = /^(application\/json|text\/|image\/svg\+xml)/i;
const MIN_BYTES = 1024;

async function forward(
  req: NextRequest,
  ctx: { params: Promise<{ proxy: string[] }> },
) {
  const { proxy } = await ctx.params;
  const url = `${API}/${proxy.join("/")}${req.nextUrl.search}`;
  const headers = new Headers(req.headers);
  headers.delete("host");
  const body = ["GET", "HEAD"].includes(req.method)
    ? undefined
    : await req.arrayBuffer();
  const upstream = await fetch(url, {
    method: req.method,
    headers,
    body,
    redirect: "manual",
  });
  const respHeaders = new Headers(upstream.headers);
  respHeaders.delete("content-encoding");
  respHeaders.delete("transfer-encoding");
  const length = Number(respHeaders.get("content-length") ?? NaN);
  if (
    upstream.body &&
    req.method !== "HEAD" &&
    upstream.status !== 204 &&
    upstream.status !== 304 &&
    /\bgzip\b/i.test(req.headers.get("accept-encoding") ?? "") &&
    COMPRESSIBLE.test(respHeaders.get("content-type") ?? "") &&
    !(length < MIN_BYTES)
  ) {
    respHeaders.delete("content-length");
    respHeaders.set("content-encoding", "gzip");
    respHeaders.append("vary", "Accept-Encoding");
    return new NextResponse(
      upstream.body.pipeThrough(new CompressionStream("gzip")),
      { status: upstream.status, headers: respHeaders },
    );
  }
  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: respHeaders,
  });
}

export {
  forward as GET,
  forward as POST,
  forward as PATCH,
  forward as PUT,
  forward as DELETE,
};
