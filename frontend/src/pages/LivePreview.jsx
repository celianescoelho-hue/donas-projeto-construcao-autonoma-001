import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { buildPreview, emptyHtml } from "@/lib/preview";

const API = `${process.env.REACT_APP_BACKEND_URL}/api/public/projects`;

const toDataUrl = (blob) => new Promise((ok, fail) => { const fr = new FileReader(); fr.onload = () => ok(fr.result); fr.onerror = fail; fr.readAsDataURL(blob); });

async function loadAssets(id, files, cache) {
  await Promise.all(files.filter((f) => f.kind === "binary" && cache[f.path]?.size !== f.size).map(async (f) => {
    try {
      const r = await fetch(`${API}/${id}/asset?path=${encodeURIComponent(f.path)}`);
      if (r.ok) cache[f.path] = { size: f.size, url: await toDataUrl(await r.blob()) };
    } catch {}
  }));
  return Object.fromEntries(Object.entries(cache).map(([k, v]) => [k, v.url]));
}

export default function LivePreview() {
  const { id } = useParams();
  const [html, setHtml] = useState(null);
  const [error, setError] = useState(null);
  const stamp = useRef(null);
  const cache = useRef({});

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const r = await fetch(`${API}/${id}/preview`);
        if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `Erro ${r.status}`);
        const d = await r.json();
        if (!alive || d.updated_at === stamp.current) return;
        stamp.current = d.updated_at;
        document.title = `${d.name} · Donas`;
        const assets = await loadAssets(id, d.files, cache.current);
        if (alive) { setHtml(buildPreview(d.files, assets, d.env).html); setError(null); }
      } catch (e) { if (alive) setError(e.message); }
    };
    load();
    const t = setInterval(load, 10000);
    return () => { alive = false; clearInterval(t); };
  }, [id]);

  if (error) return (
    <div className="h-screen grid place-items-center bg-background text-center px-6" data-testid="live-preview-error">
      <div>
        <p className="font-display text-2xl font-bold mb-2">Prévia indisponível</p>
        <p className="text-sm text-muted-foreground">{error}</p>
      </div>
    </div>
  );
  return (
    <iframe title="Prévia pública" data-testid="live-preview-iframe" srcDoc={html || emptyHtml("Carregando…")}
      sandbox="allow-scripts allow-forms allow-modals allow-popups allow-popups-to-escape-sandbox" referrerPolicy="no-referrer"
      className="fixed inset-0 h-full w-full border-0 bg-white" />
  );
}
