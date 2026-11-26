import * as Babel from "@babel/standalone";

const REACT_V = "18.3.1";
const RR_URL = "https://esm.sh/react-router-dom@6.26.2?external=react,react-dom";
const CODE_EXT = ["js", "jsx", "ts", "tsx", "mjs"];
const ASSET_EXT = ["png", "jpg", "jpeg", "gif", "webp", "svg", "ico"];
const TRY = ["", ".js", ".jsx", ".ts", ".tsx", ".json", "/index.js", "/index.jsx", "/index.ts", "/index.tsx"];
const ENTRY_NAMES = ["index.js", "index.jsx", "index.tsx", "index.ts", "main.jsx", "main.js", "main.tsx", "main.ts"];
const BUILTIN = new Set(["react", "react-dom", "react-dom/client", "react/jsx-runtime", "react/jsx-dev-runtime"]);

const ext = (p) => (p.includes(".") ? p.split(".").pop().toLowerCase() : "");
const dirname = (p) => p.split("/").slice(0, -1).join("/");

function join(base, rel) {
  const out = base ? base.split("/") : [];
  for (const part of rel.split("/")) {
    if (part === "..") out.pop();
    else if (part && part !== ".") out.push(part);
  }
  return out.join("/");
}

function findEntry(map) {
  for (const root of ["frontend/src", "src", "client/src", "web/src", ""]) {
    for (const n of ENTRY_NAMES) {
      const p = root ? `${root}/${n}` : n;
      if (map[p] && /createRoot|render\(/.test(map[p].content || "")) return { entry: p, srcRoot: root };
    }
  }
  for (const root of ["frontend/src", "src", ""]) {
    for (const n of ["App.js", "App.jsx", "App.tsx"]) {
      const p = root ? `${root}/${n}` : n;
      if (map[p]) return { app: p, srcRoot: root };
    }
  }
  return null;
}

function findStaticHtml(map) {
  for (const p of ["index.html", "frontend/index.html", "public/index.html", "site/index.html"]) {
    if (map[p] && !/<div id=["']root["']/.test(map[p].content || "")) return p;
  }
  return Object.keys(map).find((p) => p.endsWith(".html") && !p.includes("public/")) || null;
}

function pkgVersions(map) {
  for (const p of ["frontend/package.json", "package.json"]) {
    try {
      const j = JSON.parse(map[p]?.content || "");
      return { ...(j.dependencies || {}), ...(j.devDependencies || {}) };
    } catch {}
  }
  return {};
}

function bareUrl(spec, versions) {
  const parts = spec.startsWith("@") ? spec.split("/").slice(0, 2) : spec.split("/").slice(0, 1);
  const name = parts.join("/");
  const sub = spec.slice(name.length);
  const v = (versions[name] || "").replace(/^[\^~>=<\s]+/, "").split(" ")[0];
  const ver = v && /^\d/.test(v) ? `@${v}` : "";
  return `https://esm.sh/${name}${ver}${sub}?external=react,react-dom`;
}

const inspectScript = `<script>
(function(){var on=false,box,tag,cur=null;
function ensure(){if(box)return;box=document.createElement('div');box.style.cssText='position:fixed;pointer-events:none;z-index:2147483646;border:2px solid #9B5CF6;background:rgba(155,92,246,.12);border-radius:3px;transition:all .06s;display:none';tag=document.createElement('div');tag.style.cssText='position:fixed;pointer-events:none;z-index:2147483647;background:#9B5CF6;color:#fff;font:11px/1.4 JetBrains Mono,monospace;padding:2px 6px;border-radius:4px;display:none;white-space:nowrap';document.documentElement.appendChild(box);document.documentElement.appendChild(tag);}
function seg(el){var s=el.tagName.toLowerCase();if(el.id)return s+'#'+el.id;var c=(typeof el.className==='string'?el.className:'').trim().split(/\\s+/).filter(Boolean).slice(0,2);if(c.length)s+='.'+c.join('.');var p=el.parentElement;if(p){var same=Array.prototype.filter.call(p.children,function(x){return x.tagName===el.tagName});if(same.length>1)s+=':nth-of-type('+(same.indexOf(el)+1)+')';}return s;}
function sel(el){var parts=[],n=el;while(n&&n.nodeType===1&&n!==document.body&&parts.length<5){parts.unshift(seg(n));if(n.id)break;n=n.parentElement;}return parts.join(' > ');}
function move(e){if(!on)return;var el=e.target;if(!el||el===box||el===tag)return;cur=el;var r=el.getBoundingClientRect();box.style.display='block';box.style.left=r.left+'px';box.style.top=r.top+'px';box.style.width=r.width+'px';box.style.height=r.height+'px';tag.style.display='block';tag.textContent=seg(el)+'  '+Math.round(r.width)+'×'+Math.round(r.height);tag.style.left=Math.max(4,r.left)+'px';tag.style.top=Math.max(4,r.top-22)+'px';}
function stop(){on=false;if(box){box.style.display='none';tag.style.display='none';}document.documentElement.style.cursor='';}
function pick(e){if(!on)return;e.preventDefault();e.stopPropagation();var el=cur||e.target;var src=el.closest&&el.closest('[data-donas-src]');var h=el.outerHTML||'';var open=h.slice(0,h.indexOf('>')+1).replace(/\\sdata-donas-src="[^"]*"/g,'').slice(0,300);
parent.postMessage({donasPick:{selector:sel(el),tag:el.tagName.toLowerCase(),text:(el.innerText||el.textContent||'').trim().replace(/\\s+/g,' ').slice(0,120),html:open,source:src?src.getAttribute('data-donas-src'):null}},'*');stop();parent.postMessage({donasInspect:false},'*');}
document.addEventListener('mousemove',move,true);document.addEventListener('click',pick,true);document.addEventListener('mousedown',function(e){if(on){e.preventDefault();e.stopPropagation();}},true);
document.addEventListener('keydown',function(e){if(on&&e.key==='Escape'){stop();parent.postMessage({donasInspect:false},'*');}},true);
window.addEventListener('message',function(e){if(e.source!==parent||!e.data||typeof e.data.donasInspect!=='boolean')return;if(e.data.donasInspect){ensure();on=true;document.documentElement.style.cursor='crosshair';}else stop();});})();
</script>`;

const errorScript = `<script>
(function(){function post(level,m){if(String(m).indexOf('cdn.tailwindcss.com')>-1)return;try{parent.postMessage({donasLog:{level:level,msg:String(m).slice(0,2000)}},'*')}catch(e){}}
function show(m){var d=document.getElementById('__donas_err');if(!d){d=document.createElement('pre');d.id='__donas_err';d.style.cssText='position:fixed;left:12px;right:12px;bottom:12px;max-height:45%;overflow:auto;z-index:2147483647;background:#1a0b0b;color:#ff8a8a;border:1px solid #ff4d4d55;border-radius:10px;padding:14px;font:12px/1.5 JetBrains Mono,monospace;white-space:pre-wrap';(document.body||document.documentElement).appendChild(d);}d.textContent+=m+'\\n';}
function fmt(a){return Array.prototype.map.call(a,function(x){if(x instanceof Error)return x.message;if(typeof x==='object'){try{return JSON.stringify(x)}catch(e){return String(x)}}return String(x)}).join(' ')}
['log','info','warn','error','debug'].forEach(function(k){var o=console[k];console[k]=function(){post(k==='debug'?'log':k,fmt(arguments));return o.apply(console,arguments)}});
window.__donasShow=show;
window.addEventListener('error',function(e){var m='Erro: '+(e.message||e.error);show(m);post('error',m)});
window.addEventListener('unhandledrejection',function(e){var m='Erro: '+((e.reason&&e.reason.message)||e.reason);show(m);post('error',m)});
window.process={env:Object.assign({NODE_ENV:'development'},window.__DONAS_ENV__||{})};
try{window.localStorage.getItem('x')}catch(e){var mk=function(){var d={};return{getItem:function(k){return k in d?d[k]:null},setItem:function(k,v){d[k]=String(v)},removeItem:function(k){delete d[k]},clear:function(){d={}},key:function(i){return Object.keys(d)[i]||null},get length(){return Object.keys(d).length}}};try{Object.defineProperty(window,'localStorage',{value:mk()});Object.defineProperty(window,'sessionStorage',{value:mk()});}catch(_){}}
try{document.cookie}catch(e){try{Object.defineProperty(document,'cookie',{get:function(){return ''},set:function(){}})}catch(_){}}})();
</script>`;

const envScript = (env) => `<script>window.__DONAS_ENV__=${JSON.stringify(env || {}).replace(/</g, "\\u003c")};</script>`;
const routeScript = (initialPath) => `<script>window.__donasInitialPath=${JSON.stringify(initialPath || "/")};</script>`;

// Rewrites the project's /api calls (fetch + XHR) to the real running backend via the reverse proxy.
const apiProxyScript = (proxy) => {
  if (!proxy || !proxy.base) return `<script>(function(){
  var of=window.fetch;
  function isApi(u){ try{ var s=typeof u==='string'?u:(u&&u.url)||''; s=s.replace(/^(undefined|null)(?=\\/api)/,''); return s==='/api'||s.indexOf('/api/')===0; }catch(e){ return false; } }
  window.fetch=function(input,init){
    if(isApi(input)) return Promise.resolve(new Response(JSON.stringify({detail:'Back-end parado: clique em Rodar back-end na prévia.'}),{status:503,headers:{'Content-Type':'application/json'}}));
    return of(input,init);
  };
})();</script>`;
  const cfg = JSON.stringify({ base: proxy.base, token: proxy.token || "" }).replace(/</g, "\\u003c");
  return `<script>(function(){
  var P=${cfg};
  function rw(u){
    try{
      if(typeof u!=='string') return u;
      if(u.indexOf(P.base)===0) return u;
      if(/^https?:\\/\\//i.test(u)){ try{ var url=new URL(u); if(/^\\/api(\\/|$)/.test(url.pathname)) return P.base+url.pathname.replace(/^\\//,'')+(url.search||''); }catch(e){} return u; }
      if(u.indexOf('/api/')===0||u==='/api') return P.base+u.replace(/^\\//,'');
      return u;
    }catch(e){ return u; }
  }
  var of=window.fetch;
  window.fetch=function(input,init){
    try{
      if(typeof input==='string') input=rw(input);
      else if(input&&input.url) input=new Request(rw(input.url),input);
    }catch(e){}
    init=init||{};
    try{ var h=new Headers(init.headers||(input&&input.headers)||{}); if(P.token) h.set('X-Preview-Token',P.token); init.headers=h; }catch(e){}
    return of(input,init);
  };
  var oo=XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open=function(m,u){ try{ var nu=rw(u); this.__dp=(nu!==u); arguments[1]=nu; }catch(e){} return oo.apply(this,arguments); };
  var osend=XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send=function(b){ try{ if(this.__dp&&P.token) this.setRequestHeader('X-Preview-Token',P.token); }catch(e){} return osend.apply(this,arguments); };
})();</script>`;
};

export function extractRoutes(files) {
  const map = Object.fromEntries((files || []).map((f) => [f.path, f]));
  let content = "";
  for (const root of ["frontend/src", "src", "client/src", "web/src", ""]) {
    for (const n of ["App.js", "App.jsx", "App.tsx"]) {
      const p = root ? `${root}/${n}` : n;
      if (map[p]) content += "\n" + (map[p].content || "");
    }
  }
  if (!content) return [];
  const set = new Set();
  const re = /<Route\b[^>]*?\bpath\s*=\s*(?:["'`]([^"'`]*)["'`]|\{\s*["'`]([^"'`]*)["'`]\s*\})/g;
  let m;
  while ((m = re.exec(content))) {
    let pth = m[1] != null ? m[1] : m[2];
    if (pth == null) continue;
    if (pth === "*" || pth === "") continue;
    if (!pth.startsWith("/")) pth = "/" + pth;
    set.add(pth);
  }
  const arr = Array.from(set);
  if (!arr.includes("/")) arr.unshift("/");
  return arr;
}


export function buildPreview(files, assetUrls, env = {}, initialPath = "/", proxy = null) {
  const penv = proxy ? { ...env, REACT_APP_BACKEND_URL: "", VITE_BACKEND_URL: "", VITE_API_URL: "" } : env;
  const head = apiProxyScript(proxy) + envScript(penv) + routeScript(initialPath) + errorScript + inspectScript;
  const map = Object.fromEntries(files.map((f) => [f.path, f]));
  const urls = [];
  const modules = [];
  const mkBlob = (code) => {
    modules.push(code);
    return `__DONAS_MOD_${modules.length - 1}__`;
  };
  const assetFor = (p) => {
    if (assetUrls[p]) return assetUrls[p];
    if (map[p] && ext(p) === "svg") return (assetUrls[p] = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(map[p].content)}`);
    return null;
  };
  const publicPairs = [];
  for (const p of Object.keys(map)) {
    if (!ASSET_EXT.includes(ext(p))) continue;
    const m = p.match(/^(?:frontend\/)?public\/(.+)$/);
    if (m) publicPairs.push([`/${m[1]}`, p]);
  }
  const rewriteRefs = (text) => {
    let out = text;
    for (const [pub, p] of publicPairs) {
      const u = assetFor(p);
      if (u) out = out.split(`"${pub}"`).join(`"${u}"`).split(`'${pub}'`).join(`'${u}'`).split(`(${pub})`).join(`(${u})`);
    }
    return out;
  };

  const staticHtml = !findEntry(map) && findStaticHtml(map);
  if (staticHtml) return { html: buildStatic(map, staticHtml, assetFor, rewriteRefs, head), urls };

  const found = findEntry(map);
  if (!found) return { html: emptyHtml("Nenhum front-end encontrado ainda. Peça para a IA criar o projeto."), urls };
  const versions = pkgVersions(map);
  const css = [];
  const links = [];
  const compiled = {};
  const visiting = new Set();

  const resolveLocal = (from, spec) => {
    let base;
    if (spec.startsWith("@/")) base = join(found.srcRoot, spec.slice(2));
    else if (spec.startsWith("/")) base = join(dirname(found.srcRoot), spec.slice(1));
    else base = join(dirname(from), spec);
    for (const t of TRY) if (map[base + t]) return base + t;
    return null;
  };

  const cssText = (p) => {
    const d = dirname(p);
    return rewriteRefs(map[p].content.replace(/url\(\s*['"]?([^'")]+)['"]?\s*\)/g, (all, ref) => {
      if (/^(data:|https?:|#)/.test(ref)) return all;
      const u = assetFor(ref.startsWith("/") ? (publicPairs.find(([pub]) => pub === ref) || [])[1] : join(d, ref));
      return u ? `url(${u})` : all;
    }));
  };

  const compile = (path) => {
    if (compiled[path]) return compiled[path];
    if (visiting.has(path)) return mkBlob(`console.warn("Import circular ignorado: ${path}")`);
    visiting.add(path);
    const e = ext(path);
    let code;
    if (e === "json") {
      code = `export default ${map[path].content || "null"};`;
    } else {
      const plugin = ({ types: t }) => ({
        visitor: {
          JSXOpeningElement(p) {
            const n = p.node.name;
            if (n.type !== "JSXIdentifier" || !/^[a-z]/.test(n.name) || !p.node.loc) return;
            if (p.node.attributes.some((a) => a.type === "JSXAttribute" && a.name?.name === "data-donas-src")) return;
            p.node.attributes.push(t.jsxAttribute(t.jsxIdentifier("data-donas-src"), t.stringLiteral(`${path}:${p.node.loc.start.line}`)));
          },
          "ImportDeclaration|ExportNamedDeclaration|ExportAllDeclaration"(p) {
            const src = p.node.source;
            if (!src) return;
            const spec = src.value;
            if (/^(\.|@\/|\/)/.test(spec)) {
              const target = resolveLocal(path, spec);
              if (!target) { src.value = mkBlob(`throw new Error(${JSON.stringify(`Arquivo não encontrado: ${spec} (importado em ${path})`)});\nexport default null;`); return; }
              const te = ext(target);
              if (["css", "scss", "sass", "less"].includes(te)) { css.push(cssText(target)); p.remove(); return; }
              if (ASSET_EXT.includes(te)) {
                const u = assetFor(target) || "";
                const def = (p.node.specifiers || []).find((s) => s.type === "ImportDefaultSpecifier");
                if (def) p.replaceWith(t.variableDeclaration("const", [t.variableDeclarator(t.identifier(def.local.name), t.stringLiteral(u))]));
                else p.remove();
                return;
              }
              src.value = compile(target);
              return;
            }
            if (/\.css$/.test(spec)) { links.push(`https://cdn.jsdelivr.net/npm/${spec}`); p.remove(); return; }
            if (BUILTIN.has(spec)) return;
            if (spec === "react-router-dom" || spec === "react-router") { src.value = routerShim(); return; }
            src.value = bareUrl(spec, versions);
          },
        },
      });
      const presets = [["react", { runtime: "automatic" }]];
      if (["ts", "tsx"].includes(e)) presets.push(["typescript", { isTSX: e === "tsx", allExtensions: true }]);
      try {
        code = Babel.transform(map[path].content || "", { filename: path, presets, plugins: [plugin], sourceType: "module" }).code;
      } catch (err) {
        code = `throw new Error(${JSON.stringify(`Erro de sintaxe em ${path}: ${err.message}`)});\nexport default null;`;
      }
      code = rewriteRefs(code).replace(/import\.meta\.env/g, "window.process.env");
    }
    visiting.delete(path);
    compiled[path] = mkBlob(code);
    return compiled[path];
  };

  let shim = null;
  const routerShim = () => shim || (shim = mkBlob(`import * as RR from "${RR_URL}";
import { createElement as h, useEffect } from "react";
export * from "${RR_URL}";
function DonasNav(){
  var nav = RR.useNavigate();
  var loc = RR.useLocation();
  var here = loc.pathname + (loc.search||'') + (loc.hash||'');
  useEffect(function(){ try{ parent.postMessage({donasRoute: here}, '*'); }catch(e){} }, [here]);
  useEffect(function(){
    function onMsg(e){ if(e && e.data && typeof e.data.donasNavigate === 'string'){ try{ nav(e.data.donasNavigate); }catch(err){} } }
    window.addEventListener('message', onMsg);
    try{ parent.postMessage({donasRoute: here}, '*'); }catch(e){}
    return function(){ window.removeEventListener('message', onMsg); };
  }, [nav]);
  return null;
}
function DonasRouter(props){
  var initial = (typeof window!=='undefined' && window.__donasInitialPath) || '/';
  return h(RR.MemoryRouter, { initialEntries: [initial] }, h(DonasNav, null), props && props.children);
}
export { DonasRouter as BrowserRouter, DonasRouter as HashRouter };`));

  let entryUrl;
  if (found.entry) entryUrl = compile(found.entry);
  else {
    const appUrl = compile(found.app);
    entryUrl = mkBlob(`import App from "${appUrl}";\nimport { createRoot } from "react-dom/client";\nimport { jsx } from "react/jsx-runtime";\ncreateRoot(document.getElementById("root")).render(jsx(App, {}));`);
  }
  const importMap = {
    imports: {
      react: `https://esm.sh/react@${REACT_V}`,
      "react/": `https://esm.sh/react@${REACT_V}/`,
      "react-dom": `https://esm.sh/react-dom@${REACT_V}?external=react`,
      "react-dom/client": `https://esm.sh/react-dom@${REACT_V}/client?external=react`,
      "react-dom/": `https://esm.sh/react-dom@${REACT_V}/`,
    },
  };
  const html = `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
${head}
<script src="https://cdn.tailwindcss.com"></script>
<script type="importmap">${JSON.stringify(importMap)}</script>
${links.map((l) => `<link rel="stylesheet" href="${l}">`).join("\n")}
${css.map((c) => `<style>${c}</style>`).join("\n")}
</head><body><div id="root"></div>
<script type="application/json" id="__donas_modules">${JSON.stringify(modules).replace(/</g, "\\u003c")}</script>
<script>(function(){var mods=JSON.parse(document.getElementById('__donas_modules').textContent),u=[];
mods.forEach(function(c,i){c=c.replace(/__DONAS_MOD_(\\d+)__/g,function(_,n){return u[+n]});u[i]=URL.createObjectURL(new Blob([c],{type:'text/javascript'}));});
var e=${JSON.stringify(entryUrl)}.replace(/__DONAS_MOD_(\\d+)__/,function(_,n){return u[+n]});
import(e).catch(function(err){var m='Erro ao carregar o app: '+(err&&err.message||err);console.error(m);if(window.__donasShow)window.__donasShow(m);});})();</script></body></html>`;
  return { html, urls };
}

function buildStatic(map, htmlPath, assetFor, rewriteRefs, head) {
  const d = dirname(htmlPath);
  let html = map[htmlPath].content;
  html = html.replace(/<link([^>]*?)href=["']([^"']+\.css)["']([^>]*)>/gi, (all, a, href) => {
    const p = join(d, href.replace(/^\//, ""));
    return map[p] ? `<style>${map[p].content}</style>` : all;
  });
  html = html.replace(/<script([^>]*?)src=["']([^"']+\.js)["']([^>]*)><\/script>/gi, (all, a, src, b) => {
    const p = join(d, src.replace(/^\//, ""));
    return map[p] ? `<script${a}${b}>${map[p].content.replace(/<\/script>/g, "<\\/script>")}</script>` : all;
  });
  html = html.replace(/(src|href)=["']([^"']+\.(?:png|jpe?g|gif|webp|svg|ico))["']/gi, (all, attr, ref) => {
    if (/^(https?:|data:)/.test(ref)) return all;
    const u = assetFor(join(d, ref.replace(/^\//, "")));
    return u ? `${attr}="${u}"` : all;
  });
  return head + rewriteRefs(html);
}

export function emptyHtml(msg) {
  return `<!doctype html><html><body style="margin:0;height:100vh;display:grid;place-items:center;background:#0a0a0d;color:#8b8b95;font:14px 'Plus Jakarta Sans',sans-serif"><p>${msg}</p></body></html>`;
}

export const CODE_EXTENSIONS = CODE_EXT;
