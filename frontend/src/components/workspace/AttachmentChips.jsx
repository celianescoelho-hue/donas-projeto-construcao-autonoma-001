import { X, FileText, Image as ImageIcon, FileArchive, FileCode2, Loader2 } from "lucide-react";

export const ACCEPT = ".html,.htm,.css,.js,.jsx,.mjs,.ts,.tsx,.json,.md,.txt,.py,.xml,.csv,.yml,.yaml,.png,.jpg,.jpeg,.svg,.webp,.gif,.ico,.pdf,.zip";

const iconFor = (path = "") => {
  const ext = path.split(".").pop().toLowerCase();
  if (["png", "jpg", "jpeg", "webp", "gif", "svg", "ico"].includes(ext)) return ImageIcon;
  if (ext === "zip") return FileArchive;
  if (["html", "htm", "js", "jsx", "ts", "tsx", "py", "css", "json"].includes(ext)) return FileCode2;
  return FileText;
};

export const fmtSize = (n = 0) => (n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);

export default function AttachmentChips({ items, onRemove, testid = "attachment-chip" }) {
  if (!items?.length) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((a) => {
        const Icon = a.uploading ? Loader2 : iconFor(a.path || a.name);
        return (
          <span key={a.path || a.name} title={a.summary || a.path} data-testid={`${testid}-${a.path || a.name}`}
            className="anim-pop inline-flex max-w-[240px] items-center gap-1.5 rounded-md border bg-background/70 px-2 py-1 font-mono text-[11px]">
            <Icon className={`h-3.5 w-3.5 shrink-0 text-primary ${a.uploading ? "animate-spin" : ""}`} />
            <span className="truncate">{a.path || a.name}</span>
            <span className="text-muted-foreground shrink-0">{fmtSize(a.size)}</span>
            {onRemove && !a.uploading && (
              <button onClick={() => onRemove(a)} className="text-muted-foreground hover:text-foreground" data-testid={`${testid}-remove-${a.path || a.name}`}>
                <X className="h-3 w-3" />
              </button>
            )}
          </span>
        );
      })}
    </div>
  );
}
