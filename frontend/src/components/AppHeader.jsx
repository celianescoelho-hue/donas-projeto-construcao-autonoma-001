import { Link, NavLink } from "react-router-dom";
import { UserButton } from "@clerk/react";
import { Hexagon } from "lucide-react";
import { useMe } from "@/lib/api";
import { AUTH_MODE } from "@/lib/authContext";
import { SelfUserButton } from "@/components/auth/SelfHostAuthProvider";

export const Brand = ({ compact = false }) => (
  <Link to="/" data-testid="brand-link" className="flex items-center gap-2.5 group shrink-0">
    <span className="h-8 w-8 rounded-lg bg-primary grid place-items-center shadow-[0_0_24px_hsl(var(--primary)/0.45)] transition-transform duration-200 group-hover:rotate-[-10deg]">
      <Hexagon className="h-4 w-4 text-white" strokeWidth={2.5} />
    </span>
    <span className="leading-none">
      <span className="font-display text-lg font-extrabold tracking-tight block" data-testid="brand-name">Donas</span>
      {!compact && <span className="font-mono text-[9px] uppercase tracking-[0.22em] text-[hsl(var(--gold))] block mt-0.5">Build apps with ai</span>}
    </span>
  </Link>
);

const nav = "text-sm px-3 py-1.5 rounded-md transition-colors duration-150 hover:bg-secondary";

export default function AppHeader({ children }) {
  const ctx = useMe();
  const me = ctx?.me;
  return (
    <header className="h-14 shrink-0 border-b border-border/80 bg-[#0d0d11] flex items-center gap-4 px-4">
      <Brand />
      {children}
      <nav className="ml-auto flex items-center gap-1">
        <NavLink to="/" end data-testid="nav-projects" className={({ isActive }) => `${nav} ${isActive ? "text-foreground" : "text-muted-foreground"}`}>Projetos</NavLink>
        <NavLink to="/settings" data-testid="nav-settings" className={({ isActive }) => `${nav} ${isActive ? "text-foreground" : "text-muted-foreground"}`}>Configurações</NavLink>
        {me?.role === "admin" && (
          <NavLink to="/admin" data-testid="nav-admin" className={({ isActive }) => `${nav} ${isActive ? "text-primary" : "text-muted-foreground"}`}>Admin</NavLink>
        )}
        <div className="ml-2" data-testid="user-menu">{AUTH_MODE === "selfhost" ? <SelfUserButton /> : <UserButton />}</div>
      </nav>
    </header>
  );
}
