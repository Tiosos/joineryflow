import type { Me } from "@/lib/session";
import { LogoutButton } from "./LogoutButton";

interface TopBarProps {
  user: Me;
}

export function TopBar({ user }: TopBarProps) {
  return (
    <header className="flex items-center justify-between px-4 h-14 border-b border-h-line bg-h-surface">
      <div className="font-semibold text-h-ink">JoineryFlow</div>
      <div className="flex items-center gap-4 text-sm">
        <span className="text-h-muted">
          {user.full_name} · <span className="text-h-ink">{user.auth_role}</span>
        </span>
        <LogoutButton />
      </div>
    </header>
  );
}
