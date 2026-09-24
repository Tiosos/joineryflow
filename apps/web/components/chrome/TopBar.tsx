import Link from "next/link";
import type { Me } from "@/lib/session";
import { LogoutButton } from "./LogoutButton";
import { SearchBox } from "./SearchBox";

interface TopBarProps {
  user: Me;
  editorMode?: boolean;
}

export function TopBar({ user, editorMode }: TopBarProps) {
  return (
    <header className="flex items-center justify-between px-4 h-14 border-b border-h-line bg-h-surface">
      <div>
        {editorMode ? (
          <Link href="/dashboard" className="text-sm text-h-muted hover:text-h-ink">
            ← Return to dashboard
          </Link>
        ) : (
          <div className="font-semibold text-h-ink">JoineryFlow</div>
        )}
      </div>
      <SearchBox />
      <div className="flex items-center gap-4 text-sm">
        <span className="text-h-muted">
          {user.full_name} · <span className="text-h-ink">{user.auth_role}</span>
        </span>
        <LogoutButton />
      </div>
    </header>
  );
}
