import { useState } from "react";
import { toast } from "sonner";
import { KeyRound, Github, Check, Loader2 } from "lucide-react";
import AppHeader from "@/components/AppHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useApi, useMe, errMsg } from "@/lib/api";

function SecretCard({ icon: Icon, title, desc, connected, connectedText, placeholder, onSave, onRemove, testid, help }) {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const save = async () => { setBusy(true); try { await onSave(value.trim()); setValue(""); } finally { setBusy(false); } };
  return (
    <section className="rounded-xl border bg-card p-6 anim-rise" data-testid={`${testid}-card`}>
      <div className="flex items-start gap-4">
        <div className="h-10 w-10 rounded-lg bg-secondary grid place-items-center"><Icon className="h-5 w-5 text-primary" /></div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3">
            <h2 className="font-semibold">{title}</h2>
            {connected && <span className="text-xs font-mono rounded-full bg-[hsl(var(--diff-add)/0.15)] text-[hsl(var(--diff-add))] px-2 py-0.5 flex items-center gap-1" data-testid={`${testid}-status`}><Check className="h-3 w-3" />{connectedText}</span>}
          </div>
          <p className="text-sm text-muted-foreground mt-1 leading-relaxed">{desc}</p>
          {help}
          <div className="mt-4 flex gap-2">
            <Input type="password" autoComplete="off" placeholder={placeholder} value={value} onChange={(e) => setValue(e.target.value)} data-testid={`${testid}-input`} className="font-mono" />
            <Button onClick={save} disabled={busy || value.trim().length < 10} data-testid={`${testid}-save`}>{busy && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}{connected ? "Trocar" : "Salvar"}</Button>
            {connected && <Button variant="ghost" className="hover:text-destructive" onClick={onRemove} data-testid={`${testid}-remove`}>Remover</Button>}
          </div>
        </div>
      </div>
    </section>
  );
}

export default function Settings() {
  const api = useApi();
  const { me, reload } = useMe();
  const wrap = (fn, ok) => async (...a) => { try { await fn(...a); toast.success(ok); reload(); } catch (e) { toast.error(errMsg(e)); } };

  return (
    <div className="min-h-screen flex flex-col">
      <AppHeader />
      <main className="px-6 lg:px-12 py-10 max-w-3xl w-full space-y-6">
        <div className="mb-4">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-primary mb-3">Configurações</p>
          <h1 className="font-display text-4xl font-extrabold tracking-tight">Chaves e conexões</h1>
          <p className="text-sm text-muted-foreground mt-3">As chaves ficam guardadas criptografadas e nunca são mostradas de volta.</p>
        </div>
        <SecretCard icon={KeyRound} testid="openrouter-key" title="Sua chave OpenRouter" connected={me?.has_openrouter_key} connectedText="em uso"
          desc={me?.has_openrouter_key ? "O uso sai da sua conta OpenRouter e não há limite diário da plataforma." :
            `Sem chave própria você usa a chave da plataforma, com limite de US$ ${Number(me?.daily_limit_usd ?? 2).toFixed(2)} por dia.`}
          placeholder="sk-or-v1-…"
          help={<p className="text-xs text-muted-foreground mt-2">Crie em <a className="text-primary underline" href="https://openrouter.ai/keys" target="_blank" rel="noreferrer">openrouter.ai/keys</a>.</p>}
          onSave={wrap((key) => api.put("/settings/openrouter-key", { key }), "Chave OpenRouter salva")}
          onRemove={wrap(() => api.delete("/settings/openrouter-key"), "Chave removida")} />
        <SecretCard icon={Github} testid="github-token" title="GitHub" connected={!!me?.github_login} connectedText={me?.github_login ? `@${me.github_login}` : ""}
          desc="Conecte com um token de acesso pessoal para importar repositórios (inclusive privados) e enviar commits."
          placeholder="ghp_… ou github_pat_…"
          help={<p className="text-xs text-muted-foreground mt-2">Crie em <a className="text-primary underline" href="https://github.com/settings/tokens/new?scopes=repo&description=Forja" target="_blank" rel="noreferrer">github.com/settings/tokens</a> com a permissão <span className="font-mono">repo</span>.</p>}
          onSave={wrap((token) => api.put("/settings/github", { token }), "GitHub conectado")}
          onRemove={wrap(() => api.delete("/settings/github"), "GitHub desconectado")} />
      </main>
    </div>
  );
}
