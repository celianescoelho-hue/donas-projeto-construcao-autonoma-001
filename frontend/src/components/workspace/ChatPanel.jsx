import { useEffect, useRef, useState } from "react";
import { Send, Paperclip, Loader2, FilePlus2, FilePen, FileX2, Wrench, AlertTriangle, Bot } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const opIcon = { create: FilePlus2, edit: FilePen, delete: FileX2 };
const toolLabel = { list_files: "listando", read_file: "lendo", search_files: "buscando", replace_in_file: "editando trecho", create_file: "criando", delete_file: "apagando" };

export function ChangeCard({ c, onOpen, i = 0 }) {
  const Icon = opIcon[c.op] || FilePen;
  return (
    <button onClick={() => onOpen(c)} data-testid={`change-card-${c.path}`}
      className="anim-pop w-full flex items-center gap-2 rounded-md border bg-secondary/50 px-2.5 py-1.5 text-left transition-colors duration-150 hover:border-primary/60"
      style={{ animationDelay: `${Math.min(i, 8) * 40}ms` }}>
      <Icon className="h-3.5 w-3.5 text-primary shrink-0" />
      <span className="font-mono text-xs truncate flex-1">{c.path}</span>
      <span className="font-mono text-xs text-[hsl(var(--diff-add))]">+{c.added}</span>
      <span className="font-mono text-xs text-[hsl(var(--diff-del))]">−{c.removed}</span>
    </button>
  );
}

function RichText({ text }) {
  const parts = (text || "").split(/```[\w-]*\n?/);
  return parts.map((p, i) => i % 2 ? (
    <pre key={i} className="my-2 rounded-md bg-black/40 border p-3 text-xs overflow-x-auto scroll-thin">{p}</pre>
  ) : (
    <span key={i} className="whitespace-pre-wrap">{p.split(/(`[^`]+`)/).map((s, j) => s.startsWith("`") && s.endsWith("`") && s.length > 2
      ? <code key={j} className="rounded bg-secondary px-1 py-0.5 text-[12px] text-primary">{s.slice(1, -1)}</code> : s)}</span>
  ));
}

function Message({ m, onOpenDiff }) {
  if (m.role === "user") return (
    <div className="anim-rise ml-8 rounded-xl rounded-tr-sm bg-secondary px-4 py-3 text-sm" data-testid="chat-message-user"><RichText text={m.content} /></div>
  );
  return (
    <div className="anim-rise space-y-2" data-testid="chat-message-assistant">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Bot className="h-3.5 w-3.5 text-primary" /><span className="font-mono">{m.model || "donas"}</span>
        {m.cost > 0 && <span className="font-mono">· US$ {m.cost.toFixed(4)}</span>}
        {m.version && <span className="font-mono">· v{m.version.number}</span>}
      </div>
      {m.content && <div className="text-sm leading-relaxed"><RichText text={m.content} /></div>}
      {m.changes?.length > 0 && <div className="space-y-1.5">{m.changes.map((c, i) => <ChangeCard key={i} c={c} i={i} onOpen={onOpenDiff} />)}</div>}
      {m.error && <div className="flex gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-2.5 text-xs text-red-300" data-testid="chat-error"><AlertTriangle className="h-4 w-4 shrink-0" />{m.error}</div>}
    </div>
  );
}

function Live({ live, onOpenDiff }) {
  return (
    <div className="space-y-2" data-testid="chat-live">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span className="h-2 w-2 rounded-full bg-primary pulse-dot" /><span className="font-mono">{live.model || "donas"} trabalhando…</span>
      </div>
      {live.text && <div className="text-sm leading-relaxed"><RichText text={live.text} /></div>}
      {live.tools.slice(-4).map((t, i) => (
        <div key={i} className={`anim-rise flex items-center gap-2 font-mono text-[11px] ${t.error ? "text-red-300" : "text-muted-foreground"}`}>
          <Wrench className="h-3 w-3" />{toolLabel[t.name] || t.name} {t.path && <span className="truncate">{t.path}</span>}{t.error && <span className="truncate">— {t.error}</span>}
        </div>
      ))}
      {live.changes.length > 0 && <div className="space-y-1.5">{live.changes.map((c, i) => <ChangeCard key={i} c={c} i={i} onOpen={onOpenDiff} />)}</div>}
    </div>
  );
}

export default function ChatPanel({ messages, live, busy, onSend, models, model, onModel, onUploadClick, onOpenDiff, uploadDir }) {
  const [prompt, setPrompt] = useState("");
  const endRef = useRef(null);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [messages.length, live?.text, live?.changes.length, live?.tools.length]);
  const send = () => { if (!prompt.trim() || busy) return; onSend(prompt.trim()); setPrompt(""); };

  return (
    <div className="h-full flex flex-col bg-card/40" data-testid="chat-panel">
      <div className="flex-1 overflow-y-auto scroll-thin p-4 space-y-5">
        {messages.length === 0 && !live && (
          <div className="pt-10 text-center text-sm text-muted-foreground px-6" data-testid="chat-empty">
            <p className="font-display text-xl text-foreground font-bold mb-2">Descreva o que você quer criar</p>
            Ex.: “Um site para minha confeitaria com cardápio, galeria e formulário de encomenda, com API em FastAPI.”
          </div>
        )}
        {messages.map((m) => <Message key={m.id} m={m} onOpenDiff={onOpenDiff} />)}
        {live && <Live live={live} onOpenDiff={onOpenDiff} />}
        <div ref={endRef} />
      </div>
      <div className="border-t p-3 space-y-2">
        <Textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={3} data-testid="chat-input"
          placeholder={busy ? "A IA está trabalhando…" : "Peça uma página, um ajuste, uma API…"}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
          className="resize-none bg-background text-sm" />
        <div className="flex items-center gap-2">
          <Select value={model} onValueChange={onModel}>
            <SelectTrigger className="h-8 w-auto max-w-[190px] rounded-full text-xs font-mono" data-testid="model-select"><SelectValue placeholder="Modelo" /></SelectTrigger>
            <SelectContent>{models.map((m) => <SelectItem key={m.id} value={m.id} data-testid={`model-option-${m.id}`}>{m.name}</SelectItem>)}</SelectContent>
          </Select>
          <Button size="sm" variant="ghost" className="h-8 px-2" onClick={onUploadClick} title={`Enviar arquivos para /${uploadDir}`} data-testid="upload-files-btn">
            <Paperclip className="h-4 w-4" />
          </Button>
          <Button size="sm" className="ml-auto h-8 rounded-full" onClick={send} disabled={busy || !prompt.trim()} data-testid="chat-submit-button">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          </Button>
        </div>
      </div>
    </div>
  );
}
