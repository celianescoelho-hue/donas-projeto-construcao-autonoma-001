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
  const frameRef = useRef(null);
  const ptokRef = useRef(null);
  const lastStatus = useRef(null);
  const [tick, setTick] = useState(0);
  const [frameKey, setFrameKey] = useState(0);

  useEffect(() => {
    let alive = true; let tries = 0; let timer = null;
    const handle = (d) => {
      if (!alive) return;
      if (d.token && d.token !== ptokRef.current) { ptokRef.current = d.token; stamp.current = null; setTick((x) => x + 1); }
      if (d.status === "running" && lastStatus.current && lastStatus.current !== "running") setFrameKey((k) => k + 1);
      lastStatus.current = d.status;
    };
    const poll = async () => {
      if (!alive) return;
      try {
        const r = await fetch(`${API}/${id}/preview/status`);
        if (r.ok) handle(await r.json());
      } catch {}
      const waiting = ["starting", "installing"].includes(lastStatus.current) || (!lastStatus.current || lastStatus.current === "stopped") && tries < 6;
      if (alive && waiting && tries++ < 120) timer = setTimeout(poll, 3000);
    };
    (async () => {
      try {
        const r = await fetch(`${API}/${id}/preview/run`, { method: "POST" });
        if (r.ok) handle(await r.json());
      } catch {}
      if (alive && lastStatus.current !== "running" && lastStatus.current !== "no_backend") timer = setTimeout(poll, 3000);
    })();
    return () => { alive = false; clearTimeout(timer); };
  }, [id]);

  useEffect(() => {
    const onMsg = (e) => {
      const d = e.data || {};
      if (typeof d.donasRoute === "string") {
        const want = "#" + d.donasRoute;
        if (window.location.hash !== want) window.history.replaceState(null, "", want);
      }
    };
    const onHash = () => {
      const p = decodeURIComponent(window.location.hash.slice(1)) || "/";
      frameRef.current?.contentWindow?.postMessage({ donasNavigate: p }, "*");
    };
    window.addEventListener("message", onMsg);
    window.addEventListener("hashchange", onHash);
    return () => { window.removeEventListener("message", onMsg); window.removeEventListener("hashchange", onHash); };
  }, []);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const initialPath = decodeURIComponent(window.location.hash.slice(1)) || "/";
        const r = await fetch(`${API}/${id}/preview`);
        if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `Erro ${r.status}`);
        const d = await r.json();
        if (!alive) return;
        setError(null);
        if (d.updated_at === stamp.current) return;
        stamp.current = d.updated_at;
        document.title = `${d.name} · Donas`;
        const assets = await loadAssets(id, d.files, cache.current);
        const proxy = ptokRef.current ? { base: `${API}/${id}/preview/proxy/`, token: ptokRef.current } : null;
        if (alive) { setHtml(buildPreview(d.files, assets, d.env, initialPath, proxy).html); setError(null); }
      } catch (e) { if (alive) setError(e.message); }
    };
    load();
    const t = setInterval(load, 10000);
    return () => { alive = false; clearInterval(t); };
  }, [id, tick]);

  if (error) return (
    <div className="h-screen grid place-items-center bg-background text-center px-6" data-testid="live-preview-error">
      <div>
        <p className="font-display text-2xl font-bold mb-2">Prévia indisponível</p>
        <p className="text-sm text-muted-foreground">{error}</p>
      </div>
    </div>
  );
  return (
    <iframe key={frameKey} ref={frameRef} title="Prévia pública" data-testid="live-preview-iframe" srcDoc={html || emptyHtml("Carregando…")}
      sandbox="allow-scripts allow-forms allow-modals allow-popups allow-popups-to-escape-sandbox" referrerPolicy="no-referrer"
      className="fixed inset-0 h-full w-full border-0 bg-white" />
  );
}
