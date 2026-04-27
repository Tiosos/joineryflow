"use client";

import { useRouter } from "next/navigation";
import type { ItemOut } from "@/lib/pm-types";

interface Props {
  item: ItemOut;
}

export function ItemHeader({ item }: Props) {
  const router = useRouter();

  function close() {
    window.close();
    // If window.close() was a no-op (browser blocked it), fall back.
    if (!window.closed) router.push("/home");
  }

  return (
    <header className="flex items-baseline justify-between border-b border-h-line pb-3">
      <div>
        <h1 className="text-lg font-semibold text-h-ink">
          ITEM #{item.item_number ?? item.id}
        </h1>
        <p className="text-sm text-h-muted">
          {item.code ?? "—"} · {item.stage ?? "—"} ·{" "}
          {item.description ?? ""}
        </p>
      </div>
      <button
        type="button"
        onClick={close}
        data-testid="close-editor"
        aria-label="Close editor"
        className="rounded px-2 py-1 text-h-muted hover:bg-h-bg hover:text-h-ink"
      >
        ✕
      </button>
    </header>
  );
}
