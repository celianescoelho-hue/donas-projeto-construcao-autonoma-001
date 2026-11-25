import { Link } from "react-router-dom";
import { KeyRound, GitBranch, Scissors, Upload, ArrowRight, Terminal, Smartphone } from "lucide-react";
import { Brand } from "@/components/AppHeader";
import { Button } from "@/components/ui/button";

const HERO = "https://customer-assets-0z36b82j.emergentagent.net/job_or-ai-app--03yxw9is/artifacts/b91edda7da0142d4_maxresdefault.jpg";

const features = [
  { icon: KeyRound, title: "Sua chave OpenRouter", text: "Use a chave da plataforma ou a sua própria, sem limite diário." },
  { icon: Scissors, title: "Edição por trechos", text: "A IA troca só o pedaço certo do arquivo, com diff verde e vermelho." },
  { icon: GitBranch, title: "GitHub nos dois sentidos", text: "Importe um repositório privado e envie commits de volta." },
  { icon: Smartphone, title: "Prévia desktop e celular", text: "Teste a responsividade num simulador de smartphone." },
  { icon: Upload, title: "Seus arquivos e imagens", text: "Arraste HTML, JSON, código e imagens direto na árvore." },
];

const demo = [
  { t: "$ donas build \"landing da minha oficina\"", c: "text-foreground" },
  { t: "  list_files   frontend/src", c: "text-muted-foreground" },
  { t: "  create_file  frontend/src/pages/Home.jsx   +84", c: "text-[hsl(var(--diff-add))]" },
  { t: "  replace      frontend/src/App.js           +3 −1", c: "text-primary" },
  { t: "  create_file  backend/server.py  (FastAPI + MongoDB)", c: "text-[hsl(var(--diff-add))]" },
  { t: "✓ prévia atualizada", c: "text-[hsl(var(--gold))]" },
];

export default function Landing() {
  return (
    <div className="min-h-screen relative overflow-hidden grain bg-background">
      <div className="absolute inset-y-0 right-0 w-full lg:w-[62%] pointer-events-none" data-testid="hero-visual">
        <img src={HERO} alt="" className="h-full w-full object-cover object-[35%_center] opacity-70" />
        <div className="absolute inset-0 bg-gradient-to-r from-background via-background/75 to-background/10" />
        <div className="absolute inset-0 bg-gradient-to-t from-background via-transparent to-background/60" />
      </div>
      <header className="relative z-10 flex items-center justify-between px-6 lg:px-14 h-20">
        <Brand />
        <Link to="/sign-in"><Button variant="ghost" data-testid="header-sign-in-btn">Entrar</Button></Link>
      </header>
      <main className="relative z-10 px-6 lg:px-14 pt-10 lg:pt-16 pb-20 max-w-3xl">
        <section className="anim-rise">
          <p className="font-mono text-xs uppercase tracking-[0.25em] text-[hsl(var(--gold))] mb-6">Donas · Build apps with ai</p>
          <h1 className="font-display text-4xl sm:text-5xl lg:text-6xl font-extrabold leading-[1.02] tracking-tight">
            Descreva o app.<br />A IA constrói<br /><span className="text-primary">o projeto inteiro.</span>
          </h1>
          <p className="mt-8 text-base text-zinc-300 max-w-lg leading-relaxed">
            React no front, Python FastAPI + MongoDB no back. Converse, veja os arquivos surgirem, revise cada trecho alterado e sincronize com o GitHub.
          </p>
          <div className="mt-10 flex flex-wrap gap-3">
            <Link to="/sign-in">
              <Button size="lg" data-testid="hero-start-btn" className="rounded-full px-7 group shadow-[0_0_32px_hsl(var(--primary)/0.45)]">
                Começar com Google <ArrowRight className="ml-2 h-4 w-4 transition-transform duration-150 group-hover:translate-x-1" />
              </Button>
            </Link>
          </div>
        </section>
        <section className="mt-14 anim-rise [animation-delay:150ms] rounded-xl border bg-black/55 backdrop-blur-xl shadow-2xl shadow-black/50 max-w-xl">
          <div className="flex items-center gap-2 px-4 h-10 border-b">
            <Terminal className="h-4 w-4 text-primary" />
            <span className="font-mono text-xs text-muted-foreground">donas · qwen3-coder-next</span>
            <span className="ml-auto h-2 w-2 rounded-full bg-[hsl(var(--gold))] pulse-dot" />
          </div>
          <pre className="p-5 text-[12.5px] leading-7 overflow-x-auto">
            {demo.map((l, i) => (
              <div key={i} className={`anim-rise ${l.c}`} style={{ animationDelay: `${400 + i * 220}ms` }}>{l.t}</div>
            ))}
          </pre>
        </section>
      </main>
      <section className="relative z-10 px-6 lg:px-14 pb-20 grid sm:grid-cols-2 lg:grid-cols-5 gap-4">
        {features.map((f, i) => (
          <div key={f.title} className="anim-rise rounded-xl border bg-card/95 backdrop-blur-md p-6 transition-colors duration-150 hover:border-primary/60" style={{ animationDelay: `${200 + i * 80}ms` }}>
            <f.icon className="h-5 w-5 text-primary mb-5" />
            <h3 className="font-semibold mb-2">{f.title}</h3>
            <p className="text-sm text-muted-foreground leading-relaxed">{f.text}</p>
          </div>
        ))}
      </section>
      <footer className="relative z-10 border-t px-6 lg:px-14 py-8 flex flex-wrap items-center gap-4 text-sm text-muted-foreground" data-testid="site-footer">
        <Brand compact />
        <span>Donas Build apps with ai — crie sites e apps com a sua IA.</span>
        <span className="ml-auto font-mono text-xs">© {new Date().getFullYear()} Donas Build apps with ai</span>
      </footer>
    </div>
  );
}
