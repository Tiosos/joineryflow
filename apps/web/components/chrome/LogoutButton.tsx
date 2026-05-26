"use client";
import { useRouter } from "next/navigation";

export function LogoutButton() {
  const r = useRouter();
  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    r.replace("/login?reason=signed_out");
    r.refresh();
  }
  return (
    <button onClick={logout} className="text-sm text-h-muted hover:text-h-ink">
      Sign out
    </button>
  );
}
