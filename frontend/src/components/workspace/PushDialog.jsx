import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Loader2, Github } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { errMsg, useMe } from "@/lib/api";

export default function PushDialog({ open, onOpenChange, api, project, onPushed }) {
  const { me } = useMe();
  const gh = project?.github;
  const [message, setMessage] = useState("");
  const [newRepo, setNewRepo] = useState(!gh);
  const [repoName, setRepoName] = useState("");
  const [priv, setPriv] = useState(true);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open || !project) return;
    setNewRepo(!project.github);
    setRepoName(project.name.toLowerCase().replace(/[^a-z0-9._-]+/g, "-"));
    api.get(`/projects/${project.id}/github/suggest-message`).then((r) => setMessage(r.data.message)).catch(() => setMessage("Atualização via Forja"));
  }, [open, project, api]);

  const push = async () => {
    setBusy(true);
    try {
      const r = await api.post(`/projects/${project.id}/github/push`, { message, new_repo_name: newRepo ? repoName : null, private: priv });
      toast.success(r.data.changed ? `${r.data.changed} arquivo(s) enviados para ${r.data.repo} (${r.data.branch})` : r.data.message || "Nada para enviar");
      onPushed(r.data); onOpenChange(false);
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" data-testid="push-github-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Github className="h-4 w-4" />Enviar para o GitHub</DialogTitle>
          <DialogDescription>{gh && !newRepo ? `Commit direto em ${gh.owner}/${gh.repo} · ${gh.branch}` : "Cria um repositório novo na sua conta."}</DialogDescription>
        </DialogHeader>
        {!me?.github_login ? (
          <p className="text-sm text-muted-foreground">Conecte o GitHub em <Link to="/settings" className="text-primary underline">Configurações</Link>.</p>
        ) : (
          <div className="space-y-4">
            {gh && (
              <label className="flex items-center gap-2 text-sm">
                <Switch checked={newRepo} onCheckedChange={setNewRepo} data-testid="push-new-repo-switch" />Criar repositório novo
              </label>
            )}
            {newRepo && (
              <div className="flex gap-3 items-center">
                <Input value={repoName} onChange={(e) => setRepoName(e.target.value)} placeholder="nome-do-repositorio" className="font-mono" data-testid="push-repo-name-input" />
                <label className="flex items-center gap-2 text-xs shrink-0"><Switch checked={priv} onCheckedChange={setPriv} data-testid="push-private-switch" />Privado</label>
              </div>
            )}
            <div>
              <p className="text-xs text-muted-foreground mb-1.5">Mensagem do commit</p>
              <Textarea rows={5} value={message} onChange={(e) => setMessage(e.target.value)} className="font-mono text-xs" data-testid="push-commit-message" />
            </div>
            <div className="flex justify-end">
              <Button onClick={push} disabled={busy || !message.trim() || (newRepo && !repoName.trim())} data-testid="push-confirm-btn">
                {busy && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}{busy ? "Enviando…" : "Enviar commit"}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
