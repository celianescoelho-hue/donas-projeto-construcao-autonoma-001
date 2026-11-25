import { useMemo, useState } from "react";
import { ChevronRight, Folder, FolderOpen, FileText, Image as ImageIcon, Trash2, FilePlus, Upload, Github } from "lucide-react";
import { Button } from "@/components/ui/button";

function buildTree(files) {
  const root = { name: "", path: "", dirs: {}, files: [] };
  for (const f of files) {
    const parts = f.path.split("/");
    let node = root;
    parts.slice(0, -1).forEach((part, i) => {
      const p = parts.slice(0, i + 1).join("/");
      node = node.dirs[part] || (node.dirs[part] = { name: part, path: p, dirs: {}, files: [] });
    });
    node.files.push(f);
  }
  return root;
}

function Dir({ node, depth, ctx }) {
  const open = ctx.open.has(node.path);
  const [over, setOver] = useState(false);
  const drop = (e) => { e.preventDefault(); e.stopPropagation(); setOver(false); if (e.dataTransfer.files.length) ctx.onDropFiles(e.dataTransfer.files, node.path); };
  return (
    <div onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); setOver(true); }} onDragLeave={() => setOver(false)} onDrop={drop}
      className={over ? "bg-primary/10 outline outline-1 outline-primary/50 rounded" : ""}>
      <button onClick={() => { ctx.toggle(node.path); ctx.setDir(node.path); }} data-testid={`tree-dir-${node.path}`}
        className={`w-full flex items-center gap-1.5 py-1 pr-2 text-[13px] rounded transition-colors duration-150 hover:bg-secondary ${ctx.dir === node.path ? "text-foreground" : "text-muted-foreground"}`}
        style={{ paddingLeft: depth * 12 + 6 }}>
        <ChevronRight className={`h-3 w-3 transition-transform duration-150 ${open ? "rotate-90" : ""}`} />
        {open ? <FolderOpen className="h-3.5 w-3.5 text-primary/80" /> : <Folder className="h-3.5 w-3.5 text-primary/80" />}
        <span className="truncate">{node.name}</span>
      </button>
      {open && <Children node={node} depth={depth + 1} ctx={ctx} />}
    </div>
  );
}

function Children({ node, depth, ctx }) {
  const dirs = Object.values(node.dirs).sort((a, b) => a.name.localeCompare(b.name));
  const files = [...node.files].sort((a, b) => a.path.localeCompare(b.path));
  return (
    <>
      {dirs.map((d) => <Dir key={d.path} node={d} depth={depth} ctx={ctx} />)}
      {files.map((f, i) => {
        const name = f.path.split("/").pop();
        const active = ctx.selected === f.path;
        const Icon = f.kind === "binary" || name.endsWith(".svg") ? ImageIcon : FileText;
        return (
          <div key={f.path} className={`anim-rise group flex items-center rounded transition-colors duration-150 ${active ? "bg-primary/15 text-foreground" : "hover:bg-secondary text-muted-foreground"} ${ctx.fresh.has(f.path) ? "anim-flash" : ""}`}
            style={{ animationDelay: `${Math.min(i, 10) * 15}ms` }}>
            <button onClick={() => ctx.onSelect(f.path)} data-testid={`tree-file-${f.path}`} className="flex-1 min-w-0 flex items-center gap-1.5 py-1 text-[13px]" style={{ paddingLeft: depth * 12 + 20 }}>
              <Icon className={`h-3.5 w-3.5 shrink-0 ${active ? "text-primary" : ""}`} />
              <span className="truncate">{name}</span>
              {f.uploaded && <span className="text-[9px] font-mono text-primary/80 ml-1">enviado</span>}
            </button>
            <button onClick={() => ctx.onDelete(f.path)} data-testid={`delete-file-${f.path}`} className="opacity-0 group-hover:opacity-100 px-1.5 hover:text-destructive transition-opacity duration-150">
              <Trash2 className="h-3 w-3" />
            </button>
          </div>
        );
      })}
    </>
  );
}

export default function FileTree({ files, selected, onSelect, onDelete, onDropFiles, onNewFile, onUploadClick, dir, setDir, fresh, onImportGithub }) {
  const tree = useMemo(() => buildTree(files), [files]);
  const [open, setOpen] = useState(() => new Set(["frontend", "frontend/src", "backend", "src"]));
  const toggle = (p) => setOpen((s) => { const n = new Set(s); n.has(p) ? n.delete(p) : n.add(p); return n; });
  const ctx = { open, toggle, selected, onSelect, onDelete, onDropFiles, dir, setDir, fresh };
  return (
    <div className="h-full flex flex-col" data-testid="file-tree"
      onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); if (e.dataTransfer.files.length) onDropFiles(e.dataTransfer.files, ""); }}>
      <div className="h-9 shrink-0 flex items-center gap-1 px-2 border-b">
        <button onClick={() => setDir("")} className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground hover:text-foreground" data-testid="tree-root">Arquivos</button>
        <span className="text-[10px] font-mono text-muted-foreground/70 truncate">{files.length}</span>
        <Button size="icon" variant="ghost" className="ml-auto h-6 w-6" onClick={onNewFile} title="Novo arquivo" data-testid="new-file-btn"><FilePlus className="h-3.5 w-3.5" /></Button>
        <Button size="icon" variant="ghost" className="h-6 w-6" onClick={onUploadClick} title="Enviar arquivos" data-testid="tree-upload-btn"><Upload className="h-3.5 w-3.5" /></Button>
      </div>
      <div className="flex-1 overflow-auto scroll-thin p-1.5">
        {files.length === 0 ? (
          <div className="p-3 space-y-3" data-testid="tree-empty">
            <p className="text-xs text-muted-foreground">Vazio. Converse com a IA, arraste arquivos aqui ou traga um repositório.</p>
            <Button size="sm" variant="secondary" className="w-full h-8 text-xs" onClick={onImportGithub} data-testid="tree-import-github-btn"><Github className="h-3.5 w-3.5 mr-1.5" />Importar do GitHub</Button>
          </div>
        ) : <Children node={tree} depth={0} ctx={ctx} />}
      </div>
      <div className="shrink-0 border-t px-2 py-1 font-mono text-[10px] text-muted-foreground truncate" data-testid="upload-dir-label">upload → /{dir}</div>
    </div>
  );
}
