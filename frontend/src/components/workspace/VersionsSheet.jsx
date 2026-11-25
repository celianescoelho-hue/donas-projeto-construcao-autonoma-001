import { useEffect, useState } from "react";
import { toast } from "sonner";
import { History, RotateCcw, Loader2 } from "lucide-react";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { errMsg } from "@/lib/api";

const srcLabel = { ai: "IA", manual: "manual", upload: "upload", restore: "restauração" };

export default function VersionsSheet({ open, onOpenChange, api, projectId, onRestored }) {
  const [items, setItems] = useState(null);
  const [busy, setBusy] = useState(null);
  useEffect(() => {
    if (!open) return;
    setItems(null);
    api.get(`/projects/${projectId}/versions`).then((r) => setItems(r.data)).catch((e) => toast.error(errMsg(e)));
  }, [open, api, projectId]);
  const restore = async (v) => {
    setBusy(v.id);
    try {
      const r = await api.post(`/projects/${projectId}/versions/${v.id}/restore`);
      toast.success(`Restaurado para a versão ${v.number} (${r.data.changed} arquivos)`);
      onRestored(); onOpenChange(false);
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(null); }
  };
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-[420px] sm:max-w-[420px] overflow-y-auto scroll-thin" data-testid="versions-sheet">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2"><History className="h-4 w-4 text-primary" />Histórico de versões</SheetTitle>
          <SheetDescription>Volte o projeto para como estava depois de qualquer versão.</SheetDescription>
        </SheetHeader>
        <div className="mt-6 space-y-2">
          {items === null ? <p className="text-sm text-muted-foreground">Carregando…</p> : items.length === 0 ? <p className="text-sm text-muted-foreground">Nenhuma versão ainda.</p> :
            items.map((v, i) => (
              <div key={v.id} className="anim-rise rounded-lg border p-3" style={{ animationDelay: `${i * 30}ms` }} data-testid={`version-item-${v.number}`}>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs text-primary">v{v.number}</span>
                  <span className="text-[10px] font-mono uppercase text-muted-foreground">{srcLabel[v.source] || v.source}</span>
                  <span className="ml-auto text-[11px] text-muted-foreground">{new Date(v.created_at).toLocaleString("pt-BR")}</span>
                </div>
                <p className="text-sm mt-1.5 line-clamp-2">{v.label}</p>
                <p className="text-[11px] font-mono text-muted-foreground mt-1 truncate">{v.count} arquivo(s): {v.paths.slice(0, 3).join(", ")}</p>
                {i > 0 && (
                  <Button size="sm" variant="secondary" className="mt-2 h-7 text-xs" disabled={!!busy} onClick={() => restore(v)} data-testid={`restore-version-${v.number}`}>
                    {busy === v.id ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : <RotateCcw className="h-3 w-3 mr-1" />}Restaurar esta versão
                  </Button>
                )}
              </div>
            ))}
        </div>
      </SheetContent>
    </Sheet>
  );
}
