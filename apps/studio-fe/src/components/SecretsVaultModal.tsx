import { useEffect, useState } from "react";
import { Eye, EyeOff, Lock, Loader2, Plus, Trash2, X } from "lucide-react";
import { sidecar, type VaultEntrySummary } from "../lib/sidecar";

interface Props {
  open: boolean;
  onClose: () => void;
}

export function SecretsVaultModal({ open, onClose }: Props) {
  const [entries, setEntries] = useState<VaultEntrySummary[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [newName, setNewName] = useState("");
  const [newValue, setNewValue] = useState("");
  const [newPass, setNewPass] = useState("");
  const [revealName, setRevealName] = useState<string | null>(null);
  const [revealPass, setRevealPass] = useState("");
  const [revealedValue, setRevealedValue] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    loadSecrets();
  }, [open]);

  async function loadSecrets() {
    try {
      const res = await sidecar.listSecrets();
      setEntries(res.entries);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function addSecret() {
    if (!newName.trim() || !newPass.trim()) return;
    setBusy(true); setError(null);
    try {
      await sidecar.writeSecret(newName.trim(), { passphrase: newPass, value: newValue });
      setShowAdd(false);
      setNewName(""); setNewValue(""); setNewPass("");
      await loadSecrets();
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  async function reveal() {
    if (!revealName || !revealPass) return;
    setBusy(true); setError(null);
    try {
      const res = await sidecar.revealSecret(revealName, revealPass);
      setRevealedValue(res.value);
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  async function remove(name: string) {
    if (!confirm(`Delete secret "${name}"?`)) return;
    try {
      await sidecar.deleteSecret(name);
      await loadSecrets();
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
  }

  if (!open) return null;

  const inputClass = "w-full rounded-md border border-glass bg-neutral-900/50 px-3 py-1.5 text-xs text-neutral-100 placeholder-neutral-600 focus:border-cobweb-500/40 focus:outline-none";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="glass flex h-[520px] w-[550px] max-h-[90vh] max-w-[95vw] animate-slide-in flex-col overflow-hidden rounded-xl border border-glass-light shadow-2xl shadow-black/60">
        <div className="flex items-center justify-between border-b border-glass px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-medium text-neutral-100">
            <Lock className="h-4 w-4 text-cobweb-400" /> Secrets Vault
          </div>
          <div className="flex items-center gap-1">
            <button type="button" onClick={() => setShowAdd(true)} className="rounded-md p-1 text-neutral-500 transition hover:bg-white/[0.05] hover:text-neutral-200" title="Add secret"><Plus className="h-4 w-4" /></button>
            <button type="button" onClick={onClose} className="rounded-md p-1 text-neutral-500 transition hover:bg-white/[0.05] hover:text-neutral-200"><X className="h-4 w-4" /></button>
          </div>
        </div>

        {error && <div className="border-b border-rose-800/30 bg-rose-950/20 px-4 py-2 text-xs text-rose-400">{error}</div>}

        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {showAdd && (
            <div className="rounded-lg border border-glass p-3 space-y-2 bg-neutral-900/30">
              <p className="text-[11px] uppercase tracking-wider text-neutral-500">New Secret</p>
              <input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="Secret name" className={inputClass} />
              <input value={newValue} onChange={(e) => setNewValue(e.target.value)} placeholder="Secret value" className={inputClass} type="password" />
              <input value={newPass} onChange={(e) => setNewPass(e.target.value)} placeholder="Passphrase to encrypt" className={inputClass} type="password" />
              <div className="flex gap-2">
                <button type="button" onClick={addSecret} disabled={busy} className="inline-flex items-center gap-1 rounded-md bg-cobweb-600/20 px-3 py-1.5 text-xs font-medium text-cobweb-400 transition hover:bg-cobweb-600/30 disabled:opacity-50">
                  {busy && <Loader2 className="h-3 w-3 animate-spin" />} Add
                </button>
                <button type="button" onClick={() => setShowAdd(false)} className="text-xs text-neutral-400 hover:text-neutral-200">Cancel</button>
              </div>
            </div>
          )}

          {entries.length === 0 && !showAdd && (
            <p className="py-8 text-center text-xs text-neutral-600">No secrets stored yet.</p>
          )}

          {entries.map((entry) => (
            <div key={entry.name} className="rounded-lg border border-glass px-3 py-2 space-y-2">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-medium text-neutral-200">{entry.name}</p>
                  <p className="text-[11px] text-neutral-500">{entry.updated_at}</p>
                </div>
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => { setRevealName(revealName === entry.name ? null : entry.name); setRevealedValue(null); setRevealPass(""); }}
                    className="rounded p-1 text-neutral-500 transition hover:bg-neutral-800 hover:text-neutral-200"
                    title="Reveal"
                  >
                    {revealName === entry.name ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                  </button>
                  <button type="button" onClick={() => remove(entry.name)} className="rounded p-1 text-neutral-600 transition hover:bg-neutral-800 hover:text-rose-400">
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
              {revealName === entry.name && (
                <div className="flex items-center gap-2">
                  <input value={revealPass} onChange={(e) => setRevealPass(e.target.value)} placeholder="Passphrase" type="password" className={`flex-1 ${inputClass}`} />
                  <button type="button" onClick={reveal} disabled={busy} className="rounded-md bg-cobweb-600/20 px-2 py-1 text-xs text-cobweb-400 hover:bg-cobweb-600/30 disabled:opacity-50">
                    {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : "Reveal"}
                  </button>
                </div>
              )}
              {revealName === entry.name && revealedValue !== null && (
                <pre className="rounded border border-glass bg-neutral-900/50 p-2 text-xs text-emerald-400 font-mono break-all">{revealedValue}</pre>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
