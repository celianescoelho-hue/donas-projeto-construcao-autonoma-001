import os
import json
import fnmatch
import asyncio
from datetime import datetime, timezone

import httpx

from core import (db, now, new_id, decrypt, get_settings, unified_diff, record_version, file_snapshot,
                  OPENROUTER_BASE, logger)

MAX_STEPS = 30
SMALL_FILE_LINES = 60

SYSTEM_PROMPT = """Você é o Donas (Donas Build apps with ai), um engenheiro full-stack sênior que constrói sites e apps completos.
Padrão de projeto (siga sempre, a menos que o projeto importado use outra estrutura — então respeite a existente):
- frontend/  → React (JS/JSX). Entrada em frontend/src/index.js que renderiza <App/> em #root. Componentes em frontend/src/components, páginas em frontend/src/pages. Estilos em CSS (importe com import './x.css') ou classes Tailwind (Tailwind já está disponível na prévia). Inclua frontend/package.json.
- backend/   → Python FastAPI (backend/server.py) com MongoDB via motor (AsyncIOMotorClient), lendo MONGO_URL e DB_NAME do ambiente; backend/requirements.txt (fastapi, uvicorn, motor, python-dotenv, pydantic) e backend/.env.example (MONGO_URL, DB_NAME, CORS_ORIGINS). Todas as rotas com prefixo /api. Nunca retorne o _id do Mongo; use um campo id (uuid) próprio. O front lê a URL do back de process.env.REACT_APP_BACKEND_URL.
- README.md  → como rodar.
A prévia ao vivo roda apenas o front-end React no navegador (pacotes npm vêm de esm.sh). Faça o front funcionar com dados de exemplo quando o back-end não estiver disponível.

SEGURANÇA OBRIGATÓRIA (sempre, em todo back-end gerado):
- Senhas de usuários SEMPRE com hash bcrypt (passlib[bcrypt] ou bcrypt); nunca salvar nem retornar senha em texto puro.
- Autenticação por JWT (PyJWT) com segredo JWT_SECRET vindo do .env e expiração; rotas privadas protegidas por uma dependência FastAPI (Depends) que valida o token. Papéis/admin verificados no servidor.
- Toda entrada validada com modelos Pydantic (tipos, tamanhos, EmailStr, Field(min_length/max_length)); nunca passar o corpo da requisição direto para o banco ($set: body).
- Segredos (MONGO_URL, JWT_SECRET, chaves de API) apenas em variáveis de ambiente: lidos com os.environ, listados em backend/.env.example sem valores reais; nunca colocar chaves no front-end nem no código.
- CORS restrito por CORS_ORIGINS do .env, rate limit simples em login/cadastro, e mensagens de erro sem detalhes internos.

FERRAMENTAS — trabalhe como um agente:
- Use list_files / read_file / search_files para entender o projeto antes de editar arquivos existentes. Leia só os trechos necessários (start_line/end_line).
- Para alterar um arquivo EXISTENTE use replace_in_file enviando APENAS o trecho antigo (old_text, exato, único no arquivo, com contexto suficiente) e o novo. Nunca reescreva um arquivo existente inteiro (create_file só é permitido para arquivos novos ou com até 60 linhas).
- Se uma substituição falhar, leia o trecho atual com read_file e tente de novo.
- Crie vários arquivos pequenos e bem organizados. Não repita o código dos arquivos na resposta de texto.
- Arquivos enviados pelo usuário aparecem no mapa com um resumo; leia trechos quando precisar de detalhes. Imagens enviadas podem ser usadas pelo caminho (ex.: import logo from './assets/logo.png' ou '/logo.png' se estiver em frontend/public).
Ao final, responda em português com um resumo curto (3-6 linhas) do que foi feito e próximos passos."""

TOOLS = [
    {"type": "function", "function": {"name": "list_files", "description": "Lista arquivos do projeto (opcionalmente dentro de uma pasta).",
        "parameters": {"type": "object", "properties": {"directory": {"type": "string", "description": "Pasta, ex: frontend/src. Vazio = tudo."}}}}},
    {"type": "function", "function": {"name": "read_file", "description": "Lê um arquivo inteiro ou um intervalo de linhas (numeradas a partir de 1).",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "search_files", "description": "Busca um texto (sem diferenciar maiúsculas) nos arquivos. Retorna caminho:linha: trecho.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "path_glob": {"type": "string", "description": "Filtro opcional, ex: frontend/src/*.jsx"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "replace_in_file", "description": "Substitui um trecho exato e único de um arquivo existente por um novo trecho.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}}},
    {"type": "function", "function": {"name": "create_file", "description": "Cria um arquivo novo (ou reescreve um arquivo existente de até 60 linhas).",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}},
    {"type": "function", "function": {"name": "delete_file", "description": "Apaga um arquivo do projeto.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
]


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

    async def emit(self, event: dict):
        await self.q.put(event)

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
                    return f"Arquivo binário. {f.get('summary') or ''}"
                lines = f["content"].split("\n")
                s = max(1, int(args.get("start_line") or 1))
                e = min(len(lines), int(args.get("end_line") or len(lines)))
                if e - s > 600:
                    e = s + 600
                body = "\n".join(f"{i}: {lines[i - 1]}" for i in range(s, e + 1))
                return f"{path} (linhas {s}-{e} de {len(lines)})\n{body}"
            if name == "search_files":
                query = (args.get("query") or "").lower()
                glob = args.get("path_glob")
                out = []
                async for f in db.files.find({"project_id": self.pid, "kind": "text"}, {"_id": 0, "path": 1, "content": 1}):
                    if glob and not fnmatch.fnmatch(f["path"], glob):
                        continue
                    for i, line in enumerate(f["content"].split("\n"), 1):
                        if query in line.lower():
                            out.append(f"{f['path']}:{i}: {line.strip()[:160]}")
                            if len(out) >= 80:
                                return "\n".join(out) + "\n(limite de 80 resultados)"
                return "\n".join(out) or "Nenhum resultado."
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
                if f and f["kind"] == "text" and f["content"].count("\n") + 1 > SMALL_FILE_LINES:
                    return f"ERRO: '{path}' já existe com mais de {SMALL_FILE_LINES} linhas. Use replace_in_file para editar trechos."
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
            return f"ERRO: ferramenta desconhecida {name}"
        except (KeyError, ValueError) as e:
            return f"ERRO: argumentos inválidos ({e})."

    async def build_messages(self, prompt: str) -> list:
        history = await db.messages.find({"project_id": self.pid}, {"_id": 0}).sort("created_at", -1).to_list(16)
        msgs = [{"role": "system", "content": SYSTEM_PROMPT + "\n\nMAPA ATUAL DO PROJETO:\n" + await project_map(self.pid)}]
        for m in reversed(history):
            content = m.get("content") or ""
            if m["role"] == "assistant" and m.get("changes"):
                content += "\n[Alterações: " + ", ".join(f"{c['path']} (+{c['added']}/-{c['removed']})" for c in m["changes"][:40]) + "]"
            if content.strip():
                msgs.append({"role": m["role"], "content": content[:6000]})
        msgs.append({"role": "user", "content": prompt})
        return msgs

    async def call_model(self, client, headers, model, messages):
        payload = {"model": model, "messages": messages, "tools": TOOLS, "tool_choice": "auto",
                   "stream": True, "max_tokens": 8000, "temperature": 0.2}
        text, calls, usage, gen_id = "", {}, None, None
        async with client.stream("POST", f"{OPENROUTER_BASE}/chat/completions", headers=headers, json=payload) as r:
            if r.is_error:
                body = (await r.aread()).decode(errors="replace")
                try:
                    body = json.loads(body).get("error", {}).get("message", body)
                except Exception:
                    pass
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
                    raise RuntimeError(f"OpenRouter: {chunk['error'].get('message', chunk['error'])}")
                gen_id = chunk.get("id", gen_id)
                if chunk.get("usage"):
                    usage = chunk["usage"]
                delta = ((chunk.get("choices") or [{}])[0].get("delta") or {})
                if delta.get("content"):
                    text += delta["content"]
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
        return text, [calls[i] for i in sorted(calls)], usage, gen_id

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

    async def run(self, prompt: str, model: str, api_key: str, key_source: str):
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
                   "HTTP-Referer": os.environ.get("APP_PUBLIC_URL", "https://donas.app"), "X-Title": "Donas Build apps with ai"}
        error = None
        try:
            messages = await self.build_messages(prompt)
            async with httpx.AsyncClient(timeout=httpx.Timeout(connect=20, read=180, write=60, pool=20)) as client:
                for _ in range(MAX_STEPS):
                    text, calls, usage, gen_id = await self.call_model(client, headers, model, messages)
                    await self.record_usage(model, usage, gen_id, key_source)
                    if text:
                        self.text += text + "\n"
                    if not calls:
                        break
                    messages.append({"role": "assistant", "content": text or None, "tool_calls": [
                        {"id": c["id"] or f"call_{i}", "type": "function", "function": {"name": c["name"], "arguments": c["arguments"] or "{}"}}
                        for i, c in enumerate(calls)]})
                    for i, c in enumerate(calls):
                        try:
                            args = json.loads(c["arguments"] or "{}")
                        except json.JSONDecodeError:
                            args, result = None, "ERRO: argumentos JSON inválidos (talvez a resposta foi cortada). Envie arquivos menores ou edite por trechos."
                        await self.emit({"type": "tool", "name": c["name"], "path": (args or {}).get("path") or (args or {}).get("directory") or (args or {}).get("query")})
                        if args is not None:
                            result = await self.run_tool(c["name"], args)
                        if result.startswith("ERRO"):
                            await self.emit({"type": "tool_error", "name": c["name"], "message": result[:200]})
                        messages.append({"role": "tool", "tool_call_id": c["id"] or f"call_{i}", "content": result[:20000]})
                else:
                    self.text += "\n(Limite de passos atingido — envie 'continue' para seguir.)"
        except Exception as e:
            logger.exception("agent error")
            error = str(e)
            await self.emit({"type": "error", "message": error})
        finally:
            version = await record_version(self.pid, prompt, self.changes, "ai")
            msg = {"id": new_id(), "project_id": self.pid, "role": "assistant", "content": self.text.strip(),
                   "changes": self.change_cards, "error": error, "model": model, "cost": self.cost,
                   "tokens": self.tokens, "version": version, "created_at": now()}
            await db.messages.insert_one(msg)
            msg.pop("_id", None)
            await self.emit({"type": "done", "message": msg})
            await self.q.put(None)


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
