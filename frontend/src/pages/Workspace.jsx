import { ACCEPT } from "@/components/workspace/AttachmentChips";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { toast } from "sonner";
import { History, Download, Github, KeyRound } from "lucide-react";
import AppHeader from "@/components/AppHeader";
import ChatPanel from "@/components/workspace/ChatPanel";
import FileTree from "@/components/workspace/FileTree";
import CodeEditor from "@/components/workspace/CodeEditor";
import PreviewPanel from "@/components/workspace/PreviewPanel";
import DiffDialog from "@/components/workspace/DiffDialog";
import VersionsSheet from "@/components/workspace/VersionsSheet";
import PushDialog from "@/components/workspace/PushDialog";
import TerminalPanel from "@/components/workspace/TerminalPanel";
import ImportDialog from "@/components/ImportDialog";
import EnvDialog from "@/components/workspace/EnvDialog";
import { Button } from "@/components/ui/button";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { useApi, errMsg, streamChat } from "@/lib/api";
import { buildPreview, emptyHtml } from "@/lib/preview";

function useAssetUrls(api, pid, files) {
  const cache = useRef({});
  const [urls, setUrls] = useState({});
  useEffect(() => {
    const todo = files.filter((f) => f.kind === "binary" && cache.current[f.path]?.size !== f.size);
    if (!todo.length) return;
    Promise.all(todo.map(async (f) => {
      try {
        const r = await api.get(`/projects/${pid}/asset`, { params: { path: f.path }, responseType: "blob" });
        const url = await new Promise((ok, fail) => { const fr = new FileReader(); fr.onload = () => ok(fr.result); fr.onerror = fail; fr.readAsDataURL(r.data); });
        cache.current[f.path] = { size: f.size, url };
      } catch {}
    })).then(() => setUrls(Object.fromEntries(Object.entries(cache.current).map(([k, v]) => [k, v.url]))));
  }, [files, api, pid]);
  return urls;
}

function usePreview(files, assetUrls, env) {
  const [html, setHtml] = useState(emptyHtml("Carregando prévia…"));
  const [building, setBuilding] = useState(false);
  const prev = useRef([]);
  useEffect(() => {
    setBuilding(true);
    const t = setTimeout(() => {
      try {
        const { html, urls } = buildPreview(files, { ...assetUrls }, env);
        prev.current.forEach((u) => URL.revokeObjectURL(u));
        prev.current = urls;
        setHtml(html);
      } catch (e) { setHtml(emptyHtml(`Erro ao montar a prévia: ${e.message}`)); }
      setBuilding(false);
    }, 700);
    return () => clearTimeout(t);
  }, [files, assetUrls, env]);
  return { html, building };
}

export default function Workspace() {
  const { id } = useParams();
  const api = useApi();
  const [project, setProject] = useState(null);
  const [files, setFiles] = useState([]);
  const [messages, setMessages] = useState([]);
  const [models, setModels] = useState([]);
  const [model, setModel] = useState("");
  const [selected, setSelected] = useState(null);
  const [dir, setDir] = useState("");
  const [live, setLive] = useState(null);
  const [diff, setDiff] = useState(null);
  const [versionsOpen, setVersionsOpen] = useState(false);
  const [pushOpen, setPushOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [envOpen, setEnvOpen] = useState(false);
  const [env, setEnv] = useState({});
  const [inject, setInject] = useState(null);
  const [fresh, setFresh] = useState(new Set());
  const [logs, setLogs] = useState([]);
  const logSeq = useRef(0);
  const log = useCallback((level, msg) => setLogs((l) => [...l.slice(-499), { id: ++logSeq.current, level, msg, time: new Date().toLocaleTimeString("pt-BR") }]), []);
  const uploadRef = useRef(null);
  const reloadTimer = useRef(null);

  const loadFiles = useCallback(async () => {
    try {
      const r = await api.get(`/projects/${id}`);
      setProject(r.data.project);
      setFiles(r.data.files);
      return r.data;
    } catch (e) { toast.error(errMsg(e)); }
  }, [api, id]);

  useEffect(() => {
    api.get(`/projects/${id}/env`).then((r) => setEnv(Object.fromEntries(r.data.vars.map((v) => [v.key, v.value])))).catch(() => {});
  }, [api, id]);

  useEffect(() => {
    Promise.all([loadFiles(), api.get(`/projects/${id}/messages`), api.get("/models")]).then(([d, m, md]) => {
      setMessages(m.data);
      setModels(md.data.models);
      const pm = d?.project?.model;
      setModel(md.data.models.some((x) => x.id === pm) ? pm : md.data.default_model);
      const first = d?.files.find((f) => /App\.(jsx?|tsx)$/.test(f.path)) || d?.files[0];
      if (first) setSelected(first.path);
    }).catch((e) => toast.error(errMsg(e)));
  }, [api, id, loadFiles]);

  useEffect(() => {
    const h = (e) => { const d = e.origin === "null" && e.data?.donasLog; if (d) log(d.level, `[prévia] ${d.msg}`); };
    window.addEventListener("message", h);
    return () => window.removeEventListener("message", h);
  }, [log]);

  const throttledReload = () => {
    if (reloadTimer.current) return;
    reloadTimer.current = setTimeout(() => { reloadTimer.current = null; loadFiles(); }, 1200);
  };

  const changeModel = async (m) => {
    setModel(m);
    try { await api.patch(`/projects/${id}`, { model: m }); } catch (e) { toast.error(errMsg(e)); }
  };

  const send = async (prompt, attachments = []) => {
    setMessages((ms) => [...ms, { id: `tmp-${Date.now()}`, role: "user", content: prompt, attachments }]);
    setLive({ text: "", tools: [], changes: [], warnings: [], model });
    let gotDone = false;
    log("system", `$ donas run --model ${model}`);
    try {
      const token = await api.token();
      await streamChat(token, id, { prompt, model, attachments: attachments.map((a) => a.path) }, (ev) => {
        if (ev.type === "token") setLive((l) => l && { ...l, text: l.text + ev.text });
        else if (ev.type === "start") log("info", `conectado à OpenRouter · chave ${ev.key_source === "user" ? "própria" : "da plataforma"}`);
        else if (ev.type === "tool") { setLive((l) => l && { ...l, tools: [...l.tools, ev] }); log("agent", `${ev.name} ${ev.path || ""}`); }
        else if (ev.type === "tool_error") { setLive((l) => l && { ...l, tools: [...l.tools, { name: ev.name, error: ev.message }] }); log("warn", `${ev.name}: ${ev.message}`); }
        else if (ev.type === "error") { setLive((l) => l && { ...l, error: ev.message }); log("error", ev.message); }
        else if (ev.type === "warning") { setLive((l) => l && { ...l, warnings: [...l.warnings, ev.message] }); log("warn", ev.message); }
        else if (ev.type === "change") {
          setLive((l) => l && { ...l, changes: [...l.changes, ev] });
          log("change", `${ev.op} ${ev.path}  +${ev.added} −${ev.removed}`);
          setFresh((s) => new Set([...s, ev.path]));
          throttledReload();
        } else if (ev.type === "done") {
          gotDone = true;
          setMessages((ms) => [...ms, ev.message]);
          log("system", `concluído · ${ev.message.changes?.length || 0} arquivo(s) · ${ev.message.tokens || 0} tokens · US$ ${(ev.message.cost || 0).toFixed(4)}`);
          setLive(null);
          loadFiles();
        }
      });
      if (!gotDone) {
        const msg = "A conexão com a IA caiu antes do fim da resposta. O que já foi feito ficou salvo; atualize ou envie 'continue'.";
        log("error", msg);
        const r = await api.get(`/projects/${id}/messages`).catch(() => null);
        const last = r?.data?.[r.data.length - 1];
        if (last?.role === "assistant") setMessages(r.data);
        else setMessages((ms) => [...ms, { id: `err-${Date.now()}`, role: "assistant", content: "", error: msg }]);
        loadFiles();
      }
    } catch (e) {
      toast.error(e.message);
      log("error", e.message);
      setMessages((ms) => [...ms, { id: `err-${Date.now()}`, role: "assistant", content: "", error: e.message }]);
    } finally {
      setLive(null);
      setTimeout(() => setFresh(new Set()), 2000);
    }
  };

  const upload = async (fileList, target = dir, quiet = false) => {
    const form = new FormData();
    const list = Array.from(fileList).filter((f) => {
      if (f.size <= 10 * 1024 * 1024) return true;
      toast.error(`${f.name}: maior que 10 MB`);
      return false;
    });
    if (!list.length) return [];
    list.forEach((f) => form.append("files", f));
    form.append("directory", target);
    const t = toast.loading("Enviando arquivos…");
    try {
      const r = await api.post(`/projects/${id}/upload`, form);
      toast.success(`${r.data.saved.length} arquivo(s) enviados para /${target}`, { id: t });
      r.data.saved.forEach((f) => log("change", `upload ${f.path} (${f.summary || f.kind})`));
      r.data.errors.forEach((e) => toast.error(e));
      setFresh(new Set(r.data.saved.map((s) => s.path)));
      await loadFiles();
      if (r.data.saved[0] && !quiet) setSelected(r.data.saved[0].path);
      return r.data.saved;
    } catch (e) { toast.error(errMsg(e), { id: t }); return []; }
  };

  const saveFile = async (path, content) => {
    try { await api.put(`/projects/${id}/files`, { path, content }); toast.success("Arquivo salvo"); log("change", `salvo ${path}`); await loadFiles(); } catch (e) { toast.error(errMsg(e)); }
  };

  const deleteFile = async (path) => {
    if (!window.confirm(`Apagar ${path}?`)) return;
    try { await api.delete(`/projects/${id}/files`, { params: { path } }); if (selected === path) setSelected(null); await loadFiles(); } catch (e) { toast.error(errMsg(e)); }
  };

  const newFile = async () => {
    const name = window.prompt("Caminho do novo arquivo", dir ? `${dir}/novo.js` : "novo.js");
    if (!name) return;
    await saveFile(name, "");
    setSelected(name.replace(/^\/+/, ""));
  };

  const downloadZip = async () => {
    try {
      const r = await api.get(`/projects/${id}/zip`, { responseType: "blob" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(r.data);
      a.download = `${project?.name || "projeto"}.zip`;
      a.click();
    } catch (e) { toast.error(errMsg(e)); }
  };

  const fixErrors = (errs) => {
    if (live) return toast.error("A IA já está trabalhando.");
    log("info", `auto-fix · enviando ${errs.length} erro(s) da prévia para a IA`);
    send(`A prévia ao vivo mostrou ${errs.length} erro(s). Encontre a causa (use search_in_files e read_file por trechos) e corrija com edições mínimas:\n\`\`\`\n${errs.join("\n")}\n\`\`\``);
  };

  const onPick = useCallback((el) => {
    const where = el.source ? `arquivo ${el.source.replace(/:(\d+)$/, " (linha $1)")}` : "HTML estático";
    const text = `[Elemento selecionado na prévia]\n- ${where}\n- seletor: ${el.selector}\n- tag: \`${el.html}\`${el.text ? `\n- texto: “${el.text}”` : ""}`;
    setInject({ id: Date.now(), text });
    log("info", `inspect · ${el.selector}${el.source ? ` → ${el.source}` : ""}`);
    toast.success("Referência do elemento enviada para o chat");
  }, [log]);

  const undoVersion = async (v) => {
    if (live) return;
    if (!window.confirm(`Voltar os arquivos para antes da versão ${v.number}? (também desfaz as versões mais novas)`)) return;
    try {
      const r = await api.post(`/projects/${id}/versions/${v.id}/restore`, null, { params: { mode: "before" } });
      toast.success(`Desfeito: voltou para antes da v${v.number} (${r.data.changed} arquivos)`);
      log("change", `rollback · antes da v${v.number} · ${r.data.changed} arquivo(s)`);
      loadFiles();
    } catch (e) { toast.error(errMsg(e)); }
  };

  const assetUrls = useAssetUrls(api, id, files);
  const { html, building } = usePreview(files, assetUrls, env);
  const selectedFile = useMemo(() => files.find((f) => f.path === selected), [files, selected]);

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      <AppHeader>
        <div className="flex items-center gap-3 min-w-0">
          <span className="text-muted-foreground">/</span>
          <span className="font-semibold truncate" data-testid="workspace-project-name">{project?.name}</span>
          {project?.github && <span className="hidden md:inline font-mono text-[11px] text-muted-foreground truncate">{project.github.owner}/{project.github.repo}:{project.github.branch}</span>}
        </div>
        <div className="flex gap-1 ml-4">
          <Button size="sm" variant="ghost" onClick={() => setVersionsOpen(true)} data-testid="open-versions-btn"><History className="h-4 w-4 md:mr-1.5" /><span className="hidden md:inline">Versões</span></Button>
          <Button size="sm" variant="ghost" onClick={() => setEnvOpen(true)} data-testid="open-env-btn"><KeyRound className="h-4 w-4 md:mr-1.5" /><span className="hidden md:inline">.env{Object.keys(env).length ? ` (${Object.keys(env).length})` : ""}</span></Button>
          <Button size="sm" variant="ghost" onClick={downloadZip} data-testid="download-zip-btn"><Download className="h-4 w-4 md:mr-1.5" /><span className="hidden md:inline">.zip</span></Button>
          <Button size="sm" variant="secondary" onClick={() => setPushOpen(true)} data-testid="open-push-btn"><Github className="h-4 w-4 md:mr-1.5" /><span className="hidden md:inline">Enviar ao GitHub</span></Button>
        </div>
      </AppHeader>
      <ResizablePanelGroup direction="horizontal" className="flex-1 min-h-0">
        <ResizablePanel defaultSize={27} minSize={20}>
          <ChatPanel messages={messages} live={live} busy={!!live} onSend={send} models={models} model={model} onModel={changeModel}
            onOpenDiff={setDiff} onAttach={(fl) => upload(fl, "uploads", true)} showImportHint={!!project && files.length === 0} onImportGithub={() => setImportOpen(true)}
            inject={inject} onUndo={undoVersion} />
        </ResizablePanel>
        <ResizableHandle />
        <ResizablePanel defaultSize={38} minSize={22}>
          <ResizablePanelGroup direction="horizontal">
            <ResizablePanel defaultSize={34} minSize={20}>
              <FileTree files={files} selected={selected} onSelect={setSelected} onDelete={deleteFile} onDropFiles={upload}
                onNewFile={newFile} onUploadClick={() => uploadRef.current?.click()} dir={dir} setDir={setDir} fresh={fresh} onImportGithub={() => setImportOpen(true)} />
            </ResizablePanel>
            <ResizableHandle />
            <ResizablePanel defaultSize={66} minSize={30}>
              <CodeEditor file={selectedFile} assetUrl={selectedFile && assetUrls[selectedFile.path]} onSave={saveFile} />
            </ResizablePanel>
          </ResizablePanelGroup>
        </ResizablePanel>
        <ResizableHandle />
        <ResizablePanel defaultSize={35} minSize={20}>
          <ResizablePanelGroup direction="vertical">
            <ResizablePanel defaultSize={72} minSize={30}><PreviewPanel html={html} building={building} busy={!!live} onFixErrors={fixErrors} onPick={onPick} /></ResizablePanel>
            <ResizableHandle />
            <ResizablePanel defaultSize={28} minSize={8}><TerminalPanel logs={logs} onClear={() => setLogs([])} /></ResizablePanel>
          </ResizablePanelGroup>
        </ResizablePanel>
      </ResizablePanelGroup>
      <input ref={uploadRef} type="file" multiple hidden data-testid="upload-input"
        accept={ACCEPT}
        onChange={(e) => { if (e.target.files.length) upload(e.target.files); e.target.value = ""; }} />
      <ImportDialog open={importOpen} onOpenChange={setImportOpen} projectId={id} onImported={async (r) => {
        log("info", `git import · ${r.imported} arquivo(s)${r.skipped_count ? ` · ${r.skipped_count} ignorados` : ""}`);
        const [d, m] = await Promise.all([loadFiles(), api.get(`/projects/${id}/messages`)]);
        setMessages(m.data);
        const first = d?.files.find((f) => /App\.(jsx?|tsx)$/.test(f.path)) || d?.files[0];
        if (first) setSelected(first.path);
      }} />
      <EnvDialog open={envOpen} onOpenChange={setEnvOpen} api={api} projectId={id}
        onSaved={(vars) => { setEnv(Object.fromEntries(vars.map((v) => [v.key, v.value]))); log("info", `.env · ${vars.length} variável(is) injetadas na prévia`); }} />
      <DiffDialog change={diff} onClose={() => setDiff(null)} />
      <VersionsSheet open={versionsOpen} onOpenChange={setVersionsOpen} api={api} projectId={id} onRestored={loadFiles} />
      <PushDialog open={pushOpen} onOpenChange={setPushOpen} api={api} project={project} onPushed={(r) => { log("info", `git push ${r.repo}:${r.branch} · ${r.changed} arquivo(s)`); loadFiles(); }} />
    </div>
  );
}
