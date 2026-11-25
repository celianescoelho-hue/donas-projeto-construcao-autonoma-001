import { useEffect, useMemo, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { toast } from "sonner";
import { Lock, Loader2, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useApi, useMe, errMsg } from "@/lib/api";

export default function ImportDialog({ open, onOpenChange, projectId, onImported }) {
  const api = useApi();
  const { me } = useMe();
  const navigate = useNavigate();
  const [repos, setRepos] = useState(null);
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(null);
  const [branches, setBranches] = useState([]);
  const [branch, setBranch] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open || !me?.github_login) return;
    setSel(null); setRepos(null);
    api.get("/github/repos").then((r) => setRepos(r.data)).catch((e) => { toast.error(errMsg(e)); setRepos([]); });
  }, [open, me?.github_login, api]);

  const choose = async (r) => {
    setSel(r); setBranch(r.default_branch); setBranches([r.default_branch]);
    try { const b = await api.get("/github/branches", { params: { owner: r.owner, repo: r.name } }); setBranches(b.data); } catch (e) { toast.error(errMsg(e)); }
  };

  const doImport = async () => {
    setBusy(true);
    try {
      const body = { owner: sel.owner, repo: sel.name, branch, name: sel.name };
      const r = projectId ? await api.post(`/projects/${projectId}/github/import`, body) : await api.post("/projects/import", body);
      toast.success(`${r.data.imported} arquivos importados${r.data.skipped_count ? ` · ${r.data.skipped_count} ficaram de fora` : ""}`);
      onOpenChange(false);
      if (projectId) onImported?.(r.data);
      else navigate(`/p/${r.data.project_id}`);
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  const filtered = useMemo(() => (repos || []).filter((r) => r.full_name.toLowerCase().includes(q.toLowerCase())), [repos, q]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" data-testid="import-github-dialog">
        <DialogHeader>
          <DialogTitle>Importar do GitHub</DialogTitle>
          <DialogDescription>Pastas geradas (node_modules, build, dist, .git, ambientes Python) e arquivos acima de 5 MB ficam de fora.</DialogDescription>
        </DialogHeader>
        {!me?.github_login ? (
          <div className="text-sm text-muted-foreground" data-testid="github-not-connected">
            Conecte sua conta do GitHub primeiro. <Link to="/settings" className="text-primary underline">Ir para Configurações</Link>
          </div>
        ) : !sel ? (
          <div className="space-y-3">
            <div className="relative">
              <Search className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <Input className="pl-9" placeholder="Buscar repositório" value={q} onChange={(e) => setQ(e.target.value)} data-testid="repo-search-input" />
            </div>
            <div className="max-h-80 overflow-y-auto scroll-thin rounded-md border divide-y" data-testid="repo-list">
              {repos === null ? <p className="p-4 text-sm text-muted-foreground flex items-center gap-2"><Loader2 className="h-4 w-4 animate-spin" />Carregando repositórios…</p> :
                filtered.length === 0 ? <p className="p-4 text-sm text-muted-foreground">Nenhum repositório.</p> :
                filtered.map((r) => (
                  <button key={r.full_name} onClick={() => choose(r)} data-testid={`repo-item-${r.name}`}
                    className="w-full text-left px-4 py-2.5 text-sm flex items-center gap-2 transition-colors duration-150 hover:bg-secondary">
                    <span className="font-mono truncate">{r.full_name}</span>
                    {r.private && <Lock className="h-3 w-3 text-primary shrink-0" />}
                  </button>
                ))}
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <p className="font-mono text-sm">{sel.full_name}</p>
            <div>
              <p className="text-xs text-muted-foreground mb-1.5">Branch</p>
              <Select value={branch} onValueChange={setBranch}>
                <SelectTrigger data-testid="branch-select"><SelectValue /></SelectTrigger>
                <SelectContent>{branches.map((b) => <SelectItem key={b} value={b}>{b}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="flex gap-2 justify-end">
              <Button variant="ghost" onClick={() => setSel(null)}>Voltar</Button>
              <Button onClick={doImport} disabled={busy || !branch} data-testid="confirm-import-btn">
                {busy && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}{busy ? "Importando…" : "Importar"}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
