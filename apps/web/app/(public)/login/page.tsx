"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

export default function Login() {
  const r = useRouter();
  const [email, setEmail] = useState("rin.park@hartwood.test");
  const [password, setPassword] = useState("hartwood-dev");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    try {
      const resp = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          workspace_slug: "hartwood-joinery",
          email,
          password,
        }),
      });
      if (!resp.ok) {
        setErr("Invalid credentials");
        return;
      }
      r.replace("/home");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen grid place-items-center bg-h-bg">
      <form
        onSubmit={submit}
        className="w-[360px] rounded-2xl bg-h-surface p-8 shadow-sm border border-h-line space-y-4"
      >
        <h1 className="text-xl font-semibold text-h-ink">JoineryFlow</h1>
        <label className="block text-sm">
          <span className="text-h-muted">Email</span>
          <input
            type="email"
            className="mt-1 w-full rounded border border-h-line px-3 py-2"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </label>
        <label className="block text-sm">
          <span className="text-h-muted">Password</span>
          <input
            type="password"
            className="mt-1 w-full rounded border border-h-line px-3 py-2"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        {err && <p className="text-sm text-red-600">{err}</p>}
        <button
          disabled={busy}
          className="w-full rounded bg-h-accent text-white py-2 disabled:opacity-50"
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}
