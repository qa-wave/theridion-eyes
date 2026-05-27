import { useEffect, useRef, useState } from "react";
import { Code2, Copy, X } from "lucide-react";
import { sidecar } from "../lib/sidecar";
import { CodeEditor } from "./CodeEditor";
import { useFocusTrap } from "../hooks/useFocusTrap";

const LANGUAGES = [
  { id: "curl", label: "cURL" },
  { id: "python", label: "Python" },
  { id: "javascript", label: "JavaScript" },
  { id: "go", label: "Go" },
  { id: "java", label: "Java" },
  { id: "csharp", label: "C#" },
  { id: "php", label: "PHP" },
  { id: "ruby", label: "Ruby" },
];

const LANG_MAP: Record<string, string> = {
  curl: "plaintext", python: "python", javascript: "javascript",
  go: "go", java: "java", csharp: "csharp", php: "php", ruby: "ruby",
};

interface Props {
  open: boolean;
  onClose: () => void;
  method: string;
  url: string;
  headers: Record<string, string>;
  body: string | null;
}

export function CodegenModal({ open, onClose, method, url, headers, body }: Props) {
  const [lang, setLang] = useState("curl");
  const [code, setCode] = useState("");
  const [copied, setCopied] = useState(false);
  const trapRef = useRef<HTMLDivElement>(null);
  useFocusTrap(trapRef, open);

  useEffect(() => {
    if (!open || !url) return;
    sidecar.generateCode({ method, url, headers, body, language: lang })
      .then((r) => setCode(r.code))
      .catch(() => setCode("// Error generating code"));
  }, [open, lang, method, url, headers, body]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div ref={trapRef} className="glass flex h-[500px] w-[700px] max-h-[90vh] max-w-[95vw] animate-slide-in flex-col overflow-hidden rounded-xl border border-glass-light shadow-2xl shadow-black/60">
        <div className="flex items-center justify-between border-b border-glass px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-medium text-neutral-100">
            <Code2 className="h-4 w-4 text-cobweb-400" />
            Generate Code
          </div>
          <button type="button" onClick={onClose} className="rounded-md p-1 text-neutral-500 transition hover:bg-white/[0.05] hover:text-neutral-200">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex items-center gap-1 border-b border-glass px-2 py-1">
          {LANGUAGES.map((l) => (
            <button
              key={l.id}
              type="button"
              onClick={() => setLang(l.id)}
              className={`relative rounded-md px-2.5 py-1.5 text-[11px] transition ${
                lang === l.id
                  ? "bg-white/[0.06] text-neutral-100"
                  : "text-neutral-500 hover:bg-white/[0.03] hover:text-neutral-300"
              }`}
            >
              {l.label}
            </button>
          ))}
          <button
            type="button"
            onClick={() => {
              navigator.clipboard.writeText(code);
              setCopied(true);
              setTimeout(() => setCopied(false), 1500);
            }}
            className="ml-auto inline-flex items-center gap-1 rounded-md border border-glass px-2 py-1 text-[11px] text-neutral-400 transition hover:bg-white/[0.04] hover:text-neutral-200"
          >
            <Copy className="h-3 w-3" />
            {copied ? "Copied!" : "Copy"}
          </button>
        </div>

        <div className="min-h-0 flex-1">
          <CodeEditor
            value={code}
            language={(LANG_MAP[lang] ?? "plaintext") as "plaintext"}
            readOnly
          />
        </div>
      </div>
    </div>
  );
}
