import { useEffect, useRef, useState } from "react";
import { Send, Paperclip, Loader2, FilePlus2, FilePen, FileX2, Wrench, AlertTriangle, Bot, Undo2, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import AttachmentChips, { ACCEPT } from "@/components/workspace/AttachmentChips";

const opIcon = { create: FilePlus2, edit: FilePen, delete: FileX2 };
const toolLabel = { list_files: "listando", read_file: "lendo", search_files: "buscando", search_in_files: "buscando", replace_in_file: "editando trecho", create_file: "criando", delete_file: "apagando", move_or_copy_file: "movendo/copiando", clean_external_links: "limpando links", extract_zip: "descompactando" };
const PASTE_LIMIT = 6000;

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

function Message({ m, onOpenDiff, onUndo, busy }) {
  if (m.role === "user") return (
    <div className="anim-rise ml-8 rounded-xl rounded-tr-sm bg-secondary px-4 py-3 text-sm space-y-2" data-testid="chat-message-user">
      <RichText text={m.content} />
      <AttachmentChips items={m.attachments} testid="message-attachment" />
    </div>
  );
  return (
    <div className="anim-rise space-y-2" data-testid="chat-message-assistant">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Bot className="h-3.5 w-3.5 text-primary" /><span className="font-mono">{m.model || "donas"}</span>
        {m.cost > 0 && <span className="font-mono">· US$ {m.cost.toFixed(4)}</span>}
        {m.version && <span className="font-mono">· v{m.version.number}</span>}
        {m.version?.id && onUndo && (
          <button onClick={() => onUndo(m.version)} disabled={busy} className="ml-auto flex items-center gap-1 rounded px-1.5 py-0.5 hover:bg-secondary hover:text-foreground disabled:opacity-40"
            title="Voltar os arquivos para antes desta execução" data-testid={`undo-message-${m.version.number}`}>
            <Undo2 className="h-3 w-3" />Desfazer
          </button>
        )}
      </div>
      {m.content && <div className="text-sm leading-relaxed"><RichText text={m.content} /></div>}
      {m.changes?.length > 0 && <div className="space-y-1.5">{m.changes.map((c, i) => <ChangeCard key={i} c={c} i={i} onOpen={onOpenDiff} />)}</div>}
      <Warnings list={m.warnings} />
      {m.error && <ErrorBox text={m.error} />}
    </div>
  );
}

function ErrorBox({ text }) {
  return (
    <div className="flex gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-2.5 text-xs text-red-300" data-testid="chat-error">
      <AlertTriangle className="h-4 w-4 shrink-0" />{text}
    </div>
  );
}

function Warnings({ list }) {
  if (!list?.length) return null;
  return list.map((w, i) => (
    <div key={i} className="flex gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-2.5 text-xs text-amber-200" data-testid="chat-warning">
      <AlertTriangle className="h-4 w-4 shrink-0" />{w}
    </div>
  ));
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
      <Warnings list={live.warnings} />
      {live.error && <ErrorBox text={live.error} />}
    </div>
  );
}

export default function ChatPanel({ messages, live, busy, onSend, models, model, onModel, onAttach, onOpenDiff, showImportHint, onImportGithub, inject, onUndo, onStop }) {
  const [prompt, setPrompt] = useState("");
  const [atts, setAtts] = useState([]);
  const [drag, setDrag] = useState(false);
  const fileRef = useRef(null);
  const inputRef = useRef(null);
  const endRef = useRef(null);
  useEffect(() => {
    if (!inject) return;
    setPrompt((p) => (p.trim() ? `${p.trimEnd()}\n\n${inject.text}` : `${inject.text}\n\n`));
    setTimeout(() => { const el = inputRef.current; if (el) { el.focus(); el.selectionStart = el.selectionEnd = el.value.length; } }, 30);
  }, [inject]);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [messages.length, live?.text, live?.changes.length, live?.tools.length]);
  const uploading = atts.some((a) => a.uploading);

  const attach = async (fileList) => {
    const list = Array.from(fileList || []);
    if (!list.length) return;
    const temp = list.map((f) => ({ name: f.name, size: f.size, uploading: true }));
    setAtts((a) => [...a, ...temp]);
    const saved = await onAttach(list);
    setAtts((a) => {
      const rest = a.filter((x) => !temp.includes(x));
      const paths = new Set(rest.map((x) => x.path));
      return [...rest, ...saved.filter((x) => !paths.has(x.path))];
    });
  };

  const onPaste = (e) => {
    const files = e.clipboardData?.files;
    if (files?.length) { e.preventDefault(); attach(files); return; }
    const text = e.clipboardData?.getData("text") || "";
    if (text.length <= PASTE_LIMIT) return;
    e.preventDefault();
    const t = text.trimStart();
    const ext = /^<(!doctype|html)/i.test(t) ? "html" : /^[[{]/.test(t) ? "json" : "txt";
    const stamp = new Date().toTimeString().slice(0, 8).replace(/:/g, "");
    attach([new File([text], `colado-${stamp}.${ext}`, { type: "text/plain" })]);
    toast.info(`Texto grande (${Math.round(text.length / 1024)} KB) anexado como arquivo, sem colar no chat.`);
  };

  const send = () => {
    if (busy || uploading || (!prompt.trim() && !atts.length)) return;
    onSend(prompt.trim() || "Veja os arquivos anexados.", atts);
    setPrompt("");
    setAtts([]);
  };

  const dropProps = {
    onDragOver: (e) => { if (e.dataTransfer?.types?.includes("Files")) { e.preventDefault(); setDrag(true); } },
    onDragLeave: (e) => { if (!e.currentTarget.contains(e.relatedTarget)) setDrag(false); },
    onDrop: (e) => { if (!e.dataTransfer?.files?.length) return; e.preventDefault(); e.stopPropagation(); setDrag(false); attach(e.dataTransfer.files); },
  };

  return (
    <div className="h-full flex flex-col bg-card/40" data-testid="chat-panel">
      <div className="flex-1 overflow-y-auto scroll-thin p-4 space-y-5">
        {messages.length === 0 && !live && (
          <div className="pt-10 text-center text-sm text-muted-foreground px-6" data-testid="chat-empty">
            <p className="font-display text-xl text-foreground font-bold mb-2">Descreva o que você quer criar</p>
            Ex.: “Um site para minha confeitaria com cardápio, galeria e formulário de encomenda, com API em FastAPI.”
            {showImportHint && (
              <p className="mt-3 text-xs">Para continuar um projeto existente,{" "}
                <button onClick={onImportGithub} className="text-primary underline underline-offset-2" data-testid="chat-import-github-btn">importe do GitHub</button>
                {" "}— a plataforma baixa todos os arquivos antes da primeira mensagem.</p>
            )}
          </div>
        )}
        {messages.map((m) => <Message key={m.id} m={m} onOpenDiff={onOpenDiff} onUndo={onUndo} busy={busy} />)}
        {live && <Live live={live} onOpenDiff={onOpenDiff} />}
        <div ref={endRef} />
      </div>
      <div className={`relative border-t p-3 space-y-2 transition-colors duration-150 ${drag ? "bg-primary/10" : ""}`} {...dropProps} data-testid="chat-dropzone">
        {drag && (
          <div className="pointer-events-none absolute inset-2 z-10 grid place-items-center rounded-lg border-2 border-dashed border-primary bg-background/80 text-sm text-primary" data-testid="chat-drop-overlay">
            Solte para anexar (salvo em /uploads)
          </div>
        )}
        <AttachmentChips items={atts} onRemove={(a) => setAtts((x) => x.filter((y) => y !== a))} />
        <Textarea ref={inputRef} value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={3} data-testid="chat-input" onPaste={onPaste}
          placeholder={busy ? "A IA está trabalhando…" : "Peça uma página, um ajuste, uma API… (arraste arquivos aqui)"}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
          className="resize-none bg-background text-sm" />
        <input ref={fileRef} type="file" multiple hidden accept={ACCEPT} data-testid="chat-attach-input"
          onChange={(e) => { attach(e.target.files); e.target.value = ""; }} />
        <div className="flex items-center gap-2">
          <Select value={model} onValueChange={onModel}>
            <SelectTrigger className="h-8 w-auto max-w-[190px] rounded-full text-xs font-mono" data-testid="model-select"><SelectValue placeholder="Modelo" /></SelectTrigger>
            <SelectContent>{models.map((m) => <SelectItem key={m.id} value={m.id} data-testid={`model-option-${m.id}`}>{m.name}</SelectItem>)}</SelectContent>
          </Select>
          <Button size="sm" variant="ghost" className="h-8 px-2" onClick={() => fileRef.current?.click()} title="Anexar arquivos (imagens, .html, .json, .txt, .pdf, .zip) — salvos em /uploads" data-testid="upload-files-btn">
            <Paperclip className="h-4 w-4" />
          </Button>
          {busy ? (
            <Button size="sm" variant="destructive" className="ml-auto h-8 rounded-full gap-1.5" onClick={onStop} data-testid="chat-stop-button" title="Parar a IA e liberar o projeto">
              <Square className="h-3.5 w-3.5 fill-current" />Parar
            </Button>
          ) : (
            <Button size="sm" className="ml-auto h-8 rounded-full" onClick={send} disabled={uploading || (!prompt.trim() && !atts.length)} data-testid="chat-submit-button">
              {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
