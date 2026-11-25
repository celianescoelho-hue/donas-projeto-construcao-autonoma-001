import { useEffect, useRef } from "react";
import { TerminalSquare, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";

const color = { error: "text-red-300", warn: "text-amber-300", agent: "text-primary", change: "text-[hsl(var(--diff-add))]", info: "text-sky-300", log: "text-zinc-300", system: "text-muted-foreground" };
const tag = { error: "ERR", warn: "WRN", agent: "IA ", change: "FS ", info: "INF", log: "LOG", system: "SYS" };

export default function TerminalPanel({ logs, onClear }) {
  const end = useRef(null);
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [logs.length]);
  return (
    <div className="h-full flex flex-col bg-[#07070a]" data-testid="terminal-panel">
      <div className="h-8 shrink-0 flex items-center gap-2 px-3 border-b">
        <TerminalSquare className="h-3.5 w-3.5 text-primary" />
        <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Terminal · logs</span>
        <span className="font-mono text-[10px] text-muted-foreground/60">{logs.length}</span>
        <Button size="icon" variant="ghost" className="ml-auto h-6 w-6" onClick={onClear} data-testid="terminal-clear-btn"><Trash2 className="h-3 w-3" /></Button>
      </div>
      <div className="flex-1 overflow-auto scroll-thin px-3 py-2 font-mono text-[11.5px] leading-[18px]" data-testid="terminal-output">
        {logs.length === 0 && <p className="text-muted-foreground">$ aguardando atividade da IA e da prévia…</p>}
        {logs.map((l) => (
          <div key={l.id} className={`flex gap-2 ${color[l.level] || color.log}`}>
            <span className="text-muted-foreground/50 shrink-0">{l.time}</span>
            <span className="shrink-0 opacity-70">{tag[l.level] || "LOG"}</span>
            <span className="whitespace-pre-wrap break-all">{l.msg}</span>
          </div>
        ))}
        <div ref={end} />
      </div>
    </div>
  );
}
