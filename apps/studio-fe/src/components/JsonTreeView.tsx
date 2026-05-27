import { useCallback, useState } from "react";
import { ChevronDown, ChevronRight, Copy } from "lucide-react";

interface Props {
  data: unknown;
  rootPath?: string;
}

export function JsonTreeView({ data, rootPath = "$" }: Props) {
  return (
    <div className="p-3 font-mono text-xs leading-relaxed select-text">
      <JsonNode value={data} path={rootPath} depth={0} defaultOpen />
    </div>
  );
}

function JsonNode({
  keyName,
  value,
  path,
  depth,
  defaultOpen = false,
}: {
  keyName?: string;
  value: unknown;
  path: string;
  depth: number;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen || depth < 2);
  const [copied, setCopied] = useState<"key" | "value" | null>(null);

  const copyToClipboard = useCallback(
    (text: string, which: "key" | "value") => {
      navigator.clipboard.writeText(text).then(() => {
        setCopied(which);
        setTimeout(() => setCopied(null), 1200);
      });
    },
    [],
  );

  if (value === null) {
    return (
      <span className="inline">
        {keyName !== undefined && <KeyLabel name={keyName} path={path} onCopy={copyToClipboard} copied={copied === "key"} />}
        <span
          className="cursor-pointer text-neutral-500 italic hover:underline"
          onClick={() => copyToClipboard("null", "value")}
          title="Click to copy"
        >
          null
        </span>
        {copied === "value" && <CopiedBadge />}
      </span>
    );
  }

  if (typeof value === "string") {
    return (
      <span className="inline">
        {keyName !== undefined && <KeyLabel name={keyName} path={path} onCopy={copyToClipboard} copied={copied === "key"} />}
        <span
          className="cursor-pointer text-emerald-400 hover:underline"
          onClick={() => copyToClipboard(value, "value")}
          title="Click to copy"
        >
          &quot;{value.length > 200 ? value.slice(0, 200) + "..." : value}&quot;
        </span>
        {copied === "value" && <CopiedBadge />}
      </span>
    );
  }

  if (typeof value === "number") {
    return (
      <span className="inline">
        {keyName !== undefined && <KeyLabel name={keyName} path={path} onCopy={copyToClipboard} copied={copied === "key"} />}
        <span
          className="cursor-pointer text-amber-400 hover:underline"
          onClick={() => copyToClipboard(String(value), "value")}
          title="Click to copy"
        >
          {String(value)}
        </span>
        {copied === "value" && <CopiedBadge />}
      </span>
    );
  }

  if (typeof value === "boolean") {
    return (
      <span className="inline">
        {keyName !== undefined && <KeyLabel name={keyName} path={path} onCopy={copyToClipboard} copied={copied === "key"} />}
        <span
          className="cursor-pointer text-violet-400 hover:underline"
          onClick={() => copyToClipboard(String(value), "value")}
          title="Click to copy"
        >
          {String(value)}
        </span>
        {copied === "value" && <CopiedBadge />}
      </span>
    );
  }

  if (Array.isArray(value)) {
    const count = value.length;
    return (
      <div>
        <div
          className="group inline-flex cursor-pointer items-center gap-0.5"
          onClick={() => setOpen(!open)}
        >
          {open ? (
            <ChevronDown className="h-3 w-3 shrink-0 text-neutral-600" />
          ) : (
            <ChevronRight className="h-3 w-3 shrink-0 text-neutral-600" />
          )}
          {keyName !== undefined && <KeyLabel name={keyName} path={path} onCopy={copyToClipboard} copied={copied === "key"} />}
          <span className="text-neutral-500">
            {open ? "[" : `[...] `}
          </span>
          {!open && (
            <span className="text-neutral-600 text-[10px]">
              {count} item{count !== 1 ? "s" : ""}
            </span>
          )}
        </div>
        {open && (
          <>
            <div style={{ paddingLeft: "1rem" }}>
              {value.map((item, i) => (
                <div key={i}>
                  <JsonNode
                    keyName={String(i)}
                    value={item}
                    path={`${path}[${i}]`}
                    depth={depth + 1}
                  />
                  {i < value.length - 1 && <span className="text-neutral-600">,</span>}
                </div>
              ))}
            </div>
            <span className="text-neutral-500">]</span>
            <span className="ml-1 text-[10px] text-neutral-600">
              {count} item{count !== 1 ? "s" : ""}
            </span>
          </>
        )}
      </div>
    );
  }

  if (typeof value === "object" && value !== null) {
    const entries = Object.entries(value as Record<string, unknown>);
    const keyCount = entries.length;
    return (
      <div>
        <div
          className="group inline-flex cursor-pointer items-center gap-0.5"
          onClick={() => setOpen(!open)}
        >
          {open ? (
            <ChevronDown className="h-3 w-3 shrink-0 text-neutral-600" />
          ) : (
            <ChevronRight className="h-3 w-3 shrink-0 text-neutral-600" />
          )}
          {keyName !== undefined && <KeyLabel name={keyName} path={path} onCopy={copyToClipboard} copied={copied === "key"} />}
          <span className="text-neutral-500">
            {open ? "{" : `{...} `}
          </span>
          {!open && (
            <span className="text-neutral-600 text-[10px]">
              {keyCount} key{keyCount !== 1 ? "s" : ""}
            </span>
          )}
        </div>
        {open && (
          <>
            <div style={{ paddingLeft: "1rem" }}>
              {entries.map(([k, v], i) => (
                <div key={k}>
                  <JsonNode
                    keyName={k}
                    value={v}
                    path={`${path}.${k}`}
                    depth={depth + 1}
                  />
                  {i < entries.length - 1 && <span className="text-neutral-600">,</span>}
                </div>
              ))}
            </div>
            <span className="text-neutral-500">{"}"}</span>
            <span className="ml-1 text-[10px] text-neutral-600">
              {keyCount} key{keyCount !== 1 ? "s" : ""}
            </span>
          </>
        )}
      </div>
    );
  }

  // Fallback for unknown types
  return (
    <span className="inline">
      {keyName !== undefined && <KeyLabel name={keyName} path={path} onCopy={copyToClipboard} copied={copied === "key"} />}
      <span className="text-neutral-400">{String(value)}</span>
    </span>
  );
}

function KeyLabel({
  name,
  path,
  onCopy,
  copied,
}: {
  name: string;
  path: string;
  onCopy: (text: string, which: "key" | "value") => void;
  copied: boolean;
}) {
  return (
    <>
      <span
        className="cursor-pointer text-cobweb-400 hover:underline"
        onClick={(e) => {
          e.stopPropagation();
          onCopy(path, "key");
        }}
        title={`Copy path: ${path}`}
      >
        {name}
      </span>
      <span className="text-neutral-600">: </span>
      {copied && <CopiedBadge />}
    </>
  );
}

function CopiedBadge() {
  return (
    <span className="ml-1 inline-flex items-center gap-0.5 rounded bg-emerald-900/40 px-1 py-0 text-[9px] text-emerald-400">
      <Copy className="h-2 w-2" /> copied
    </span>
  );
}
