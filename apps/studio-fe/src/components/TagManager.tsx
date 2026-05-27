import { useEffect, useRef, useState } from "react";
import { X, Plus, Tag } from "lucide-react";
import { sidecar } from "../lib/sidecar";

const TAG_COLORS = [
  "#ef4444", "#f59e0b", "#10b981", "#3b82f6",
  "#8b5cf6", "#ec4899", "#06b6d4", "#6b7280",
];

/** Simple hash to pick a consistent color for a tag name. */
function tagColor(tag: string): string {
  let hash = 0;
  for (let i = 0; i < tag.length; i++) {
    hash = ((hash << 5) - hash + tag.charCodeAt(i)) | 0;
  }
  return TAG_COLORS[Math.abs(hash) % TAG_COLORS.length];
}

/** Small colored pill for displaying a tag. */
export function TagPill({ tag, onRemove }: { tag: string; onRemove?: () => void }) {
  const color = tagColor(tag);
  return (
    <span
      className="inline-flex items-center gap-0.5 rounded-full px-1.5 py-0 text-[9px] font-semibold leading-4"
      style={{ backgroundColor: `${color}20`, color, border: `1px solid ${color}40` }}
    >
      {tag}
      {onRemove && (
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onRemove(); }}
          className="ml-0.5 rounded-full p-0 hover:opacity-70"
        >
          <X className="h-2 w-2" />
        </button>
      )}
    </span>
  );
}

/** Inline tag pills for a request row in the sidebar. */
export function TagPills({ tags }: { tags: string[] }) {
  if (!tags || tags.length === 0) return null;
  return (
    <span className="ml-1 inline-flex gap-0.5 overflow-hidden">
      {tags.slice(0, 3).map((t) => (
        <TagPill key={t} tag={t} />
      ))}
      {tags.length > 3 && (
        <span className="text-[9px] text-neutral-500">+{tags.length - 3}</span>
      )}
    </span>
  );
}

interface TagManagerPopoverProps {
  collectionId: string;
  requestId: string;
  currentTags: string[];
  onTagsChange: (tags: string[]) => void;
  onClose: () => void;
}

/** Popover for managing tags on a request. */
export function TagManagerPopover({
  collectionId,
  requestId,
  currentTags,
  onTagsChange,
  onClose,
}: TagManagerPopoverProps) {
  const [input, setInput] = useState("");
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [allTags, setAllTags] = useState<string[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
    sidecar.listTags().then((res) => {
      const existing = res.tags.map((t) => t.tag);
      const combined = [...new Set([...existing, ...res.suggestions])];
      setAllTags(combined);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!input.trim()) {
      setSuggestions([]);
      return;
    }
    const q = input.toLowerCase();
    const filtered = allTags.filter(
      (t) => t.toLowerCase().includes(q) && !currentTags.includes(t)
    );
    setSuggestions(filtered.slice(0, 6));
  }, [input, allTags, currentTags]);

  async function addTag(tag: string) {
    const trimmed = tag.trim().toLowerCase();
    if (!trimmed || currentTags.includes(trimmed)) return;
    const newTags = [...currentTags, trimmed];
    try {
      const result = await sidecar.assignTags({ collection_id: collectionId, request_id: requestId, tags: newTags });
      onTagsChange(result);
    } catch {
      onTagsChange(newTags);
    }
    setInput("");
  }

  async function removeTag(tag: string) {
    try {
      const result = await sidecar.removeTag({ collection_id: collectionId, request_id: requestId, tag });
      onTagsChange(result);
    } catch {
      onTagsChange(currentTags.filter((t) => t !== tag));
    }
  }

  return (
    <div
      className="absolute left-full top-0 z-50 ml-2 w-64 rounded-lg border border-neutral-700 bg-neutral-900 p-3 shadow-xl"
      onClick={(e) => e.stopPropagation()}
    >
      <div className="mb-2 flex items-center justify-between">
        <span className="flex items-center gap-1.5 text-xs font-semibold text-neutral-200">
          <Tag className="h-3 w-3" /> Manage Tags
        </span>
        <button type="button" onClick={onClose} className="text-neutral-500 hover:text-neutral-300">
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Current tags */}
      {currentTags.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-1">
          {currentTags.map((t) => (
            <TagPill key={t} tag={t} onRemove={() => removeTag(t)} />
          ))}
        </div>
      )}

      {/* Input + autocomplete */}
      <div className="relative">
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && input.trim()) {
              e.preventDefault();
              addTag(input);
            } else if (e.key === "Escape") {
              onClose();
            }
          }}
          placeholder="Add tag..."
          className="w-full rounded-md border border-neutral-700 bg-neutral-800 px-2 py-1.5 text-xs text-neutral-100 placeholder-neutral-500 focus:border-cobweb-500/50 focus:outline-none"
        />
        {input.trim() && (
          <button
            type="button"
            onClick={() => addTag(input)}
            className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-0.5 text-neutral-400 hover:text-emerald-400"
          >
            <Plus className="h-3 w-3" />
          </button>
        )}
      </div>

      {/* Suggestions dropdown */}
      {suggestions.length > 0 && (
        <div className="mt-1 rounded-md border border-neutral-700 bg-neutral-800/80">
          {suggestions.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => addTag(s)}
              className="flex w-full items-center gap-2 px-2 py-1 text-left text-xs text-neutral-300 hover:bg-neutral-700/60"
            >
              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: tagColor(s) }} />
              {s}
            </button>
          ))}
        </div>
      )}

      {/* Color legend */}
      <div className="mt-2 flex gap-1">
        {TAG_COLORS.map((c) => (
          <span key={c} className="h-3 w-3 rounded-full opacity-60" style={{ backgroundColor: c }} />
        ))}
      </div>
    </div>
  );
}

interface TagFilterBarProps {
  activeTags: string[];
  onToggleTag: (tag: string) => void;
  onClear: () => void;
}

/** Tag filter bar shown above collection list when tags are in use. */
export function TagFilterBar({ activeTags, onToggleTag, onClear }: TagFilterBarProps) {
  const [availableTags, setAvailableTags] = useState<string[]>([]);

  useEffect(() => {
    sidecar.listTags().then((res) => {
      setAvailableTags(res.tags.map((t) => t.tag));
    }).catch(() => {});
  }, []);

  if (availableTags.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-1 border-b border-glass px-3 py-1.5">
      <Tag className="h-3 w-3 text-neutral-500" />
      {availableTags.slice(0, 10).map((tag) => {
        const active = activeTags.includes(tag);
        const color = tagColor(tag);
        return (
          <button
            key={tag}
            type="button"
            onClick={() => onToggleTag(tag)}
            className="rounded-full px-1.5 py-0 text-[9px] font-semibold leading-4 transition"
            style={{
              backgroundColor: active ? `${color}30` : "transparent",
              color: active ? color : "#737373",
              border: `1px solid ${active ? `${color}60` : "#404040"}`,
            }}
          >
            {tag}
          </button>
        );
      })}
      {activeTags.length > 0 && (
        <button
          type="button"
          onClick={onClear}
          className="ml-1 text-[9px] text-neutral-500 hover:text-neutral-300"
        >
          clear
        </button>
      )}
    </div>
  );
}
