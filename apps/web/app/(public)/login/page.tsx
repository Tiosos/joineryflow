"use client";
import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

const WORKSPACE_SLUG = "hartwood-joinery";
const IS_DEV = process.env.NODE_ENV === "development";
const DEV_EMAIL = IS_DEV ? "rin.park@hartwood.test" : "";
const DEV_PASSWORD = IS_DEV ? "hartwood-dev" : "";

const REASON_COPY: Record<string, string> = {
  signed_out: "You've been signed out.",
  expired: "Your session expired — please sign in again.",
};

// Allow only relative paths starting with a single "/" — blocks open-redirect.
function safeNext(raw: string | null): string {
  if (!raw) return "/dashboard";
  if (!raw.startsWith("/") || raw.startsWith("//")) return "/dashboard";
  return raw;
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <Login />
    </Suspense>
  );
}

function Login() {
  const r = useRouter();
  const sp = useSearchParams();
  const reason = sp?.get("reason") ?? null;
  const next = safeNext(sp?.get("next") ?? null);

  const [email, setEmail] = useState(DEV_EMAIL);
  const [password, setPassword] = useState(DEV_PASSWORD);
  const [err, setErr] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(
    reason && REASON_COPY[reason] ? REASON_COPY[reason] : null,
  );
  const [busy, setBusy] = useState(false);
  const [stats, setStats] = useState<{ projects_live: number; parts_tracked: number; suppliers: number } | null>(null);

  useEffect(() => {
    fetch(`/api/public/stats?workspace_slug=${encodeURIComponent(WORKSPACE_SLUG)}`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => { if (data) setStats(data); })
      .catch(() => null);
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setNotice(null);
    setBusy(true);
    try {
      const resp = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          workspace_slug: WORKSPACE_SLUG,
          email,
          password,
        }),
      });
      if (!resp.ok) {
        setErr("Invalid credentials");
        return;
      }
      r.replace(next);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen bg-h-bg">
      {/* Left — brand panel */}
      <section
        aria-label="JoineryFlow"
        className="relative hidden flex-1 flex-col justify-between overflow-hidden bg-h-ink p-10 text-h-bg md:flex"
      >
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{
            backgroundImage:
              "linear-gradient(rgba(255,255,255,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.04) 1px, transparent 1px)",
            backgroundSize: "28px 28px",
          }}
        />

        <div className="relative z-[2] flex items-center gap-2.5">
          <div
            aria-hidden
            className="flex h-7 w-7 items-center justify-center rounded-[7px] bg-h-accent text-[15px] font-bold text-h-bg"
          >
            ◴
          </div>
          <div className="text-base font-semibold tracking-[-0.01em]">
            Joinery<span className="text-h-accent">Flow</span>
          </div>
        </div>

        <div className="relative z-[2]">
          <h1 className="mb-3.5 max-w-[420px] text-[28px] font-semibold leading-[1.15] tracking-[-0.5px]">
            Every joint, every delivery, every drawing — in one place.
          </h1>
          <p
            className="m-0 max-w-[380px] text-[13px] leading-[1.55]"
            style={{ color: "#a8a49a" }}
          >
            Built for custom joinery shops. Cutlists, hardware, samples, shop
            drawings, and orderbooks move together — not in separate
            spreadsheets.
          </p>
        </div>

        <div
          className="relative z-[2] flex gap-7 text-[11px]"
          style={{ color: "#8f8b80" }}
        >
          <div>
            <b className="block text-[13px] font-semibold text-h-bg">
              {stats ? stats.projects_live.toLocaleString() : "—"}
            </b>
            projects live
          </div>
          <div>
            <b className="block text-[13px] font-semibold text-h-bg">
              {stats ? stats.parts_tracked.toLocaleString() : "—"}
            </b>
            parts tracked
          </div>
          <div>
            <b className="block text-[13px] font-semibold text-h-bg">
              {stats ? stats.suppliers.toLocaleString() : "—"}
            </b>
            suppliers
          </div>
        </div>
      </section>

      {/* Right — form panel */}
      <section
        aria-label="Sign in"
        className="flex w-full flex-col bg-h-surface p-12 md:w-[420px] md:px-11"
      >
        <div className="text-xl font-semibold tracking-[-0.3px] text-h-ink">
          Welcome back
        </div>
        <p className="mb-7 mt-1 text-[13px] text-h-ink2">
          Sign in to continue to your workshop.
        </p>

        {notice && (
          <div
            role="status"
            className="mb-5 flex items-start gap-2 rounded-[5px] border border-h-line bg-h-surface-alt px-3 py-2 text-[12px] text-h-ink2"
          >
            <span className="flex-1">{notice}</span>
            <button
              type="button"
              aria-label="Dismiss"
              onClick={() => setNotice(null)}
              className="text-h-ink3 hover:text-h-ink"
            >
              ×
            </button>
          </div>
        )}

        <form onSubmit={submit} noValidate>
          <label
            htmlFor="email"
            className="text-[11px] font-semibold uppercase tracking-[0.04em] text-h-ink2"
          >
            Email
          </label>
          <input
            id="email"
            type="email"
            autoComplete="username"
            autoFocus
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mb-3.5 mt-1 w-full rounded-[5px] border border-h-line bg-h-surface p-2 text-[13px] text-h-ink outline-none focus:border-h-accent focus:shadow-[0_0_0_3px_var(--h-accent-soft)]"
          />

          <div className="flex items-baseline justify-between">
            <label
              htmlFor="password"
              className="text-[11px] font-semibold uppercase tracking-[0.04em] text-h-ink2"
            >
              Password
            </label>
            <a
              href="#"
              onClick={(e) => e.preventDefault()}
              className="text-[11px] text-h-accent hover:underline"
            >
              Forgot?
            </a>
          </div>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            aria-invalid={err ? "true" : "false"}
            className="mt-1 w-full rounded-[5px] border border-h-line bg-h-surface p-2 text-[13px] text-h-ink outline-none focus:border-h-accent focus:shadow-[0_0_0_3px_var(--h-accent-soft)] aria-[invalid=true]:border-h-bad"
          />
          {err ? (
            <p role="alert" className="mb-3 mt-1 text-[12px] text-h-bad">
              {err}
            </p>
          ) : (
            <div className="mb-3.5" />
          )}

          <label className="text-[11px] font-semibold uppercase tracking-[0.04em] text-h-ink2">
            Workspace
          </label>
          <div
            className="mb-5 mt-1 flex items-center rounded-[5px] border border-h-line bg-h-surface-alt"
            title="Single-tenant — fixed for now"
          >
            <div className="flex-1 px-2.5 py-2 text-[12px] text-h-ink">
              {WORKSPACE_SLUG}
            </div>
            <svg
              aria-hidden
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="mr-2.5 text-h-ink3"
            >
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </div>

          <button
            type="submit"
            disabled={busy}
            className="flex w-full items-center justify-center gap-1.5 rounded-[5px] border border-h-accent bg-h-accent px-3 py-2 text-[13px] font-medium text-white hover:brightness-95 disabled:opacity-50"
          >
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <div className="my-5 flex items-center gap-2.5 text-[11px] text-h-ink3">
          <div className="h-px flex-1 bg-h-line" />
          or
          <div className="h-px flex-1 bg-h-line" />
        </div>
        <button
          type="button"
          onClick={(e) => e.preventDefault()}
          className="flex w-full items-center justify-center gap-1.5 rounded-[5px] border border-h-line bg-h-surface px-3 py-2 text-[12px] font-medium text-h-ink hover:bg-h-surface-alt"
        >
          <svg
            aria-hidden
            width="13"
            height="13"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
          </svg>
          Continue with SSO
        </button>

        <div className="flex flex-1 flex-col justify-end">
          <p className="mt-5 text-center text-[11px] text-h-ink3">
            New shop?{" "}
            <a
              href="#"
              onClick={(e) => e.preventDefault()}
              className="font-medium text-h-ink hover:underline"
            >
              Request access
            </a>
          </p>
        </div>
      </section>
    </main>
  );
}
