import { cookies } from "next/headers";

import { SESSION_COOKIE_NAME } from "./session-cookie";

export { SESSION_COOKIE_NAME };
const COOKIE_NAME = SESSION_COOKIE_NAME;
const API = process.env.API_URL ?? "http://api:8000";

// `Me` / `can` live in ./permissions so client components can import them —
// this module is server-only via next/headers. Re-exported for callers that
// already import them from here.
export { can } from "./permissions";
export type { Action, Me, Module } from "./permissions";

import type { Me } from "./permissions";

export async function getSessionCookie(): Promise<string | null> {
  const c = await cookies();
  return c.get(COOKIE_NAME)?.value ?? null;
}

export async function fetchMe(): Promise<Me | null> {
  const tok = await getSessionCookie();
  if (!tok) return null;
  const r = await fetch(`${API}/auth/me`, {
    headers: { cookie: `${COOKIE_NAME}=${tok}` },
    cache: "no-store",
  });
  return r.ok ? ((await r.json()) as Me) : null;
}
