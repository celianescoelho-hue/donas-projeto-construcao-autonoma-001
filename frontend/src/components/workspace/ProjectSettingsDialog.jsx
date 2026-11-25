import { useEffect, useState } from "react";
import { Settings2 } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PublicToggle, liveUrl } from "@/components/workspace/SharePopover";

export default function ProjectSettingsDialog({ open, onOpenChange, project, onPatch }) {
  const [name, setName] = useState("");
  useEffect(() => { if (open && project) setName(project.name); }, [open, project]);
  if (!project) return null;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" data-testid="project-settings-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Settings2 className="h-4 w-4 text-primary" />Configurações do projeto</DialogTitle>
          <DialogDescription>Nome e acesso público do Link Preview.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-xs text-muted-foreground">Nome</label>
            <div className="flex gap-2">
              <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} data-testid="project-settings-name" />
              <Button variant="secondary" disabled={!name.trim() || name.trim() === project.name} onClick={() => onPatch({ name: name.trim() })} data-testid="project-settings-save-name">Salvar</Button>
            </div>
          </div>
          <PublicToggle enabled={project.public_preview} onToggle={(v) => onPatch({ public_preview: v })} testid="project-settings-public-switch" />
          <p className="font-mono text-[11px] text-muted-foreground break-all" data-testid="project-settings-url">{liveUrl(project.id)}</p>
        </div>
        <DialogFooter><Button variant="ghost" onClick={() => onOpenChange(false)}>Fechar</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
