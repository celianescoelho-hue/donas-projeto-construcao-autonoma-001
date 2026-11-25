import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Hexagon, LogOut, Loader2 } from "lucide-react";
import { AuthBridge } from "@/lib/authContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { errMsg } from "@/lib/api";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const KEY = "donas_selfhost_token";

export function SelfUserButton() {
  return (
    <Button size="sm" variant="ghost" className="h-8" data-testid="selfhost-logout-btn"
      onClick={() => { localStorage.removeItem(KEY); window.location.href = "/"; }}>
      <LogOut className="h-4 w-4 md:mr-1.5" /><span className="hidden md:inline">Sair</span>
    </Button>
  );
}

function LoginScreen({ onLogin }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const r = await fetch(`${API}/auth/login`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim(), password }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "Falha no login");
      onLogin(d.token);
    } catch (err) { toast.error(err.message); } finally { setBusy(false); }
  };
  return (
    <div className="min-h-screen grid-lines flex items-center justify-center p-4 bg-background">
      <form onSubmit={submit} className="w-full max-w-sm rounded-2xl border bg-card/80 backdrop-blur p-8 space-y-5" data-testid="selfhost-login-form">
        <div className="flex items-center gap-2.5">
          <span className="h-9 w-9 rounded-lg bg-primary grid place-items-center"><Hexagon className="h-5 w-5 text-white" strokeWidth={2.5} /></span>
          <div className="leading-none">
            <span className="font-display text-lg font-extrabold block">Donas</span>
            <span className="font-mono text-[9px] uppercase tracking-[0.22em] text-[hsl(var(--gold))]">Build apps with ai</span>
          </div>
        </div>
        <div className="space-y-2">
          <Input type="email" required placeholder="E-mail do admin" value={email} onChange={(e) => setEmail(e.target.value)} data-testid="selfhost-email" autoFocus />
          <Input type="password" required placeholder="Senha" value={password} onChange={(e) => setPassword(e.target.value)} data-testid="selfhost-password" />
        </div>
        <Button type="submit" className="w-full rounded-full" disabled={busy} data-testid="selfhost-submit">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Entrar"}
        </Button>
        <p className="text-xs text-muted-foreground text-center">Acesso restrito ao administrador (ADMIN_EMAIL).</p>
      </form>
    </div>
  );
}

export default function SelfHostAuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem(KEY) || "");
  const [email, setEmail] = useState("");

  useEffect(() => {
    if (!token) return;
    const [, payload] = token.split(".");
    try {
      const claims = JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/")));
      if (claims.exp && claims.exp * 1000 < Date.now()) { localStorage.removeItem(KEY); setToken(""); return; }
      setEmail(claims.email || "");
    } catch { /* keep token, backend validates */ }
  }, [token]);

  useEffect(() => {
    const onUnauth = () => { localStorage.removeItem(KEY); setToken(""); };
    window.addEventListener("donas-unauthorized", onUnauth);
    return () => window.removeEventListener("donas-unauthorized", onUnauth);
  }, []);

  const value = useMemo(() => ({
    getToken: async () => token || null,
    signOut: () => { localStorage.removeItem(KEY); setToken(""); },
    email,
  }), [token, email]);

  if (!token) return <LoginScreen onLogin={(t) => { localStorage.setItem(KEY, t); setToken(t); }} />;
  return <AuthBridge.Provider value={value}>{children}</AuthBridge.Provider>;
}

export { errMsg };
