"use client";

import { useEffect, useState } from "react";

export function BlurTextArea({
  defaultValue, onSave,
}: { defaultValue: string; onSave: (v: string) => Promise<boolean> }) {
  const [value, setValue] = useState(defaultValue);
  useEffect(() => setValue(defaultValue), [defaultValue]);
  return (
    <textarea
      rows={2}
      value={value}
      onChange={e => setValue(e.target.value)}
      onBlur={async () => {
        if (value === defaultValue) return;
        if (!(await onSave(value))) setValue(defaultValue);
      }}
      className="w-full resize-none rounded border border-h-line bg-h-bg px-2 py-1 text-h-ink focus:outline-none focus:ring-1 focus:ring-h-accent"
    />
  );
}
