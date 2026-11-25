import { useEffect, useState } from "react";
import { toast } from "sonner";
import { KeyRound, Plus, Trash2, Eye, EyeOff, Loader2 } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { errMsg } from "@/lib/api";

const KEY_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;

export default function EnvDialog({ open, onOpenChange, api, projectId, onSaved }) {
  const [rows, setRows] = useState(null);
  const [show, setShow] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setRows(null);
    api.get(`/projects/${projectId}/env`).then((r) => setRows(r.data.vars.length ? r.data.vars : [{ key: "REACT_APP_", value: "" }]))
      .catch((e) => toast.error(errMsg(e)));
  }, [open, api, projectId]);

  const set = (i, field, v) => setRows((rs) => rs.map((r, j) => (j === i ? { ...r, [field]: v } : r)));
  const filled = (rows || []).filter((r) => r.key.trim() && r.key.trim() !== "REACT_APP_");
  const invalid = filled.find((r) => !KEY_RE.test(r.key.trim()));
  const dup = filled.find((r, i) => filled.findIndex((x) => x.key.trim() === r.key.trim()) !== i);

  const save = async () => {
    setSaving(true);
    try {
      const r = await api.put(`/projects/${projectId}/env`, { vars: filled.map((x) => ({ key: x.key.trim(), value: x.value })) });
      toast.success(`${r.data.vars.length} variável(is) salvas — prévia atualizada`);
      onSaved(r.data.vars);
      onOpenChange(false);
    } catch (e) { toast.error(errMsg(e)); } finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl" data-testid="env-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><KeyRound className="h-4 w-4 text-primary" />Variáveis de ambiente</DialogTitle>
          <DialogDescription>
            Injetadas na prévia como <code className="text-primary">process.env.NOME</code>, sem editar código. Ficam criptografadas,
            não vão para o .zip nem para o GitHub. A IA só vê os nomes.
          </DialogDescription>
        </DialogHeader>
        {rows === null ? <p className="text-sm text-muted-foreground py-6">Carregando…</p> : (
          <div className="space-y-2 max-h-[50vh] overflow-y-auto scroll-thin pr-1">
            {rows.map((r, i) => (
              <div key={i} className="flex gap-2" data-testid={`env-row-${i}`}>
                <Input value={r.key} onChange={(e) => set(i, "key", e.target.value.toUpperCase().replace(/\s/g, "_"))} placeholder="REACT_APP_API_URL"
                  className={`font-mono text-xs w-[42%] ${r.key && !KEY_RE.test(r.key) ? "border-destructive" : ""}`} data-testid={`env-key-${i}`} />
                <Input value={r.value} onChange={(e) => set(i, "value", e.target.value)} placeholder="valor" type={show ? "text" : "password"}
                  className="font-mono text-xs flex-1" data-testid={`env-value-${i}`} />
                <Button size="icon" variant="ghost" className="h-9 w-9 shrink-0" onClick={() => setRows((rs) => rs.filter((_, j) => j !== i))} data-testid={`env-remove-${i}`}>
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            ))}
            <div className="flex gap-2 pt-1">
              <Button size="sm" variant="secondary" onClick={() => setRows((rs) => [...rs, { key: "REACT_APP_", value: "" }])} data-testid="env-add-btn"><Plus className="h-3.5 w-3.5 mr-1" />Adicionar</Button>
              <Button size="sm" variant="ghost" onClick={() => setShow((v) => !v)} data-testid="env-toggle-visibility">
                {show ? <EyeOff className="h-3.5 w-3.5 mr-1" /> : <Eye className="h-3.5 w-3.5 mr-1" />}{show ? "Ocultar valores" : "Mostrar valores"}
              </Button>
            </div>
            {(invalid || dup) && (
              <p className="text-xs text-red-300" data-testid="env-error">
                {invalid ? `Nome inválido: ${invalid.key}. Use letras, números e _.` : `Nome repetido: ${dup.key}`}
              </p>
            )}
          </div>
        )}
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancelar</Button>
          <Button onClick={save} disabled={!rows || saving || !!invalid || !!dup} data-testid="env-save-btn">
            {saving && <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />}Salvar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
