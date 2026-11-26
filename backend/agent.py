import os
import json
import fnmatch
import asyncio
from datetime import datetime, timezone

import httpx

import io
import re
from urllib.parse import urlparse
from starlette.concurrency import run_in_threadpool
from core import (db, now, new_id, decrypt, get_settings, unified_diff, record_version, file_snapshot,
                  OPENROUTER_BASE, logger, get_object, store_binary, summarize_text)

MAX_STEPS = 30
SMALL_FILE_LINES = 60
RETRYABLE_STATUS = {429, 502, 503, 529}


class ModelUnavailable(Exception):
    def __init__(self, status, detail=""):
        super().__init__(f"{status}: {detail}")
        self.status, self.detail = status, detail

SYSTEM_PROMPT = """Você é o Donas (Donas Build apps with ai), um engenheiro full-stack sênior que constrói sites e apps completos.
Padrão de projeto (siga sempre, a menos que o projeto importado use outra estrutura — então respeite a existente):
- frontend/  → React (JS/JSX). Entrada em frontend/src/index.js que renderiza <App/> em #root. Componentes em frontend/src/components, páginas em frontend/src/pages. Estilos em CSS (importe com import './x.css') ou classes Tailwind (Tailwind já está disponível na prévia). Inclua frontend/package.json.
- backend/   → Python FastAPI (backend/server.py) com MongoDB via motor (AsyncIOMotorClient), lendo MONGO_URL e DB_NAME do ambiente; backend/requirements.txt (fastapi, uvicorn, motor, python-dotenv, pydantic) e backend/.env.example (MONGO_URL, DB_NAME, CORS_ORIGINS). Todas as rotas com prefixo /api. Nunca retorne o _id do Mongo; use um campo id (uuid) próprio. O front lê a URL do back de process.env.REACT_APP_BACKEND_URL (na prévia use chamadas relativas a /api). IMPORTANTE: o backend RODA DE VERDADE na prévia — defina obrigatoriamente `app = FastAPI()` em backend/server.py (variável chamada `app`), habilite CORS, e NÃO fixe host/porta (a plataforma inicia com uvicorn server:app na porta que escolher). Liste toda dependência usada em backend/requirements.txt.
- README.md  → como rodar.
A prévia ao vivo roda apenas o front-end React no navegador (pacotes npm vêm de esm.sh). Faça o front funcionar com dados de exemplo quando o back-end não estiver disponível.

SEGURANÇA OBRIGATÓRIA (sempre, em todo back-end gerado):
- Senhas de usuários SEMPRE com hash bcrypt (passlib[bcrypt] ou bcrypt); nunca salvar nem retornar senha em texto puro.
- Autenticação por JWT (PyJWT) com segredo JWT_SECRET vindo do .env e expiração; rotas privadas protegidas por uma dependência FastAPI (Depends) que valida o token. Papéis/admin verificados no servidor.
- Toda entrada validada com modelos Pydantic (tipos, tamanhos, EmailStr, Field(min_length/max_length)); nunca passar o corpo da requisição direto para o banco ($set: body).
- Segredos (MONGO_URL, JWT_SECRET, chaves de API) apenas em variáveis de ambiente: lidos com os.environ, listados em backend/.env.example sem valores reais; nunca colocar chaves no front-end nem no código.
- CORS restrito por CORS_ORIGINS do .env, rate limit simples em login/cadastro, e mensagens de erro sem detalhes internos.

FERRAMENTAS — você NÃO tem terminal, shell, git, npm, pip nem acesso à internet. Não existe run_shell_command, execute_command, bash, git clone nem nada parecido: nunca tente chamá-los. Você só pode usar estas ferramentas: list_files, read_file, search_in_files, replace_in_file, create_file, delete_file, move_or_copy_file, clean_external_links, extract_zip.
- Para instalar dependências, apenas edite frontend/package.json ou backend/requirements.txt e explique os comandos no README.
- Se o usuário pedir para clonar/importar um repositório do GitHub, diga para ele usar o botão "Importar do GitHub" (a plataforma baixa os arquivos sozinha); não tente clonar.
Trabalhe como um agente:
- Use search_in_files (texto ou regex, devolve arquivo:linha) para achar onde algo está ANTES de ler; depois read_file só no intervalo de linhas necessário. Use list_files / read_file / search_in_files para entender o projeto antes de editar arquivos existentes. Leia só os trechos necessários (start_line/end_line).
- Para pequenas alterações em um arquivo EXISTENTE prefira replace_in_file enviando APENAS o trecho antigo (old_text, exato, único no arquivo, com contexto suficiente) e o novo. Quando a mudança for grande (reestruturar boa parte do arquivo), use create_file com o conteúdo COMPLETO e final do arquivo — ele sobrescreve o arquivo existente de uma vez. Nunca envie arquivo parcial ou com "..." no create_file.
- Se uma substituição falhar, leia o trecho atual com read_file e tente de novo.
- Crie vários arquivos pequenos e bem organizados. Não repita o código dos arquivos na resposta de texto.
- ARQUIVOS GRANDES (ex.: HTML salvo do navegador com 150 KB+): NUNCA leia o arquivo inteiro nem o recrie com create_file — isso estoura o limite de tokens. Para mover/copiar use move_or_copy_file; para remover links externos use clean_external_links (rode antes com dry_run=true para ver os domínios); para ajustes pontuais use search_in_files + read_file com start_line/end_line + replace_in_file. Para .zip use extract_zip.
- Anexos do chat chegam como "[ANEXOS ...]" com caminho e resumo: o conteúdo NÃO está na mensagem, ele já está salvo no projeto naquele caminho.
- Arquivos enviados pelo usuário aparecem no mapa com um resumo; leia trechos quando precisar de detalhes. Imagens enviadas podem ser usadas pelo caminho (ex.: import logo from './assets/logo.png' ou '/logo.png' se estiver em frontend/public).
Ao final, responda em português com um resumo curto (3-6 linhas) do que foi feito e próximos passos."""

TOOLS = [
    {"type": "function", "function": {"name": "list_files", "description": "Lista arquivos do projeto (opcionalmente dentro de uma pasta).",
        "parameters": {"type": "object", "properties": {"directory": {"type": "string", "description": "Pasta, ex: frontend/src. Vazio = tudo."}}}}},
    {"type": "function", "function": {"name": "read_file", "description": "Lê um arquivo inteiro ou um intervalo de linhas (numeradas a partir de 1).",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "search_in_files", "description": "Busca global em todos os arquivos de texto do projeto. O argumento 'query' é OBRIGATÓRIO e deve conter o texto (ou regex) a procurar, nunca vazio. Exemplo: {\"query\": \"useState\"} ou {\"query\": \"class=\\\"hero\", \"path_glob\": \"frontend/src/*\"}. Retorna arquivo:linha:coluna e o trecho. Para listar arquivos use list_files.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "minLength": 1, "description": "Texto ou regex a procurar (obrigatório, não vazio). Ex.: 'Cliques', 'function App', 'https?://'"},
            "regex": {"type": "boolean", "description": "true = query é regex Python; padrão false (texto literal)"},
            "case_sensitive": {"type": "boolean", "description": "Padrão false"},
            "path_glob": {"type": "string", "description": "Filtro opcional de caminho, ex.: frontend/src/*.jsx ou frontend/src/ (pasta)"},
            "context": {"type": "integer", "minimum": 0, "maximum": 3, "description": "Linhas de contexto antes/depois"},
            "max_results": {"type": "integer", "minimum": 1, "maximum": 200}},
            "required": ["query"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "replace_in_file", "description": "Substitui um trecho exato e único de um arquivo existente por um novo trecho.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}}},
    {"type": "function", "function": {"name": "create_file", "description": "Cria um arquivo novo ou SOBRESCREVE um existente com o conteúdo completo enviado (use para reescritas grandes; para ajustes pequenos prefira replace_in_file).",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}},
    {"type": "function", "function": {"name": "delete_file", "description": "Apaga um arquivo do projeto.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "move_or_copy_file", "description": "Move ou copia um arquivo de QUALQUER tamanho (texto, imagem, pdf, zip) direto no servidor, sem passar o conteúdo pela IA. Se dest terminar com '/', mantém o nome do arquivo.",
        "parameters": {"type": "object", "properties": {"source": {"type": "string"}, "dest": {"type": "string", "description": "Ex.: frontend/public/pagina.html ou frontend/public/"},
                       "mode": {"type": "string", "enum": ["move", "copy"], "description": "Padrão: copy"}, "overwrite": {"type": "boolean"}}, "required": ["source", "dest"]}}},
    {"type": "function", "function": {"name": "clean_external_links", "description": "Remove links externos (href/src/action/srcset de outros domínios) de um HTML direto no servidor, preservando todo o resto do HTML/CSS byte a byte. Links <a> viram '#', scripts externos são removidos, imagens/iframes externos ficam vazios. Use dry_run=true para só listar os domínios.",
        "parameters": {"type": "object", "properties": {"source": {"type": "string"}, "dest": {"type": "string", "description": "Opcional; padrão = sobrescrever source"},
                       "keep_domains": {"type": "array", "items": {"type": "string"}, "description": "Domínios a manter, ex.: fonts.googleapis.com"},
                       "keep_stylesheets": {"type": "boolean", "description": "Manter <link rel=stylesheet> externos (padrão true)"},
                       "dry_run": {"type": "boolean"}}, "required": ["source"]}}},
    {"type": "function", "function": {"name": "extract_zip", "description": "Descompacta um .zip do projeto numa pasta, direto no servidor (ignora node_modules, build, .git e arquivos > 5 MB).",
        "parameters": {"type": "object", "properties": {"source": {"type": "string"}, "dest_dir": {"type": "string", "description": "Pasta destino, ex.: uploads/site"}}, "required": ["source", "dest_dir"]}}},
    {"type": "function", "function": {"name": "html_to_js_module", "description": "Converte um .html grande (ex.: frontend/public/bling_login.html) num módulo JS 'export default \"<html>\";' dentro de frontend/src/, direto no servidor, limpando links externos e <script> antigos. Use quando a prévia não carrega um HTML da pasta public via fetch: depois é só importar no React (import html from './bling_login_raw.js') e usar com dangerouslySetInnerHTML.",
        "parameters": {"type": "object", "properties": {
            "html_path": {"type": "string", "description": "HTML de origem, ex.: frontend/public/bling_login.html"},
            "js_path": {"type": "string", "description": "Destino .js dentro de frontend/src/, ex.: frontend/src/bling_login_raw.js"},
            "keep_domains": {"type": "array", "items": {"type": "string"}, "description": "Domínios a manter nos links/estilos"},
            "keep_stylesheets": {"type": "boolean", "description": "Manter <link rel=stylesheet> externos (padrão true)"}},
            "required": ["html_path", "js_path"], "additionalProperties": False}}},
]

LINK_ATTR = re.compile(r'(\s(?:href|src|action|poster|data-src|srcset)\s*=\s*)(["\'])(.*?)\2', re.I | re.S)
TAG_RE = re.compile(r'<([a-zA-Z][\w-]*)(\s(?:[^<>"\']|"[^"]*"|\'[^\']*\')*)?/?>', re.S)
EXT_SCRIPT = re.compile(r'<script\b[^>]*?\ssrc\s*=\s*(["\'])((?:https?:)?//[^"\']+)\1[^>]*>\s*</script\s*>', re.I | re.S)
ALL_SCRIPT = re.compile(r'<script\b[^>]*>.*?</script\s*>', re.I | re.S)
ORPHAN_SCRIPT = re.compile(r'<script\b[^>]*/?>', re.I)


def _host(url: str):
    u = url.strip()
    if not re.match(r'^(?:https?:)?//', u, re.I):
        return None
    return (urlparse(u if not u.startswith("//") else "http:" + u).hostname or "").lower() or None


def _kept(host: str, keep: list) -> bool:
    return any(host == k or host.endswith("." + k) for k in keep)


def strip_external(html: str, keep: list, keep_styles: bool):
    stats, domains = {"links": 0, "scripts": 0, "media": 0, "link_tags": 0}, {}

    def ext(url):
        h = _host(url)
        if h and not _kept(h, keep):
            domains[h] = domains.get(h, 0) + 1
            return True
        return False

    def drop_script(m):
        if ext(m.group(2)):
            stats["scripts"] += 1
            return ""
        return m.group(0)
    out = EXT_SCRIPT.sub(drop_script, html)

    def fix_tag(m):
        tag, attrs = m.group(1).lower(), m.group(2) or ""
        if not LINK_ATTR.search(attrs):
            return m.group(0)
        if tag == "link":
            href = re.search(r'\shref\s*=\s*(["\'])(.*?)\1', attrs, re.I | re.S)
            rel = (re.search(r'\srel\s*=\s*(["\'])(.*?)\1', attrs, re.I | re.S) or [None, None, ""])[2].lower()
            if href and _host(href.group(2)):
                if keep_styles and ("stylesheet" in rel or "icon" in rel):
                    return m.group(0)
                if ext(href.group(2)):
                    stats["link_tags"] += 1
                    return ""
            return m.group(0)

        def fix_attr(a):
            name = a.group(1).strip().split("=")[0].strip().lower()
            val = a.group(3)
            if name == "srcset":
                if any(ext(part.strip().split(" ")[0]) for part in val.split(",") if part.strip()):
                    stats["media"] += 1
                    return f"{a.group(1)}{a.group(2)}{a.group(2)}"
                return a.group(0)
            if not ext(val):
                return a.group(0)
            if tag in ("a", "area", "form") or name == "action":
                stats["links"] += 1
                return f"{a.group(1)}{a.group(2)}#{a.group(2)}"
            stats["media"] += 1
            return f"{a.group(1)}{a.group(2)}{'about:blank' if tag == 'iframe' else ''}{a.group(2)}"
        new_attrs = LINK_ATTR.sub(fix_attr, attrs)
        return m.group(0).replace(attrs, new_attrs, 1) if new_attrs != attrs else m.group(0)
    out = TAG_RE.sub(fix_tag, out)
    return out, stats, domains


def attachments_note(atts: list) -> str:
    if not atts:
        return ""
    lines = [f"- {a['path']} ({a['kind']}, {round((a.get('size') or 0) / 1024, 1)} KB){': ' + a['summary'] if a.get('summary') else ''}" for a in atts]
    return ("\n\n[ANEXOS — já salvos no projeto nestes caminhos; o conteúdo NÃO está colado aqui. "
            "Use read_file por trechos, search_in_files, move_or_copy_file, clean_external_links ou extract_zip]\n" + "\n".join(lines))


HISTORY_LIMIT = 6
MAX_NUDGES = 2
FAKE_LOG = re.compile(r"\n?\[Altera[çc][õo]es:[^\]]*\]", re.I)
CLAIM = re.compile(
    r"\[Altera[çc][õo]es:"
    r"|arquivos?\s+(?:criados?|atualizados?|editados?|modificados?|alterados?|salvos?)\s*[:\-–]"
    r"|arquivos?\s+[\w./-]+\.\w{1,5}\s+(?:foi|foram)\s+(?:criados?|atualizados?|editados?|modificados?|alterados?|salvos?)"
    r"|(?:criei|atualizei|editei|modifiquei|alterei|adicionei|substitu[ií])\s+(?:o |a |os |as )?(?:arquivo|componente|p[áa]gina|c[óo]digo)"
    r"|\b\d+ arquivo\(s\)"
    r"|(?:create_file|replace_in_file|delete_file)\s*[:(]", re.I)
NEGATION = re.compile(r"\b(?:n[ãa]o|nenhum|nenhuma|nada|sem|nunca|ainda n[ãa]o)\b[^.!?\n]*$", re.I)
TOOL_RULE = ("\n\nREGRA CRÍTICA: alterações só existem se você CHAMAR as ferramentas (tool_calls). Nunca escreva 'Arquivo criado', "
             "'[Alterações: ...]' ou um resumo de mudanças sem ter chamado create_file/replace_in_file/delete_file/move_or_copy_file antes. "
             "Se o pedido exige mudar arquivos, comece chamando as ferramentas.")
NUDGE = ("SISTEMA: sua última resposta descreveu alterações, mas você NÃO chamou nenhuma ferramenta — nenhum arquivo foi modificado. "
         "Faça agora as alterações de verdade chamando as ferramentas (search_in_files/read_file para localizar, depois replace_in_file ou create_file). "
         "Não escreva resumo antes de concluir as chamadas.")


def fake_claim(text: str) -> bool:
    for m in CLAIM.finditer(text or ""):
        if not NEGATION.search(text[max(0, m.start() - 60):m.start()]):
            return True
    return False


READ_BUDGET = 18000
LINE_CAP = 2000


TOOL_NAMES = {t["function"]["name"] for t in TOOLS} | {"search_files"}


def clean_path(p: str) -> str:
    parts = [x for x in (p or "").strip().replace("\\", "/").split("/") if x not in ("", ".")]
    if ".." in parts:
        raise ValueError("Caminho inválido")
    return "/".join(parts)


async def project_map(project_id: str) -> str:
    files = await db.files.find({"project_id": project_id}, {"_id": 0, "path": 1, "kind": 1, "content": 1, "summary": 1, "uploaded": 1}).sort("path", 1).to_list(5000)
    if not files:
        return "(projeto vazio)"
    lines = []
    for f in files[:400]:
        if f["kind"] == "text":
            info = f"{(f.get('content') or '').count(chr(10)) + 1} linhas"
        else:
            info = "binário"
        extra = f" — {f['summary']}" if f.get("uploaded") and f.get("summary") else ""
        lines.append(f"{f['path']} ({info}){extra}")
    if len(files) > 400:
        lines.append(f"... e mais {len(files) - 400} arquivos (use list_files).")
    return "\n".join(lines)


class Agent:
    def __init__(self, project: dict, member: dict, queue: asyncio.Queue):
        self.project = project
        self.pid = project["id"]
        self.member = member
        self.q = queue
        self.changes: dict = {}
        self.change_cards: list = []
        self.text = ""
        self.cost = 0.0
        self.tokens = 0
        self.unknown_streak = 0
        self.warnings: list = []
        self.stream_buf = ""
        self.nudges = 0
        self.force_tools = False

    async def emit(self, event: dict):
        await self.q.put(event)

    async def warn(self, message: str):
        if message not in self.warnings:
            self.warnings.append(message)
        await self.emit({"type": "warning", "message": message})

    async def _light_card(self, path, op, added, removed, note):
        card = {"path": path, "op": op, "added": added, "removed": removed, "diff": note}
        self.change_cards.append(card)
        await self.emit({"type": "change", **card})

    async def _search(self, args):
        query = next((v for k in ("query", "pattern", "search", "text", "term", "keyword", "q")
                      if isinstance(v := args.get(k), str) and v.strip()), "")
        if not query and isinstance(args.get("regex"), str) and args["regex"].strip():
            query, args = args["regex"], {**args, "regex": True}
        if not query:
            return ('ERRO: search_in_files precisa do argumento "query" com o texto a procurar (não pode ser vazio). '
                    'Exemplo: {"query": "useState"}. Para ver os arquivos use list_files.')
        flags = 0 if args.get("case_sensitive") else re.I
        try:
            rx = re.compile(query if args.get("regex") else re.escape(query), flags)
        except re.error as e:
            return f"ERRO: regex inválida ({e})."
        glob = args.get("path_glob") or args.get("glob") or args.get("path") or args.get("directory")
        if glob and not any(c in glob for c in "*?["):
            glob = glob.rstrip("/") + ("/*" if "." not in glob.split("/")[-1] else "")
        ctx = max(0, min(3, int(args.get("context") or 0)))
        limit = max(1, min(200, int(args.get("max_results") or 80)))
        out, hits, files_hit = [], 0, set()
        async for f in db.files.find({"project_id": self.pid, "kind": "text"}, {"_id": 0, "path": 1, "content": 1}).sort("path", 1):
            if glob and not (fnmatch.fnmatch(f["path"], glob) or fnmatch.fnmatch(f["path"], glob.replace("**/", ""))):
                continue
            lines = f["content"].split("\n")
            for i, line in enumerate(lines, 1):
                m = rx.search(line)
                if not m:
                    continue
                hits += 1
                files_hit.add(f["path"])
                start = max(0, m.start() - 60)
                snippet = ("…" if start else "") + line[start:m.end() + 100].strip()
                out.append(f"{f['path']}:{i}:{m.start() + 1}: {snippet[:220]}")
                for j in range(max(1, i - ctx), min(len(lines), i + ctx) + 1):
                    if j != i:
                        out.append(f"   {j}| {lines[j - 1].strip()[:160]}")
                if hits >= limit:
                    return "\n".join(out) + f"\n(limite de {limit} resultados — refine a busca ou use path_glob)"
        return (f"{hits} resultado(s) em {len(files_hit)} arquivo(s):\n" + "\n".join(out)) if out else "Nenhum resultado."

    async def _read_pdf(self, f, args):
        data, _ = await run_in_threadpool(get_object, f["storage_path"])

        def extract():
            from pypdf import PdfReader
            r = PdfReader(io.BytesIO(data))
            s = max(1, int(args.get("start_line") or 1))
            e = min(len(r.pages), int(args.get("end_line") or len(r.pages)))
            out, used, last = [], 0, s - 1
            for i in range(s, e + 1):
                t = (r.pages[i - 1].extract_text() or "").strip()
                if used + len(t) > READ_BUDGET and out:
                    break
                out.append(f"--- página {i} ---\n{t[:READ_BUDGET]}")
                used += len(t)
                last = i
            return len(r.pages), last, "\n".join(out)
        total, last, body = await run_in_threadpool(extract)
        more = f"\n[continue com start_line={last + 1}]" if last < total else ""
        return f"{f['path']} (PDF, páginas até {last} de {total}; start_line/end_line = páginas)\n{body}{more}"

    async def _move_copy(self, args):
        src = clean_path(args["source"])
        raw_dest = (args.get("dest") or "").strip()
        dest = clean_path(raw_dest)
        mode = (args.get("mode") or "copy").lower()
        if mode not in ("move", "copy"):
            return "ERRO: mode deve ser 'move' ou 'copy'."
        f = await self._get(src)
        if not f:
            return f"ERRO: '{src}' não existe."
        name = src.split("/")[-1]
        is_dir = raw_dest.endswith("/") or not dest or await db.files.find_one({"project_id": self.pid, "path": {"$regex": "^" + re.escape(dest) + "/"}}, {"_id": 1})
        if is_dir:
            dest = f"{dest}/{name}" if dest else name
        if dest == src:
            return "ERRO: origem e destino são iguais."
        existing = await self._get(dest)
        if existing and not args.get("overwrite"):
            return f"ERRO: '{dest}' já existe. Use overwrite=true para substituir."
        doc = {k: v for k, v in f.items() if k not in ("path", "updated_at")}
        doc.update({"path": dest, "updated_at": now()})
        if doc["kind"] == "text" and doc.get("uploaded"):
            doc["summary"] = summarize_text(dest, doc["content"])
        await db.files.update_one({"project_id": self.pid, "path": dest}, {"$set": doc}, upsert=True)
        self._track(dest, existing, doc)
        n = (doc.get("content") or "").count("\n") + 1 if doc["kind"] == "text" else 0
        kb = round((doc.get("size") or 0) / 1024, 1)
        await self._light_card(dest, "edit" if existing else "create", n, 0, f"({'movido' if mode == 'move' else 'copiado'} de {src}: {kb} KB — conteúdo idêntico, diff omitido)")
        if mode == "move":
            await db.files.delete_one({"project_id": self.pid, "path": src})
            self._track(src, f, None)
            await self._light_card(src, "delete", 0, n, f"(movido para {dest})")
        return f"OK: {src} {'movido' if mode == 'move' else 'copiado'} para {dest} ({kb} KB, sem passar pela IA)."

    async def _clean_links(self, args):
        src = clean_path(args["source"])
        dest = clean_path(args.get("dest") or "") or src
        f = await self._get(src)
        if not f or f["kind"] != "text":
            return f"ERRO: '{src}' não existe ou não é texto."
        keep = [k.strip().lower().lstrip(".") for k in (args.get("keep_domains") or []) if k and k.strip()]
        out, stats, domains = await run_in_threadpool(strip_external, f["content"], keep, args.get("keep_stylesheets", True) is not False)
        top = ", ".join(f"{d} ({c})" for d, c in sorted(domains.items(), key=lambda x: -x[1])[:30]) or "nenhum"
        if args.get("dry_run"):
            return f"DRY RUN {src}: domínios externos encontrados: {top}. Nada foi alterado."
        changed = sum(stats.values())
        if not changed and dest == src:
            return f"OK: nenhum link externo encontrado em {src}."
        before = await self._get(dest) if dest != src else f
        await self._write(dest, before, out)
        await self._light_card(dest, "edit" if before else "create", changed, changed,
                               f"(links externos limpos no servidor: {stats['links']} links → '#', {stats['scripts']} scripts removidos, "
                               f"{stats['media']} mídias esvaziadas, {stats['link_tags']} <link> removidos; {len(f['content'])//1024} KB → {len(out)//1024} KB. Domínios: {top})")
        return (f"OK: {dest} salvo. {stats['links']} links viraram '#', {stats['scripts']} scripts externos removidos, "
                f"{stats['media']} src/srcset esvaziados, {stats['link_tags']} <link> removidos. Domínios: {top}. "
                f"Tamanho {len(f['content'])} → {len(out)} bytes; o resto do HTML/CSS ficou idêntico.")

    async def _extract_zip(self, args):
        from github_sync import _extract
        src = clean_path(args["source"])
        base = clean_path(args.get("dest_dir") or "")
        f = await self._get(src)
        if not f or f.get("content_type") != "application/zip":
            return f"ERRO: '{src}' não é um .zip do projeto."
        data, _ = await run_in_threadpool(get_object, f["storage_path"])
        texts, images, skipped = await run_in_threadpool(_extract, data, False)
        n = 0
        for path, text, size in texts:
            p = f"{base}/{path}" if base else path
            before = await self._get(p)
            doc = {"project_id": self.pid, "path": p, "kind": "text", "content": text, "size": size, "uploaded": True,
                   "summary": summarize_text(p, text), "updated_at": now()}
            await db.files.update_one({"project_id": self.pid, "path": p}, {"$set": doc}, upsert=True)
            self._track(p, before, doc)
            n += 1
        for path, blob, ctype in images:
            p = f"{base}/{path}" if base else path
            before = await self._get(p)
            sp = await store_binary(self.member["user_id"], p, blob, ctype)
            doc = {"project_id": self.pid, "path": p, "kind": "binary", "storage_path": sp, "content_type": ctype,
                   "size": len(blob), "uploaded": True, "summary": f"Imagem {ctype}, {len(blob)//1024} KB.", "updated_at": now()}
            await db.files.update_one({"project_id": self.pid, "path": p}, {"$set": doc}, upsert=True)
            self._track(p, before, doc)
            n += 1
        await self._light_card(base or "/", "create", n, 0, f"({n} arquivos extraídos de {src}; {len(skipped)} ignorados)")
        names = ", ".join(p for p, _, _ in texts[:20])
        return f"OK: {n} arquivos extraídos de {src} para '{base or '/'}' ({len(skipped)} ignorados). Ex.: {names}"

    async def _html_to_js_module(self, args):
        src = clean_path(args["html_path"])
        dest = clean_path(args["js_path"])
        if not dest.startswith("frontend/src/"):
            return "ERRO: js_path deve ficar dentro de frontend/src/ (ex.: frontend/src/bling_login_raw.js) para o React importar."
        if not dest.endswith(".js"):
            return "ERRO: js_path deve terminar em .js."
        f = await self._get(src)
        if not f or f["kind"] != "text":
            return f"ERRO: '{src}' não existe ou não é um arquivo de texto (.html)."
        keep = [k.strip().lower().lstrip(".") for k in (args.get("keep_domains") or []) if k and k.strip()]
        cleaned, stats, domains = await run_in_threadpool(strip_external, f["content"], keep, args.get("keep_stylesheets", True) is not False)
        scripts_removed = stats["scripts"] + len(ALL_SCRIPT.findall(cleaned))
        cleaned = ALL_SCRIPT.sub("", cleaned)
        scripts_removed += len(ORPHAN_SCRIPT.findall(cleaned))
        cleaned = ORPHAN_SCRIPT.sub("", cleaned)
        module = "// Gerado por html_to_js_module a partir de " + src + " — não edite à mão.\nexport default " + json.dumps(cleaned) + ";\n"
        before = await self._get(dest)
        await self._write(dest, before, module)
        n = module.count("\n") + 1
        top = ", ".join(sorted(domains)[:20]) or "nenhum"
        await self._light_card(dest, "edit" if before else "create", n, before.get("content", "").count("\n") + 1 if before else 0,
                               f"(módulo JS gerado de {src}: {len(f['content'])//1024} KB de HTML embutido; {scripts_removed} <script> (externos e inline) e {stats['link_tags']} <link> externos removidos. Importe com: import html from './{dest.split('/')[-1]}')")
        return (f"OK: {dest} criado como módulo JS (export default). HTML de {len(f['content'])} bytes embutido; "
                f"{scripts_removed} <script> removidos, {stats['link_tags']} <link> externos removidos, {stats['links']} links → '#'. Domínios: {top}. "
                f"No React: import html from './{dest.split('/')[-1]}'; e use <div dangerouslySetInnerHTML={{{{ __html: html }}}} />.")

    async def _get(self, path):
        return await db.files.find_one({"project_id": self.pid, "path": path}, {"_id": 0})

    async def _write(self, path, before, content):
        doc = {"project_id": self.pid, "path": path, "kind": "text", "content": content,
               "size": len(content.encode()), "updated_at": now()}
        if before:
            doc["uploaded"] = before.get("uploaded", False)
            doc["summary"] = before.get("summary")
        await db.files.update_one({"project_id": self.pid, "path": path}, {"$set": doc}, upsert=True)
        self._track(path, before, doc)

    def _track(self, path, before, after):
        if path not in self.changes:
            self.changes[path] = {"before": file_snapshot(before), "after": None}
        self.changes[path]["after"] = file_snapshot(after)

    async def _card(self, path, op, before_text, after_text):
        d = unified_diff(path, before_text, after_text)
        card = {"path": path, "op": op, **d}
        self.change_cards.append(card)
        await self.emit({"type": "change", **card})

    async def run_tool(self, name: str, args: dict) -> str:
        try:
            if name == "list_files":
                d = clean_path(args.get("directory") or "")
                q = {"project_id": self.pid}
                if d:
                    q["path"] = {"$regex": "^" + __import__("re").escape(d) + "/"}
                files = await db.files.find(q, {"_id": 0, "path": 1, "kind": 1, "size": 1}).sort("path", 1).to_list(3000)
                return "\n".join(f"{f['path']} ({f.get('size', 0)} bytes{', binário' if f['kind'] != 'text' else ''})" for f in files) or "Nenhum arquivo."
            if name == "read_file":
                path = clean_path(args["path"])
                f = await self._get(path)
                if not f:
                    return f"ERRO: arquivo '{path}' não existe."
                if f["kind"] != "text":
                    if f.get("content_type") == "application/pdf":
                        return await self._read_pdf(f, args)
                    return f"Arquivo binário. {f.get('summary') or ''}"
                lines = f["content"].split("\n")
                s = max(1, int(args.get("start_line") or 1))
                e = min(len(lines), int(args.get("end_line") or len(lines)))
                if e - s > 600:
                    e = s + 600
                out, used, last = [], 0, s - 1
                for i in range(s, e + 1):
                    ln = lines[i - 1]
                    if len(ln) > LINE_CAP:
                        ln = ln[:LINE_CAP] + f" …[linha cortada: {len(lines[i - 1])} caracteres; use search_in_files para achar trechos]"
                    if used + len(ln) > READ_BUDGET and out:
                        break
                    out.append(f"{i}: {ln}")
                    used += len(ln)
                    last = i
                more = f"\n[parado na linha {last} para não estourar tokens; continue com start_line={last + 1}]" if last < e else ""
                return f"{path} (linhas {s}-{last} de {len(lines)})\n" + "\n".join(out) + more
            if name in ("search_in_files", "search_files"):
                return await self._search(args)
            if name == "replace_in_file":
                path = clean_path(args["path"])
                f = await self._get(path)
                if not f or f["kind"] != "text":
                    return f"ERRO: arquivo de texto '{path}' não existe. Use create_file para arquivos novos."
                old, new = args.get("old_text") or "", args.get("new_text") or ""
                if not old:
                    return "ERRO: old_text vazio."
                count = f["content"].count(old)
                if count == 0:
                    return "ERRO: old_text não encontrado (o arquivo não foi alterado). Leia o trecho atual com read_file e tente novamente com o texto exato."
                if count > 1:
                    return f"ERRO: old_text aparece {count} vezes; inclua mais contexto para torná-lo único. Arquivo não alterado."
                content = f["content"].replace(old, new, 1)
                await self._write(path, f, content)
                await self._card(path, "edit", old, new)
                return f"OK: {path} atualizado."
            if name == "create_file":
                path = clean_path(args["path"])
                if not path:
                    return "ERRO: caminho vazio."
                content = args.get("content") or ""
                f = await self._get(path)
                if f and f["kind"] != "text":
                    return f"ERRO: '{path}' é um arquivo binário (imagem/asset); não pode ser sobrescrito com texto."
                if f and not content.strip():
                    return f"ERRO: conteúdo vazio para '{path}'. Para remover o arquivo use delete_file."
                await self._write(path, f, content)
                await self._card(path, "edit" if f else "create", f.get("content") if f and f["kind"] == "text" else "", content)
                return f"OK: {path} {'reescrito' if f else 'criado'}."
            if name == "delete_file":
                path = clean_path(args["path"])
                f = await self._get(path)
                if not f:
                    return f"ERRO: '{path}' não existe."
                await db.files.delete_one({"project_id": self.pid, "path": path})
                self._track(path, f, None)
                await self._card(path, "delete", f.get("content") if f["kind"] == "text" else "", "")
                return f"OK: {path} apagado."
            if name == "move_or_copy_file":
                return await self._move_copy(args)
            if name == "clean_external_links":
                return await self._clean_links(args)
            if name == "extract_zip":
                return await self._extract_zip(args)
            if name == "html_to_js_module":
                return await self._html_to_js_module(args)
            return f"ERRO: ferramenta desconhecida {name}"
        except (KeyError, ValueError) as e:
            return f"ERRO: argumentos inválidos ({e})."

    async def build_messages(self, prompt: str) -> list:
        history = list(reversed(await db.messages.find({"project_id": self.pid, "archived": {"$ne": True}}, {"_id": 0}).sort("created_at", -1).to_list(HISTORY_LIMIT)))
        p = await db.projects.find_one({"id": self.pid}, {"_id": 0, "env_enc": 1}) or {}
        env_names = []
        if p.get("env_enc"):
            try:
                env_names = list(json.loads(decrypt(p["env_enc"])))
            except Exception:
                env_names = []
        env_note = ("\n\nVARIÁVEIS DE AMBIENTE DO PROJETO (valores definidos pelo usuário no painel .env, injetados na prévia como process.env.NOME; "
                    "use-as pelo nome, nunca escreva os valores no código): " + ", ".join(env_names)) if env_names else ""
        done = [f"{c['path']} ({c.get('op', 'edit')})" for m in history if m["role"] == "assistant" for c in (m.get("changes") or [])[:20]]
        done_note = ("\n\nALTERAÇÕES JÁ FEITAS EM TURNOS ANTERIORES (registro da plataforma, não imite este formato): " + ", ".join(done[-40:])) if done else ""
        msgs = [{"role": "system", "content": SYSTEM_PROMPT + TOOL_RULE + env_note + done_note + "\n\nMAPA ATUAL DO PROJETO:\n" + await project_map(self.pid)}]
        current = history and history[-1]["role"] == "user" and history[-1].get("content") == prompt
        for i, m in enumerate(history):
            content = m.get("content") or ""
            if m["role"] == "assistant":
                content = FAKE_LOG.sub("", content).strip()[:2000]
            is_last = current and i == len(history) - 1
            if not is_last:
                content = content[:6000]
            if m["role"] == "user":
                content += attachments_note(m.get("attachments") or [])
            if content.strip():
                msgs.append({"role": m["role"], "content": content})
        if not current:
            msgs.append({"role": "user", "content": prompt})
        return msgs

    async def call_model(self, client, headers, model, messages):
        payload = {"model": model, "messages": messages, "tools": TOOLS, "tool_choice": "required" if self.force_tools else "auto",
                   "stream": True, "max_tokens": 8000, "temperature": 0.2}
        text, calls, usage, gen_id, finish = "", {}, None, None, None
        self.stream_buf = ""
        async with client.stream("POST", f"{OPENROUTER_BASE}/chat/completions", headers=headers, json=payload) as r:
            if r.is_error:
                body = (await r.aread()).decode(errors="replace")
                try:
                    body = json.loads(body).get("error", {}).get("message", body)
                except Exception:
                    pass
                if r.status_code in RETRYABLE_STATUS:
                    raise ModelUnavailable(r.status_code, str(body)[:300])
                raise RuntimeError(f"OpenRouter {r.status_code}: {str(body)[:400]}")
            async for line in r.aiter_lines():
                if not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if raw == "[DONE]":
                    break
                try:
                    chunk = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if chunk.get("error"):
                    err = chunk["error"]
                    code = err.get("code") if isinstance(err, dict) else None
                    if not text and not calls and code in RETRYABLE_STATUS:
                        raise ModelUnavailable(code, str(err.get("message", err))[:300])
                    raise RuntimeError(f"OpenRouter: {err.get('message', err) if isinstance(err, dict) else err}")
                gen_id = chunk.get("id", gen_id)
                if chunk.get("usage"):
                    usage = chunk["usage"]
                choice = (chunk.get("choices") or [{}])[0]
                finish = choice.get("finish_reason") or finish
                delta = choice.get("delta") or {}
                if delta.get("content"):
                    text += delta["content"]
                    self.stream_buf = text
                    await self.emit({"type": "token", "text": delta["content"]})
                for tc in delta.get("tool_calls") or []:
                    slot = calls.setdefault(tc.get("index", 0), {"id": None, "name": "", "arguments": ""})
                    if tc.get("id"):
                        slot["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        slot["name"] += fn["name"]
                    if fn.get("arguments"):
                        slot["arguments"] += fn["arguments"]
        return text, [calls[i] for i in sorted(calls)], usage, gen_id, finish

    async def record_usage(self, model, usage, gen_id, key_source):
        if not usage:
            return
        cost = float(usage.get("cost") or 0)
        self.cost += cost
        self.tokens += int(usage.get("total_tokens") or 0)
        await db.usage.insert_one({"id": new_id(), "user_id": self.member["user_id"], "project_id": self.pid,
            "model": model, "generation_id": gen_id, "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"), "total_tokens": usage.get("total_tokens"),
            "cost": cost, "key_source": key_source, "created_at": now()})

    async def call_with_fallback(self, client, headers, messages):
        """Call the current model; on 429/provider-unavailable switch to the next enabled model."""
        while True:
            try:
                return await self.call_model(client, headers, self.model, messages)
            except ModelUnavailable as e:
                if self.stream_buf or not self.fallbacks:
                    raise RuntimeError(f"OpenRouter {e.status}: {e.detail}")
                nxt = self.fallbacks.pop(0)
                msg = f"Modelo {self.model} indisponível ({e.status}). Continuando com {nxt}."
                logger.warning(msg)
                await self.emit({"type": "fallback", "from": self.model, "to": nxt, "message": msg})
                self.model = nxt

    async def run(self, prompt: str, model: str, api_key: str, key_source: str, fallbacks=None):
        self.model = model
        self.fallbacks = list(fallbacks or [])
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
                   "HTTP-Referer": os.environ.get("APP_PUBLIC_URL", "https://donas.app"), "X-Title": "Donas Build apps with ai"}
        error = None
        try:
            messages = await self.build_messages(prompt)
            async with httpx.AsyncClient(timeout=httpx.Timeout(connect=20, read=180, write=60, pool=20)) as client:
                for _ in range(MAX_STEPS):
                    text, calls, usage, gen_id, finish = await self.call_with_fallback(client, headers, messages)
                    self.stream_buf = ""
                    await self.record_usage(self.model, usage, gen_id, key_source)
                    if text:
                        self.text += text + "\n"
                    if finish == "length":
                        await self.warn("A resposta do modelo foi cortada no limite de tokens. "
                                        + ("Pedi para ele refazer em partes menores." if calls else "Envie 'continue' para ele seguir."))
                    if not calls and not self.change_cards and fake_claim(text) and self.nudges < MAX_NUDGES:
                        self.nudges += 1
                        self.text = self.text[: len(self.text) - len(text) - 1] if text else self.text
                        await self.warn("A IA descreveu alterações sem usar ferramentas (nada foi salvo). Pedi para ela fazer de verdade.")
                        messages.append({"role": "assistant", "content": text})
                        messages.append({"role": "user", "content": NUDGE})
                        self.force_tools = True
                        continue
                    self.force_tools = False
                    if not calls:
                        if not self.change_cards and fake_claim(text):
                            self.text = self.text[: len(self.text) - len(text) - 1] if text else self.text
                            await self.warn("A IA afirmou ter alterado arquivos, mas não chamou nenhuma ferramenta: nenhum arquivo foi modificado. Tente 'Nova conversa' ou outro modelo.")
                        break
                    messages.append({"role": "assistant", "content": text or None, "tool_calls": [
                        {"id": c["id"] or f"call_{i}", "type": "function", "function": {"name": c["name"], "arguments": c["arguments"] or "{}"}}
                        for i, c in enumerate(calls)]})
                    stop = None
                    for i, c in enumerate(calls):
                        try:
                            args = json.loads(c["arguments"] or "{}")
                        except json.JSONDecodeError:
                            args, result = None, ("ERRO: argumentos JSON inválidos — sua resposta foi cortada pelo limite de tokens. Nada foi salvo. "
                                                  "Não envie arquivos grandes inteiros: use replace_in_file com trechos pequenos, ou move_or_copy_file / clean_external_links para arquivos grandes.")
                        await self.emit({"type": "tool", "name": c["name"], "path": (args or {}).get("path") or (args or {}).get("source") or (args or {}).get("directory") or (args or {}).get("query")})
                        if c["name"] not in TOOL_NAMES:
                            self.unknown_streak += 1
                            result = (f"ERRO: a ferramenta '{c['name']}' não existe. Você NÃO tem terminal/shell. "
                                      f"Use somente: {', '.join(sorted(TOOL_NAMES))}.")
                            if self.unknown_streak >= 2:
                                stop = c["name"]
                        elif args is not None:
                            self.unknown_streak = 0
                            result = await self.run_tool(c["name"], args)
                        if result.startswith("ERRO"):
                            await self.emit({"type": "tool_error", "name": c["name"], "message": result[:200]})
                        messages.append({"role": "tool", "tool_call_id": c["id"] or f"call_{i}", "content": result[:20000]})
                    if stop:
                        note = (f"\n(Interrompido: o modelo tentou usar a ferramenta inexistente '{stop}' 2 vezes seguidas. "
                                "Ele não tem terminal; reformule o pedido ou troque de modelo.)")
                        self.text += note
                        await self.emit({"type": "token", "text": note})
                        await self.emit({"type": "tool_error", "name": stop, "message": "ferramenta inexistente 2x seguidas — execução interrompida"})
                        break
                else:
                    self.text += "\n(Limite de passos atingido — envie 'continue' para seguir.)"
        except asyncio.CancelledError:
            if self.stream_buf:
                self.text += self.stream_buf + "\n"
            error = "Execução interrompida (botão Parar, conexão caiu ou tempo limite). O que já foi feito ficou salvo."
            raise
        except Exception as e:
            logger.exception("agent error")
            error = friendly_error(e)
            await self.emit({"type": "error", "message": error})
        finally:
            if not error and not self.text.strip() and not self.change_cards and not self.warnings:
                error = "O modelo não retornou nenhuma resposta (pode ter batido no limite de tokens). Tente de novo, divida o pedido ou troque de modelo."
            await asyncio.shield(self._finish(prompt, self.model, error))

    async def _finish(self, prompt, model, error):
        version = await record_version(self.pid, prompt, self.changes, "ai")
        msg = {"id": new_id(), "project_id": self.pid, "role": "assistant", "content": self.text.strip(),
               "changes": self.change_cards, "error": error, "warnings": self.warnings, "model": model, "cost": self.cost,
               "tokens": self.tokens, "version": version, "created_at": now()}
        await db.messages.insert_one(msg)
        msg.pop("_id", None)
        await self.emit({"type": "done", "message": msg})


def friendly_error(e: Exception) -> str:
    msg = str(e)
    low = msg.lower()
    if "context" in low and ("length" in low or "window" in low or "too long" in low or "maximum" in low):
        return f"O pedido ficou maior que o limite de contexto do modelo. Divida o pedido ou use um modelo com mais contexto. ({msg[:200]})"
    if isinstance(e, httpx.TimeoutException):
        return "A OpenRouter demorou demais para responder (tempo esgotado). Tente de novo ou peça uma mudança menor."
    if "402" in msg or "credits" in low:
        return f"Sem saldo na OpenRouter para este modelo. ({msg[:200]})"
    return msg or e.__class__.__name__


async def resolve_key(member: dict) -> tuple[str, str]:
    full = await db.users.find_one({"user_id": member["user_id"]}, {"_id": 0, "openrouter_key_enc": 1})
    if full and full.get("openrouter_key_enc"):
        return decrypt(full["openrouter_key_enc"]), "user"
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        raise ValueError("A plataforma ainda não tem uma chave OpenRouter configurada. Adicione a sua em Configurações.")
    settings = await get_settings()
    today = datetime.now(timezone.utc).date().isoformat()
    spent = await db.usage.aggregate([
        {"$match": {"user_id": member["user_id"], "key_source": "platform", "created_at": {"$gte": today}}},
        {"$group": {"_id": None, "c": {"$sum": "$cost"}}}]).to_list(1)
    if spent and spent[0]["c"] >= float(settings["daily_limit_usd"]):
        raise ValueError(f"Limite diário de US$ {settings['daily_limit_usd']:.2f} atingido. Volte amanhã ou use sua própria chave OpenRouter em Configurações.")
    return key, "platform"
