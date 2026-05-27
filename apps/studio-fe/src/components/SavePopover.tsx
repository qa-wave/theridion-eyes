import { useEffect, useRef, useState } from "react";
import { FolderClosed, FolderPlus, X } from "lucide-react";
import type { StoredCollection } from "../lib/sidecar";

interface Props {
  open: boolean;
  collections: StoredCollection[];
  defaultName: string;
  onClose: () => void;
  onSave: (input: { collectionId: string; name: string }) => Promise<void>;
  onCreateCollection: (name: string) => Promise<StoredCollection>;
}

export function SavePopover({
  open,
  collections,
  defaultName,
  onClose,
  onSave,
  onCreateCollection,
}: Props) {
  const [name, setName] = useState(defaultName);
  const [pickedId, setPickedId] = useState<string | null>(
    collections[0]?.id ?? null,
  );
  const [creatingNew, setCreatingNew] = useState(collections.length === 0);
  const [newCollectionName, setNewCollectionName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    setName(defaultName);
    setPickedId(collections[0]?.id ?? null);
    setCreatingNew(collections.length === 0);
    setNewCollectionName("");
    setError(null);
  }, [open, defaultName, collections]);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") { e.preventDefault(); onClose(); }
    }
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    }
    window.addEventListener("keydown", onKey);
    const t = window.setTimeout(() => window.addEventListener("mousedown", onClick), 0);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onClick);
      window.clearTimeout(t);
    };
  }, [open, onClose]);

  if (!open) return null;

  async function handleSave() {
    setError(null);
    setBusy(true);
    try {
      let collectionId = pickedId;
      if (creatingNew) {
        const trimmed = newCollectionName.trim();
        if (!trimmed) { setError("Collection name can\u2019t be empty."); setBusy(false); return; }
        const created = await onCreateCollection(trimmed);
        collectionId = created.id;
      }
      if (!collectionId) { setError("Pick a collection or create one."); setBusy(false); return; }
      await onSave({ collectionId, name: name.trim() || defaultName });
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      ref={ref}
      role="dialog"
      aria-label="Save request"
      className="glass absolute right-4 top-full z-30 mt-1.5 w-80 animate-slide-in rounded-xl border border-glass-light shadow-xl shadow-black/50"
    >
      <div className="flex items-center justify-between border-b border-glass px-3 py-2">
        <span className="text-xs font-semibold uppercase tracking-widest text-neutral-400">
          Save request
        </span>
        <button
          type="button"
          onClick={onClose}
          className="rounded-md p-0.5 text-neutral-500 hover:bg-white/[0.05] hover:text-neutral-200"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      <div className="space-y-3 p-3">
        <Field label="Name">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Search repos"
            className="w-full rounded-md border border-glass bg-neutral-900/50 px-2 py-1.5 text-sm text-neutral-100 placeholder-neutral-600 focus:border-cobweb-500/40 focus:outline-none"
            autoFocus
          />
        </Field>

        <Field label="Collection">
          <div className="max-h-44 overflow-y-auto rounded-md border border-glass">
            {collections.map((c) => (
              <label
                key={c.id}
                className={`flex cursor-pointer items-center gap-2 px-2 py-1.5 text-sm transition ${
                  pickedId === c.id && !creatingNew
                    ? "bg-cobweb-950/30 text-cobweb-200"
                    : "text-neutral-300 hover:bg-white/[0.03]"
                }`}
              >
                <input
                  type="radio"
                  name="collection"
                  checked={pickedId === c.id && !creatingNew}
                  onChange={() => { setPickedId(c.id); setCreatingNew(false); }}
                  className="h-3 w-3 cursor-pointer accent-cobweb-500"
                />
                <FolderClosed className="h-3.5 w-3.5 text-neutral-500" />
                <span className="flex-1 truncate">{c.name}</span>
                <span className="text-[10px] text-neutral-600">{c.items.length}</span>
              </label>
            ))}
            <label
              className={`flex cursor-pointer items-center gap-2 border-t border-glass px-2 py-1.5 text-sm transition ${
                creatingNew
                  ? "bg-cobweb-950/30 text-cobweb-200"
                  : "text-neutral-400 hover:bg-white/[0.03]"
              }`}
            >
              <input
                type="radio"
                name="collection"
                checked={creatingNew}
                onChange={() => setCreatingNew(true)}
                className="h-3 w-3 cursor-pointer accent-cobweb-500"
              />
              <FolderPlus className="h-3.5 w-3.5 text-neutral-500" />
              <span>New collection&hellip;</span>
            </label>
          </div>
        </Field>

        {creatingNew && (
          <Field label="New collection name">
            <input
              value={newCollectionName}
              onChange={(e) => setNewCollectionName(e.target.value)}
              placeholder="e.g. Onboarding"
              className="w-full rounded-md border border-glass bg-neutral-900/50 px-2 py-1.5 text-sm text-neutral-100 placeholder-neutral-600 focus:border-cobweb-500/40 focus:outline-none"
            />
          </Field>
        )}

        {error && (
          <p className="rounded-md border border-rose-800/30 bg-rose-950/20 px-2 py-1 text-xs text-rose-300">
            {error}
          </p>
        )}

        <div className="flex justify-end gap-2 pt-1">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-glass px-3 py-1.5 text-xs text-neutral-400 transition hover:bg-white/[0.04] hover:text-neutral-200"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={busy}
            className="rounded-md bg-accent-gradient px-4 py-1.5 text-xs font-medium text-white shadow-glow-sm transition disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none"
          >
            {busy ? "Saving\u2026" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-xs">
      <span className="font-medium uppercase tracking-widest text-neutral-500">
        {label}
      </span>
      {children}
    </label>
  );
}
