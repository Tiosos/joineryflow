"use client";

import { useMemo, useRef, useState } from "react";

import type { Mentionable } from "@/lib/comments-types";

const MAX_SUGGESTIONS = 6;

/** A textarea that offers workspace members after `@`. Choosing one inserts
 *  `@Full Name `; which members end up notified is decided from the final text
 *  (`mentionedIds`), not from what was clicked. */
export function MentionTextarea({
  value,
  onChange,
  members,
  placeholder,
  rows = 2,
  testId,
  id,
}: {
  value: string;
  onChange: (v: string) => void;
  members: Mentionable[];
  placeholder?: string;
  rows?: number;
  testId?: string;
  id?: string;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const [caret, setCaret] = useState(0);
  const [active, setActive] = useState(0);
  const [dismissedAt, setDismissedAt] = useState<number | null>(null);

  const query = useMemo(() => {
    const m = /(?:^|\s)@([^\s@]*)$/.exec(value.slice(0, caret));
    return m ? m[1] : null;
  }, [value, caret]);

  const suggestions = useMemo(() => {
    if (query === null || dismissedAt === caret) return [];
    const q = query.toLowerCase();
    return members
      .filter((m) => m.full_name.toLowerCase().includes(q))
      .slice(0, MAX_SUGGESTIONS);
  }, [query, members, dismissedAt, caret]);

  function choose(m: Mentionable) {
    const before = value.slice(0, caret).replace(/@([^\s@]*)$/, `@${m.full_name} `);
    onChange(before + value.slice(caret));
    requestAnimationFrame(() => {
      ref.current?.focus();
      ref.current?.setSelectionRange(before.length, before.length);
      setCaret(before.length);
    });
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (suggestions.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => (a + 1) % suggestions.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => (a - 1 + suggestions.length) % suggestions.length);
    } else if (e.key === "Enter" || e.key === "Tab") {
      e.preventDefault();
      choose(suggestions[Math.min(active, suggestions.length - 1)]);
    } else if (e.key === "Escape") {
      e.preventDefault();
      setDismissedAt(caret);
    }
  }

  return (
    <div className="relative">
      <textarea
        ref={ref}
        id={id}
        value={value}
        rows={rows}
        placeholder={placeholder}
        data-testid={testId}
        onChange={(e) => {
          onChange(e.target.value);
          setCaret(e.target.selectionStart);
          setActive(0);
        }}
        onKeyDown={onKeyDown}
        onKeyUp={(e) => setCaret(e.currentTarget.selectionStart)}
        onClick={(e) => setCaret(e.currentTarget.selectionStart)}
        className="w-full rounded border border-h-line bg-white px-2 py-1.5 text-sm"
      />
      {suggestions.length > 0 && (
        <ul
          role="listbox"
          data-testid="mention-suggestions"
          className="absolute left-0 top-full z-20 mt-1 w-64 overflow-hidden rounded border border-h-line bg-h-surface shadow"
        >
          {suggestions.map((m, i) => (
            <li key={m.id} role="option" aria-selected={i === active}>
              <button
                type="button"
                // mousedown, not click: keeps focus (and the caret) in the textarea.
                onMouseDown={(e) => {
                  e.preventDefault();
                  choose(m);
                }}
                className={[
                  "flex w-full items-center justify-between px-2 py-1.5 text-left text-sm",
                  i === active ? "bg-h-accent-soft text-h-ink" : "text-h-ink hover:bg-h-bg",
                ].join(" ")}
              >
                <span>{m.full_name}</span>
                <span className="text-xs text-h-muted">{m.auth_role}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
