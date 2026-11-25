import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { toast } from "sonner";
import { Plus, Github, FolderGit2, Trash2, Pencil, FileCode2 } from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import { ptBR } from "date-fns/locale";
import AppHeader from "@/components/AppHeader";
import ImportDialog from "@/components/ImportDialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { useApi, useMe, errMsg } from "@/lib/api";

function NameDialog({ open, onOpenChange, title, initial, onSubmit, testid }) {
  const [name, setName] = useState(initial || "");
  useEffect(() => { if (open) setName(initial || ""); }, [open, initial]);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={`${testid}-dialog`}>
        <DialogHeader><DialogTitle>{title}</DialogTitle></DialogHeader>
        <Input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="Nome do projeto" data-testid={`${testid}-input`}
          onKeyDown={(e) => e.key === "Enter" && name.trim() && onSubmit(name.trim())} />
        <DialogFooter>
          <Button disabled={!name.trim()} onClick={() => onSubmit(name.trim())} data-testid={`${testid}-submit`}>Salvar</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ProjectCard({ p, i, onRename, onDelete }) {
  const navigate = useNavigate();
  return (
    <div data-testid={`project-card-${p.id}`} onClick={() => navigate(`/p/${p.id}`)}
      className="anim-rise group cursor-pointer rounded-xl border bg-card p-5 transition-colors duration-150 hover:border-primary/60"
      style={{ animationDelay: `${i * 40}ms` }}>
      <div className="flex items-start gap-3">
        <div className="h-9 w-9 rounded-lg bg-secondary grid place-items-center">
          {p.github ? <FolderGit2 className="h-4 w-4 text-primary" /> : <FileCode2 className="h-4 w-4 text-primary" />}
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="font-semibold truncate" data-testid={`project-name-${p.id}`}>{p.name}</h3>
          <p className="text-xs text-muted-foreground mt-1 font-mono truncate">
            {p.github ? `${p.github.owner}/${p.github.repo} · ${p.github.branch}` : "Projeto local"}
          </p>
        </div>
        <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity duration-150" onClick={(e) => e.stopPropagation()}>
          <Button size="icon" variant="ghost" className="h-8 w-8" onClick={() => onRename(p)} data-testid={`rename-project-${p.id}`}><Pencil className="h-3.5 w-3.5" /></Button>
          <Button size="icon" variant="ghost" className="h-8 w-8 hover:text-destructive" onClick={() => onDelete(p)} data-testid={`delete-project-${p.id}`}><Trash2 className="h-3.5 w-3.5" /></Button>
        </div>
      </div>
      <div className="mt-6 flex items-center justify-between text-xs text-muted-foreground">
        <span className="font-mono">{p.file_count} arquivos</span>
        <span>{formatDistanceToNow(new Date(p.updated_at), { addSuffix: true, locale: ptBR })}</span>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const api = useApi();
  const { me } = useMe();
  const navigate = useNavigate();
  const [projects, setProjects] = useState(null);
  const [creating, setCreating] = useState(false);
  const [renaming, setRenaming] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const [importing, setImporting] = useState(false);

  const load = () => api.get("/projects").then((r) => setProjects(r.data)).catch((e) => toast.error(errMsg(e)));
  useEffect(() => { load(); }, [api]); // eslint-disable-line

  const create = async (name) => {
    try { const r = await api.post("/projects", { name }); navigate(`/p/${r.data.id}`); } catch (e) { toast.error(errMsg(e)); }
  };
  const rename = async (name) => {
    try { await api.patch(`/projects/${renaming.id}`, { name }); setRenaming(null); load(); } catch (e) { toast.error(errMsg(e)); }
  };
  const remove = async () => {
    try { await api.delete(`/projects/${deleting.id}`); setDeleting(null); load(); toast.success("Projeto excluído"); } catch (e) { toast.error(errMsg(e)); }
  };

  return (
    <div className="min-h-screen flex flex-col">
      <AppHeader />
      <main className="flex-1 px-6 lg:px-12 py-10 max-w-7xl w-full">
        {me?.blocked && <div className="mb-6 rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm" data-testid="blocked-banner">Sua conta está bloqueada. Fale com o administrador.</div>}
        <div className="flex flex-wrap items-end gap-4 mb-10">
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-primary mb-3">Seus projetos</p>
            <h1 className="font-display text-4xl sm:text-5xl font-extrabold tracking-tight">O que vamos construir?</h1>
          </div>
          <div className="ml-auto flex gap-2">
            <Button variant="secondary" onClick={() => setImporting(true)} data-testid="import-github-btn"><Github className="h-4 w-4 mr-2" />Importar do GitHub</Button>
            <Button onClick={() => setCreating(true)} data-testid="new-project-button"><Plus className="h-4 w-4 mr-2" />Novo projeto</Button>
          </div>
        </div>
        {!me?.platform_key_available && !me?.has_openrouter_key && me && (
          <div className="mb-6 rounded-lg border border-primary/40 bg-primary/5 p-4 text-sm" data-testid="no-key-banner">
            A plataforma ainda não tem chave OpenRouter. <Link className="text-primary underline" to="/settings">Adicione a sua em Configurações</Link> para usar a IA.
          </div>
        )}
        {projects === null ? (
          <p className="text-muted-foreground text-sm">Carregando…</p>
        ) : projects.length === 0 ? (
          <button onClick={() => setCreating(true)} data-testid="empty-new-project" className="w-full rounded-xl border border-dashed p-16 text-center transition-colors duration-150 hover:border-primary/60">
            <Plus className="h-6 w-6 mx-auto text-primary mb-3" />
            <p className="font-semibold">Crie seu primeiro projeto</p>
            <p className="text-sm text-muted-foreground mt-1">Ou importe um repositório do GitHub para continuar de onde parou.</p>
          </button>
        ) : (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="projects-grid">
            {projects.map((p, i) => <ProjectCard key={p.id} p={p} i={i} onRename={setRenaming} onDelete={setDeleting} />)}
          </div>
        )}
      </main>
      <NameDialog open={creating} onOpenChange={setCreating} title="Novo projeto" onSubmit={create} testid="create-project" />
      <NameDialog open={!!renaming} onOpenChange={(o) => !o && setRenaming(null)} title="Renomear projeto" initial={renaming?.name} onSubmit={rename} testid="rename-project" />
      <ImportDialog open={importing} onOpenChange={setImporting} />
      <AlertDialog open={!!deleting} onOpenChange={(o) => !o && setDeleting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Excluir “{deleting?.name}”?</AlertDialogTitle>
            <AlertDialogDescription>Todos os arquivos, mensagens e versões deste projeto serão apagados. O repositório no GitHub não é afetado.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={remove} data-testid="confirm-delete-project" className="bg-destructive hover:bg-destructive/90">Excluir</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
