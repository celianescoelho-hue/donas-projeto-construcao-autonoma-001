import { useEffect, useRef, useState } from "react";
import { Save, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function CodeEditor({ file, assetUrl, onSave }) {
  const [draft, setDraft] = useState(file?.content ?? "");
  const [saving, setSaving] = useState(false);
  const gutter = useRef(null);
  useEffect(() => { setDraft(file?.content ?? ""); }, [file?.path, file?.content]);
  const dirty = file && file.kind === "text" && draft !== file.content;
  const save = async () => { if (!dirty) return; setSaving(true); try { await onSave(file.path, draft); } finally { setSaving(false); } };

  if (!file) return <div className="h-full grid place-items-center text-sm text-muted-foreground" data-testid="editor-empty">Selecione um arquivo</div>;
  const header = (
    <div className="h-9 shrink-0 flex items-center gap-2 px-3 border-b">
      <span className="font-mono text-xs truncate" data-testid="editor-path">{file.path}</span>
      {dirty && <span className="h-1.5 w-1.5 rounded-full bg-primary" data-testid="editor-dirty" />}
      {file.kind === "text" && (
        <Button size="sm" variant={dirty ? "default" : "ghost"} className="ml-auto h-6 text-xs" disabled={!dirty || saving} onClick={save} data-testid="editor-save-btn">
          {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3 mr-1" />}Salvar
        </Button>
      )}
    </div>
  );
  if (file.kind !== "text") return (
    <div className="h-full flex flex-col">{header}
      <div className="flex-1 grid place-items-center p-6 bg-[repeating-conic-gradient(#17171c_0_25%,#111115_0_50%)] bg-[length:20px_20px]">
        {assetUrl ? <img src={assetUrl} alt={file.path} className="max-w-full max-h-full object-contain" data-testid="editor-image" /> : <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />}
      </div>
      {file.summary && <p className="border-t px-3 py-2 text-xs text-muted-foreground">{file.summary}</p>}
    </div>
  );
  const lines = draft.split("\n").length;
  return (
    <div className="h-full flex flex-col" data-testid="code-editor">
      {header}
      <div className="flex-1 flex min-h-0 bg-[#09090c]">
        <div ref={gutter} className="shrink-0 overflow-hidden py-3 pl-3 pr-2 text-right font-mono text-[12px] leading-[20px] text-muted-foreground/50 select-none">
          {Array.from({ length: lines }, (_, i) => <div key={i}>{i + 1}</div>)}
        </div>
        <textarea value={draft} spellCheck={false} data-testid="code-editor-textarea"
          onChange={(e) => setDraft(e.target.value)}
          onScroll={(e) => { if (gutter.current) gutter.current.scrollTop = e.target.scrollTop; }}
          onKeyDown={(e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); save(); }
            if (e.key === "Tab") {
              e.preventDefault();
              const t = e.target, s = t.selectionStart;
              setDraft(draft.slice(0, s) + "  " + draft.slice(t.selectionEnd));
              requestAnimationFrame(() => { t.selectionStart = t.selectionEnd = s + 2; });
            }
          }}
          className="code flex-1 resize-none bg-transparent py-3 pr-4 text-[12px] leading-[20px] outline-none whitespace-pre overflow-auto scroll-thin text-zinc-200" />
      </div>
    </div>
  );
}
