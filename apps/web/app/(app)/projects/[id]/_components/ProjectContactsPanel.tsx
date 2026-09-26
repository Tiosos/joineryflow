"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { ContactKind, CreateContactIn, ProjectContactOut } from "@/lib/pm-types";
import { projectContactsApi } from "@/lib/project-contacts-fetch";

interface Props {
  projectId: number;
  contacts: ProjectContactOut[];
  /** tracking:write — {editor, drafter, manager, admin}. */
  canEdit: boolean;
}

const KIND_LABEL: Record<ContactKind, string> = { office: "Office", site: "Site" };

export function ProjectContactsPanel({ projectId, contacts, canEdit }: Props) {
  const router = useRouter();
  const [adding, setAdding] = useState(false);
  const office = contacts.filter((c) => c.kind === "office");
  const site = contacts.filter((c) => c.kind === "site");

  return (
    <section className="rounded-lg border border-h-line bg-h-surface p-4">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-h-ink">Contacts</h2>
        {canEdit && !adding && (
          <button
            type="button"
            onClick={() => setAdding(true)}
            className="text-xs text-h-accent hover:underline"
          >
            + Add contact
          </button>
        )}
      </div>

      {adding && (
        <AddContactForm
          projectId={projectId}
          onDone={() => {
            setAdding(false);
            router.refresh();
          }}
          onCancel={() => setAdding(false)}
        />
      )}

      <ContactGroup
        title={KIND_LABEL.office}
        rows={office}
        canEdit={canEdit}
        onChanged={() => router.refresh()}
      />
      <ContactGroup
        title={KIND_LABEL.site}
        rows={site}
        canEdit={canEdit}
        onChanged={() => router.refresh()}
      />

      {contacts.length === 0 && !adding && (
        <p className="text-sm text-h-muted">No contacts on this project yet.</p>
      )}
    </section>
  );
}

function ContactGroup({
  title,
  rows,
  canEdit,
  onChanged,
}: {
  title: string;
  rows: ProjectContactOut[];
  canEdit: boolean;
  onChanged: () => void;
}) {
  if (rows.length === 0) return null;
  return (
    <div className="mb-3">
      <h3 className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-h-muted">
        {title}
      </h3>
      <ul className="grid gap-2">
        {rows.map((c) => (
          <ContactRow key={c.contact_id} contact={c} canEdit={canEdit} onChanged={onChanged} />
        ))}
      </ul>
    </div>
  );
}

function ContactRow({
  contact,
  canEdit,
  onChanged,
}: {
  contact: ProjectContactOut;
  canEdit: boolean;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function remove() {
    if (!confirm(`Remove contact ${contact.name}?`)) return;
    setBusy(true);
    setError(null);
    try {
      await projectContactsApi.remove(contact.contact_id);
      onChanged();
    } catch {
      setError("Failed to remove");
      setBusy(false);
    }
  }

  return (
    <li className="rounded border border-h-line bg-h-bg px-2 py-1.5 text-sm">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-h-ink">
          {contact.name}
          {contact.position && <span className="text-h-muted"> · {contact.position}</span>}
        </span>
        {canEdit && (
          <button
            type="button"
            disabled={busy}
            onClick={remove}
            className="text-xs text-h-muted hover:text-rose-700 disabled:opacity-50"
          >
            Remove
          </button>
        )}
      </div>
      {(contact.email || contact.mobile) && (
        <p className="mt-0.5 text-xs text-h-muted">
          {[contact.email, contact.mobile].filter(Boolean).join(" · ")}
        </p>
      )}
      {error && <p className="mt-0.5 text-xs text-rose-700">{error}</p>}
    </li>
  );
}

function AddContactForm({
  projectId,
  onDone,
  onCancel,
}: {
  projectId: number;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [form, setForm] = useState<CreateContactIn>({
    kind: "office",
    name: "",
    position: "",
    email: "",
    mobile: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await projectContactsApi.create(projectId, {
        ...form,
        name: form.name.trim(),
        position: form.position || null,
        email: form.email || null,
        mobile: form.mobile || null,
      });
      onDone();
    } catch {
      setError("Failed to add contact");
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="mb-3 grid gap-2 rounded border border-h-line bg-h-bg p-2">
      <div className="flex gap-2">
        <select
          value={form.kind}
          onChange={(e) => setForm({ ...form, kind: e.target.value as ContactKind })}
          className="rounded border border-h-line bg-white px-2 py-1 text-sm"
        >
          <option value="office">Office</option>
          <option value="site">Site</option>
        </select>
        <input
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          placeholder="Name *"
          className="flex-1 rounded border border-h-line bg-white px-2 py-1 text-sm"
        />
      </div>
      <div className="flex flex-wrap gap-2">
        <input
          value={form.position ?? ""}
          onChange={(e) => setForm({ ...form, position: e.target.value })}
          placeholder="Position"
          className="min-w-32 flex-1 rounded border border-h-line bg-white px-2 py-1 text-sm"
        />
        <input
          value={form.email ?? ""}
          onChange={(e) => setForm({ ...form, email: e.target.value })}
          placeholder="Email"
          className="min-w-32 flex-1 rounded border border-h-line bg-white px-2 py-1 text-sm"
        />
        <input
          value={form.mobile ?? ""}
          onChange={(e) => setForm({ ...form, mobile: e.target.value })}
          placeholder="Mobile"
          className="min-w-28 flex-1 rounded border border-h-line bg-white px-2 py-1 text-sm"
        />
      </div>
      {error && <p className="text-xs text-rose-700">{error}</p>}
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={busy || !form.name.trim()}
          className="rounded bg-h-accent px-2 py-1 text-xs font-medium text-white disabled:opacity-50"
        >
          Add
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded border border-h-line px-2 py-1 text-xs text-h-ink"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
