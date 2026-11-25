import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

export default function DiffDialog({ change, onClose }) {
  const lines = (change?.diff || "").split("\n").filter((l) => !l.startsWith("---") && !l.startsWith("+++"));
  return (
    <Dialog open={!!change} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl" data-testid="diff-view-dialog">
        <DialogHeader>
          <DialogTitle className="font-mono text-sm flex items-center gap-3">
            {change?.path}
            <span className="text-[hsl(var(--diff-add))]">+{change?.added}</span>
            <span className="text-[hsl(var(--diff-del))]">−{change?.removed}</span>
          </DialogTitle>
        </DialogHeader>
        <pre className="max-h-[65vh] overflow-auto scroll-thin rounded-md border bg-[#09090c] text-[12px] leading-5">
          {lines.length === 0 && <div className="p-3 text-muted-foreground">Sem diferenças de texto.</div>}
          {lines.map((l, i) => {
            const cls = l.startsWith("+") ? "bg-[hsl(var(--diff-add)/0.12)] text-[hsl(142_71%_70%)]"
              : l.startsWith("-") ? "bg-[hsl(var(--diff-del)/0.12)] text-[hsl(0_84%_75%)]"
              : l.startsWith("@@") ? "text-primary/80 bg-primary/5" : "text-zinc-400";
            return <div key={i} className={`px-3 whitespace-pre ${cls}`}>{l || " "}</div>;
          })}
        </pre>
      </DialogContent>
    </Dialog>
  );
}
