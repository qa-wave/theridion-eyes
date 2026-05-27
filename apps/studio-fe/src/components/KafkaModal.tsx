import { useState } from "react";
import { Database, Loader2, Play, Send, X } from "lucide-react";
import { sidecar } from "../lib/sidecar";
import { CodeEditor } from "./CodeEditor";

interface TopicInfo { name: string; partitions: number; }
interface ConsumedMessage {
  topic: string; partition: number; offset: number;
  key: string | null; value: string; timestamp: number;
  headers: Record<string, string>;
}

interface Props { open: boolean; onClose: () => void; }

export function KafkaModal({ open, onClose }: Props) {
  const [brokers, setBrokers] = useState("localhost:9092");
  const [topics, setTopics] = useState<TopicInfo[]>([]);
  const [selectedTopic, setSelectedTopic] = useState("");
  const [tab, setTab] = useState<"topics" | "produce" | "consume">("topics");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Produce state
  const [prodKey, setProdKey] = useState("");
  const [prodValue, setProdValue] = useState('{"event": "test"}');
  const [prodResult, setProdResult] = useState<string | null>(null);

  // Consume state
  const [messages, setMessages] = useState<ConsumedMessage[]>([]);
  const [maxMessages, setMaxMessages] = useState(10);

  if (!open) return null;

  async function loadTopics() {
    setBusy(true); setError(null);
    try {
      const res = await sidecar.kafkaTopics(brokers);
      setTopics(res.topics);
      if (res.topics.length > 0 && !selectedTopic) setSelectedTopic(res.topics[0].name);
      setTab("topics");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally { setBusy(false); }
  }

  async function produce() {
    if (!selectedTopic || !prodValue.trim()) return;
    setBusy(true); setError(null); setProdResult(null);
    try {
      const res = await sidecar.kafkaProduce({
        bootstrap_servers: brokers, topic: selectedTopic,
        key: prodKey || null, value: prodValue, headers: {},
      });
      setProdResult(`Sent to ${res.topic}:${res.partition} @ offset ${res.offset}`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally { setBusy(false); }
  }

  async function consume() {
    if (!selectedTopic) return;
    setBusy(true); setError(null);
    try {
      const res = await sidecar.kafkaConsume({
        bootstrap_servers: brokers, topic: selectedTopic,
        max_messages: maxMessages, timeout_seconds: 5,
      });
      setMessages(res.messages);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally { setBusy(false); }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="glass flex h-[640px] w-[900px] max-h-[90vh] max-w-[95vw] animate-slide-in flex-col overflow-hidden rounded-xl border border-glass-light shadow-2xl shadow-black/60">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-glass px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-medium text-neutral-100">
            <Database className="h-4 w-4 text-cobweb-400" />
            Kafka
          </div>
          <button type="button" onClick={onClose} className="rounded-md p-1 text-neutral-500 transition hover:bg-white/[0.05] hover:text-neutral-200">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Broker bar */}
        <div className="flex items-center gap-2 border-b border-glass px-4 py-2.5">
          <span className="shrink-0 rounded bg-orange-600/20 px-2 py-0.5 text-[10px] font-bold text-orange-300">
            KAFKA
          </span>
          <input
            value={brokers}
            onChange={(e) => setBrokers(e.target.value)}
            placeholder="localhost:9092"
            className="flex-1 rounded-md border border-glass bg-neutral-900/50 px-3 py-1.5 font-mono text-xs text-neutral-100 placeholder-neutral-600 focus:border-cobweb-500/40 focus:outline-none"
            spellCheck={false}
          />
          <button
            type="button"
            onClick={loadTopics}
            disabled={busy || !brokers.trim()}
            className="bg-accent-gradient inline-flex items-center gap-1.5 rounded-md px-4 py-1.5 text-xs font-medium text-white shadow-glow-sm transition disabled:opacity-40 disabled:shadow-none"
          >
            {busy && tab === "topics" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
            Connect
          </button>
        </div>

        {/* Tabs */}
        <div className="flex items-center gap-px border-b border-glass px-2">
          {(["topics", "produce", "consume"] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={`relative px-3 py-2 text-xs font-medium capitalize transition ${
                tab === t ? "text-neutral-100" : "text-neutral-400 hover:text-neutral-200"
              }`}
            >
              {t}
              {tab === t && <span className="absolute inset-x-2 bottom-0 h-0.5 rounded-full bg-accent-gradient-bar" />}
            </button>
          ))}
          {selectedTopic && (
            <span className="ml-auto mr-2 rounded-md border border-glass px-2 py-0.5 font-mono text-[10px] text-cobweb-400">
              {selectedTopic}
            </span>
          )}
        </div>

        {/* Error */}
        {error && (
          <div className="border-b border-rose-800/30 bg-rose-950/20 px-4 py-2 text-xs text-rose-400">{error}</div>
        )}

        {/* Content */}
        <div className="min-h-0 flex-1 overflow-auto">
          {tab === "topics" && (
            <div className="p-4">
              {topics.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-12 text-xs text-neutral-600">
                  <Database className="mb-2 h-8 w-8 text-neutral-800" />
                  Click Connect to browse topics
                </div>
              ) : (
                <div className="overflow-hidden rounded-lg border border-glass">
                  <div className="grid grid-cols-[1fr_100px] bg-neutral-900/30 px-4 py-1.5 text-[10px] font-semibold uppercase tracking-widest text-neutral-500">
                    <span>Topic</span><span className="text-right">Partitions</span>
                  </div>
                  {topics.map((t) => (
                    <button
                      key={t.name}
                      type="button"
                      onClick={() => setSelectedTopic(t.name)}
                      className={`grid w-full grid-cols-[1fr_100px] border-t border-glass px-4 py-2 text-left text-xs transition ${
                        selectedTopic === t.name
                          ? "bg-cobweb-950/20 text-cobweb-200"
                          : "text-neutral-300 hover:bg-white/[0.02]"
                      }`}
                    >
                      <span className="font-mono">{t.name}</span>
                      <span className="text-right text-neutral-500">{t.partitions}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {tab === "produce" && (
            <div className="flex flex-col gap-3 p-4">
              <div>
                <p className="mb-1 text-[10px] uppercase tracking-widest text-neutral-500">Key (optional)</p>
                <input
                  value={prodKey}
                  onChange={(e) => setProdKey(e.target.value)}
                  placeholder="message-key"
                  className="w-full rounded-md border border-glass bg-neutral-900/50 px-3 py-1.5 font-mono text-xs text-neutral-100 placeholder-neutral-600 focus:border-cobweb-500/40 focus:outline-none"
                  spellCheck={false}
                />
              </div>
              <div>
                <p className="mb-1 text-[10px] uppercase tracking-widest text-neutral-500">Value</p>
                <div className="h-40 overflow-hidden rounded-lg border border-glass">
                  <CodeEditor value={prodValue} onChange={setProdValue} language="json" />
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={produce}
                  disabled={busy || !selectedTopic}
                  className="bg-accent-gradient inline-flex items-center gap-1.5 rounded-md px-4 py-1.5 text-xs font-medium text-white shadow-glow-sm transition disabled:opacity-40 disabled:shadow-none"
                >
                  {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
                  Produce
                </button>
                {prodResult && <span className="text-xs text-emerald-400">{prodResult}</span>}
              </div>
            </div>
          )}

          {tab === "consume" && (
            <div className="flex flex-col gap-3 p-4">
              <div className="flex items-center gap-3">
                <label className="text-[10px] uppercase tracking-widest text-neutral-500">Max messages</label>
                <input
                  type="number"
                  value={maxMessages}
                  onChange={(e) => setMaxMessages(Number(e.target.value))}
                  min={1} max={100}
                  className="w-20 rounded-md border border-glass bg-neutral-900/50 px-2 py-1 text-xs text-neutral-100 focus:border-cobweb-500/40 focus:outline-none"
                />
                <button
                  type="button"
                  onClick={consume}
                  disabled={busy || !selectedTopic}
                  className="bg-accent-gradient inline-flex items-center gap-1.5 rounded-md px-4 py-1.5 text-xs font-medium text-white shadow-glow-sm transition disabled:opacity-40 disabled:shadow-none"
                >
                  {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
                  Consume
                </button>
                <span className="text-xs text-neutral-500">{messages.length} messages</span>
              </div>
              {messages.length === 0 ? (
                <div className="py-8 text-center text-xs text-neutral-600">
                  No messages yet. Click Consume to poll.
                </div>
              ) : (
                <div className="space-y-1">
                  {messages.map((m, i) => (
                    <div key={i} className="rounded-md border border-glass bg-neutral-900/30 p-3 text-xs">
                      <div className="mb-1 flex items-center gap-3 text-[10px] text-neutral-500">
                        <span>P:{m.partition}</span>
                        <span>O:{m.offset}</span>
                        {m.key && <span className="text-cobweb-400">key={m.key}</span>}
                        <span className="ml-auto">{new Date(m.timestamp).toLocaleTimeString()}</span>
                      </div>
                      <pre className="whitespace-pre-wrap break-all font-mono text-neutral-200">{m.value}</pre>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
