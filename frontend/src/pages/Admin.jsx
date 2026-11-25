import { useEffect, useMemo, useState } from "react";
import { Navigate } from "react-router-dom";
import { toast } from "sonner";
import { Users, FolderKanban, MessageSquare, DollarSign, Star, X, Search, Plus } from "lucide-react";
import AppHeader from "@/components/AppHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useApi, useMe, errMsg } from "@/lib/api";

const usd = (v) => `US$ ${Number(v || 0).toFixed(4)}`;

function Overview({ api }) {
  const [d, setD] = useState(null);
  useEffect(() => { api.get("/admin/overview").then((r) => setD(r.data)).catch((e) => toast.error(errMsg(e))); }, [api]);
  const cards = d ? [
    { icon: Users, label: "Usuários", value: d.users, id: "users" },
    { icon: FolderKanban, label: "Projetos", value: d.projects, id: "projects" },
    { icon: MessageSquare, label: "Mensagens", value: d.messages, id: "messages" },
    { icon: DollarSign, label: "Custo (sua chave)", value: usd(d.cost_platform), id: "cost-platform" },
    { icon: DollarSign, label: "Custo (chaves dos usuários)", value: usd(d.cost_user), id: "cost-user" },
    { icon: Star, label: "Tokens", value: Number(d.tokens).toLocaleString("pt-BR"), id: "tokens" },
  ] : [];
  return (
    <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {cards.map((c, i) => (
        <div key={c.id} className="rounded-xl border bg-card p-5 anim-rise" style={{ animationDelay: `${i * 50}ms` }} data-testid={`stat-${c.id}`}>
          <c.icon className="h-4 w-4 text-primary mb-4" />
          <p className="text-xs text-muted-foreground">{c.label}</p>
          <p className="font-display text-3xl font-bold mt-1">{c.value}</p>
        </div>
      ))}
    </div>
  );
}

function UsersTab({ api, meId }) {
  const [d, setD] = useState(null);
  const load = () => api.get("/users").then((r) => setD(r.data)).catch((e) => toast.error(errMsg(e)));
  useEffect(() => { load(); }, [api]); // eslint-disable-line
  const act = (fn) => async () => { try { await fn(); load(); } catch (e) { toast.error(errMsg(e)); } };
  if (!d) return <p className="text-sm text-muted-foreground">Carregando…</p>;
  return (
    <div className="rounded-xl border bg-card overflow-x-auto">
      <Table data-testid="users-table">
        <TableHeader><TableRow><TableHead>Usuário</TableHead><TableHead>Papel</TableHead><TableHead>Chave</TableHead><TableHead>Projetos</TableHead><TableHead>Gasto</TableHead><TableHead>Bloqueado</TableHead></TableRow></TableHeader>
        <TableBody>
          {d.users.map((u) => (
            <TableRow key={u.user_id} data-testid={`user-row-${u.user_id}`}>
              <TableCell><p className="font-medium">{u.name}</p><p className="text-xs text-muted-foreground">{u.email}</p></TableCell>
              <TableCell>
                <Select value={u.role} onValueChange={(role) => act(() => api.patch(`/users/${u.user_id}/role`, { role }))()}>
                  <SelectTrigger className="w-28 h-8" data-testid={`role-select-${u.user_id}`}><SelectValue /></SelectTrigger>
                  <SelectContent>{d.roles.map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}</SelectContent>
                </Select>
              </TableCell>
              <TableCell className="text-xs">{u.own_key ? <span className="text-primary">própria</span> : "plataforma"}</TableCell>
              <TableCell className="font-mono text-xs">{u.projects}</TableCell>
              <TableCell className="font-mono text-xs">{usd(u.cost)}</TableCell>
              <TableCell>
                <Switch checked={u.blocked} disabled={u.user_id === meId} data-testid={`block-switch-${u.user_id}`}
                  onCheckedChange={(blocked) => act(() => api.patch(`/admin/users/${u.user_id}/block`, { blocked }))()} />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function ModelsTab({ api }) {
  const [s, setS] = useState(null);
  const [all, setAll] = useState(null);
  const [q, setQ] = useState("");
  useEffect(() => {
    api.get("/admin/settings").then((r) => setS(r.data)).catch((e) => toast.error(errMsg(e)));
    api.get("/admin/openrouter-models").then((r) => setAll(r.data)).catch(() => setAll([]));
  }, [api]);
  const save = async (upd) => { try { const r = await api.put("/admin/settings", upd); setS(r.data); toast.success("Modelos atualizados"); } catch (e) { toast.error(errMsg(e)); } };
  const enabledIds = useMemo(() => new Set((s?.enabled_models || []).map((m) => m.id)), [s]);
  const results = useMemo(() => (all || []).filter((m) => !enabledIds.has(m.id) && (m.id + m.name).toLowerCase().includes(q.toLowerCase())).slice(0, 40), [all, q, enabledIds]);
  if (!s) return <p className="text-sm text-muted-foreground">Carregando…</p>;
  return (
    <div className="grid lg:grid-cols-2 gap-6">
      <section className="rounded-xl border bg-card p-5">
        <h3 className="font-semibold mb-1">Modelos liberados</h3>
        <p className="text-xs text-muted-foreground mb-4">A estrela marca o padrão para novos projetos.</p>
        <div className="space-y-2" data-testid="enabled-models">
          {s.enabled_models.map((m) => (
            <div key={m.id} className="flex items-center gap-2 rounded-md border px-3 py-2" data-testid={`enabled-model-${m.id}`}>
              <button onClick={() => save({ default_model: m.id })} data-testid={`default-model-${m.id}`}>
                <Star className={`h-4 w-4 ${s.default_model === m.id ? "fill-primary text-primary" : "text-muted-foreground"}`} />
              </button>
              <div className="min-w-0 flex-1"><p className="text-sm truncate">{m.name}</p><p className="text-xs font-mono text-muted-foreground truncate">{m.id}</p></div>
              <Button size="icon" variant="ghost" className="h-7 w-7" disabled={s.enabled_models.length === 1}
                onClick={() => save({ enabled_models: s.enabled_models.filter((x) => x.id !== m.id) })} data-testid={`remove-model-${m.id}`}><X className="h-3.5 w-3.5" /></Button>
            </div>
          ))}
        </div>
      </section>
      <section className="rounded-xl border bg-card p-5">
        <h3 className="font-semibold mb-1">Liberar modelo da OpenRouter</h3>
        <p className="text-xs text-muted-foreground mb-4">Só aparecem modelos que suportam ferramentas.</p>
        <div className="relative mb-3">
          <Search className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input className="pl-9" placeholder="Buscar (ex: claude, gpt, deepseek)" value={q} onChange={(e) => setQ(e.target.value)} data-testid="model-search-input" />
        </div>
        <div className="max-h-96 overflow-y-auto scroll-thin divide-y rounded-md border">
          {all === null ? <p className="p-3 text-sm text-muted-foreground">Carregando…</p> : results.map((m) => (
            <div key={m.id} className="flex items-center gap-2 px-3 py-2">
              <div className="min-w-0 flex-1"><p className="text-sm truncate">{m.name}</p>
                <p className="text-xs font-mono text-muted-foreground truncate">{m.id} · ${(Number(m.prompt_price || 0) * 1e6).toFixed(2)}/${(Number(m.completion_price || 0) * 1e6).toFixed(2)} por 1M</p></div>
              <Button size="sm" variant="secondary" onClick={() => save({ enabled_models: [...s.enabled_models, { id: m.id, name: m.name }] })} data-testid={`add-model-${m.id}`}><Plus className="h-3.5 w-3.5" /></Button>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function LimitTab({ api }) {
  const [v, setV] = useState("");
  const [s, setS] = useState(null);
  useEffect(() => { api.get("/admin/settings").then((r) => { setS(r.data); setV(String(r.data.daily_limit_usd)); }); }, [api]);
  const save = async () => { try { const r = await api.put("/admin/settings", { daily_limit_usd: Number(v) }); setS(r.data); toast.success("Limite salvo"); } catch (e) { toast.error(errMsg(e)); } };
  return (
    <section className="rounded-xl border bg-card p-6 max-w-lg">
      <h3 className="font-semibold">Limite diário por usuário</h3>
      <p className="text-sm text-muted-foreground mt-1 mb-4">Vale só para quem usa a sua chave. Quem tem chave própria não tem limite.</p>
      <div className="flex gap-2 items-center">
        <span className="text-sm text-muted-foreground">US$</span>
        <Input type="number" min="0" step="0.5" value={v} onChange={(e) => setV(e.target.value)} className="w-32 font-mono" data-testid="daily-limit-input" />
        <Button onClick={save} data-testid="daily-limit-save">Salvar</Button>
      </div>
      {s && !s.platform_key_available && <p className="text-xs text-primary mt-4">A chave OpenRouter da plataforma ainda não foi configurada.</p>}
    </section>
  );
}

function UsageTab({ api }) {
  const [rows, setRows] = useState(null);
  useEffect(() => { api.get("/admin/usage").then((r) => setRows(r.data)).catch((e) => toast.error(errMsg(e))); }, [api]);
  if (!rows) return <p className="text-sm text-muted-foreground">Carregando…</p>;
  return (
    <div className="rounded-xl border bg-card overflow-x-auto">
      <Table data-testid="usage-table">
        <TableHeader><TableRow><TableHead>Quando</TableHead><TableHead>Usuário</TableHead><TableHead>Modelo</TableHead><TableHead>Tokens</TableHead><TableHead>Custo</TableHead><TableHead>Chave</TableHead></TableRow></TableHeader>
        <TableBody>
          {rows.length === 0 && <TableRow><TableCell colSpan={6} className="text-muted-foreground text-sm">Nenhuma chamada ainda.</TableCell></TableRow>}
          {rows.map((r) => (
            <TableRow key={r.id}>
              <TableCell className="text-xs">{new Date(r.created_at).toLocaleString("pt-BR")}</TableCell>
              <TableCell className="text-xs">{r.email}</TableCell>
              <TableCell className="text-xs font-mono">{r.model}</TableCell>
              <TableCell className="text-xs font-mono">{r.prompt_tokens}/{r.completion_tokens}</TableCell>
              <TableCell className="text-xs font-mono">{usd(r.cost)}</TableCell>
              <TableCell className="text-xs">{r.key_source === "user" ? "usuário" : "plataforma"}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

export default function Admin() {
  const api = useApi();
  const { me } = useMe();
  if (me && me.role !== "admin") return <Navigate to="/" replace />;
  if (!me) return null;
  return (
    <div className="min-h-screen flex flex-col">
      <AppHeader />
      <main className="px-6 lg:px-12 py-10 max-w-7xl w-full">
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-primary mb-3">Painel admin</p>
        <h1 className="font-display text-4xl font-extrabold tracking-tight mb-8">Controle do Donas</h1>
        <Tabs defaultValue="overview">
          <TabsList className="mb-6">
            <TabsTrigger value="overview" data-testid="admin-tab-overview">Visão geral</TabsTrigger>
            <TabsTrigger value="users" data-testid="admin-tab-users">Usuários</TabsTrigger>
            <TabsTrigger value="models" data-testid="admin-tab-models">Modelos</TabsTrigger>
            <TabsTrigger value="limit" data-testid="admin-tab-limit">Limite</TabsTrigger>
            <TabsTrigger value="usage" data-testid="admin-tab-usage">Histórico de uso</TabsTrigger>
          </TabsList>
          <TabsContent value="overview"><Overview api={api} /></TabsContent>
          <TabsContent value="users"><UsersTab api={api} meId={me.user_id} /></TabsContent>
          <TabsContent value="models"><ModelsTab api={api} /></TabsContent>
          <TabsContent value="limit"><LimitTab api={api} /></TabsContent>
          <TabsContent value="usage"><UsageTab api={api} /></TabsContent>
        </Tabs>
      </main>
    </div>
  );
}
