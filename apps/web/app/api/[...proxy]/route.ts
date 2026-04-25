import { NextRequest, NextResponse } from "next/server";

const API = process.env.API_URL ?? "http://api:8000";

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
