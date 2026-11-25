import { useState } from "react";
import { toast } from "sonner";
import { QRCodeSVG } from "qrcode.react";
import { Share2, Copy, ExternalLink, Globe, Lock } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export const liveUrl = (id) => `${window.location.origin}/p/${id}/live`;

export function PublicToggle({ enabled, onToggle, testid = "public-preview-switch" }) {
  const [busy, setBusy] = useState(false);
  return (
    <div className="flex items-center gap-3 rounded-lg border p-3">
      {enabled ? <Globe className="h-4 w-4 text-[hsl(var(--diff-add))]" /> : <Lock className="h-4 w-4 text-muted-foreground" />}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium">Acesso público ao link</p>
        <p className="text-xs text-muted-foreground">{enabled ? "Qualquer pessoa com o link usa o app (o back-end roda, mas o código dele não é exposto)." : "Desativado: o link mostra 'prévia indisponível'."}</p>
      </div>
      <Switch checked={!!enabled} disabled={busy} data-testid={testid}
        onCheckedChange={async (v) => { setBusy(true); try { await onToggle(v); } finally { setBusy(false); } }} />
    </div>
  );
}

export default function SharePopover({ project, onTogglePublic }) {
  if (!project) return null;
  const url = liveUrl(project.id);
  const on = !!project.public_preview;
  const copy = async () => {
    try { await navigator.clipboard.writeText(url); toast.success("Link copiado"); }
    catch { toast.error("Não foi possível copiar; selecione o link manualmente."); }
  };
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button size="sm" variant={on ? "secondary" : "ghost"} className="h-6 px-2 text-[11px] gap-1.5" data-testid="share-preview-btn" title="Abrir / Copiar Link Preview">
          <Share2 className="h-3.5 w-3.5" /><span className="hidden xl:inline">Link</span>
          {on && <span className="h-1.5 w-1.5 rounded-full bg-[hsl(var(--diff-add))]" />}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[340px] space-y-3" data-testid="share-popover">
        <div>
          <p className="font-semibold text-sm">Link Preview público</p>
          <p className="text-xs text-muted-foreground">Abre o site em tela cheia, sem o editor. Ótimo para testar no celular de verdade.</p>
        </div>
        <PublicToggle enabled={on} onToggle={onTogglePublic} />
        <div className="flex gap-1.5">
          <Input readOnly value={url} className="h-8 font-mono text-[11px]" onFocus={(e) => e.target.select()} data-testid="share-url-input" />
          <Button size="icon" variant="secondary" className="h-8 w-8 shrink-0" onClick={copy} data-testid="share-copy-btn"><Copy className="h-3.5 w-3.5" /></Button>
          <Button size="icon" className="h-8 w-8 shrink-0" disabled={!on} onClick={() => window.open(url, "_blank", "noopener")} data-testid="share-open-btn"><ExternalLink className="h-3.5 w-3.5" /></Button>
        </div>
        {on ? (
          <div className="flex items-center gap-3 rounded-lg bg-white p-3" data-testid="share-qr">
            <QRCodeSVG value={url} size={96} />
            <p className="text-xs text-zinc-700">Aponte a câmera do celular para abrir a prévia.</p>
          </div>
        ) : <p className="text-xs text-amber-300" data-testid="share-disabled-hint">Ative o acesso público para o link funcionar.</p>}
      </PopoverContent>
    </Popover>
  );
}
