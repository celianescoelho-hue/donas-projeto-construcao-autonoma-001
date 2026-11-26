# Donas Build apps with ai — PRD

## Original problem
"posso criar com uma chave api minha? queria criar com minha IA openrouter" → AI site/app builder (Emergent-style) whose brain is OpenRouter. Later: rebrand to "Donas Build apps with ai" with a user-supplied hero image, Desktop/Mobile preview, terminal/logs, a strict security layer, a fix for the unknown-tool loop, and GitHub auto-import.

## Architecture
- Backend: FastAPI (server.py routes, core.py auth/roles/encryption/storage/rate-limit, agent.py OpenRouter tool agent, github_sync.py), MongoDB (users, projects, files, messages, versions, usage, settings), Emergent Object Storage for images.
- Frontend: React + shadcn. Pages: Landing, Dashboard, Workspace (chat | tree+editor | preview+terminal), Settings, Admin. In-browser preview built with @babel/standalone + esm.sh import maps inside a sandboxed iframe (no allow-same-origin).
- Auth: Emergent-managed Clerk (Google). ADMIN_EMAIL=celiane.scoelho@professor.educacao.pe.gov.br, ya0934037096@gmail.com.

## Implemented (2026-06)
- Agent with tools list/read/search/replace_in_file/create_file/delete_file, SSE streaming, change cards + diff, versions per turn, restore, zip.
- Upload with summaries; GitHub import (zipball, filters, 2000-file cap, 200 MB cap) on new or empty projects; push to an existing or new repo.
- Per-project model selector (qwen3-coder-next / qwen3-coder default), user's own OpenRouter key (Fernet-encrypted), platform key with a daily limit (US$2).
- Admin: overview costs (platform vs user key), users (role, block), models, limit, usage log.
- Rebrand: Donas, purple/gold palette, hero image, footer, title "Donas | Build apps with AI", purple favicon.
- Preview Desktop/Celular (375x812 phone frame), terminal/logs panel (agent + preview console).
- Security: encrypted keys never returned, server-side role checks, rate limits (per-user + per-IP), sandboxed iframe, security headers, secure-codegen rules in the system prompt (bcrypt, JWT, Pydantic, .env).
- Models: qwen3-coder-next (default), qwen3-coder, deepseek-chat-v3-0324 "DeepSeek V3 (Cirúrgico)" (seeded once).
- Fixes: unknown-tool guard (stop after 2), no-shell prompt, chat/import locks, atomic version numbers, '..' → 400.

- Chat attachments (clip, drag-and-drop, large pastes → files in uploads/, AI gets path + metadata), PDF/ZIP support; server-side tools move_or_copy_file, clean_external_links, extract_zip; read_file token budget; visible token-limit/failure errors.
- search_in_files (text/regex, file:line:col), preview error banner + "Corrigir com IA", rollback "Voltar para antes" per version + "Desfazer" on chat messages, per-project .env (encrypted, injected as process.env), Inspect element picker → chat reference (file:line via data-donas-src).
- Public Link Preview /p/{id}/live (no login, front-end only, toggle in share popover + project settings, QR code, auto-refresh 10s).

- Self-host deploy (VPS): AUTH_MODE env switch — "clerk" (Emergent preview, Google) or "selfhost" (own JWT, ADMIN_EMAIL+ADMIN_PASSWORD, single admin). backend/self_auth.py (/api/auth/mode, /api/auth/login), core require_user branch, frontend AuthBridge (lib/authContext.js) so useApi works in both; App.js branches ClerkApp/SelfHostApp; SelfHostAuthProvider + login screen. Deploy files at repo root: docker-compose.yml (mongo+backend+frontend+nginx), nginx.conf, DEPLOY_VPS.md, backend/Dockerfile, frontend/Dockerfile, .env.example files.

## Backlog
- P1: run the generated Python backend in an isolated sandbox for a full-stack preview; publish to a public link.
- P1: GitHub pull requests instead of direct pushes; real-PAT import/push E2E test.
- P2: self-testing agent, templates, paid plans.

## 2026-06 — Prévia full-stack (Fase 2)
- runner.py: back-end real dos projetos (venv + pip + uvicorn em porta livre) com MongoDB próprio da prévia (--auth, usuário por projeto, banco preview_{id}).
- Isolamento: uid Linux único por projeto (setpriv), pasta 0700, env mínimo sem segredos, .env/credenciais da plataforma 0600/0700, trava de rede em Python (sitecustomize).
- Proxy reverso: /api/projects/{id}/preview/proxy/* (token da prévia) e /api/public/projects/{id}/preview/proxy/*; o fetch/XHR da prévia é reescrito.
- Ociosidade de 30 min pausa (mantém venv e dados); excluir projeto remove tudo; reinicia sozinho quando backend/ ou as variáveis mudam.
- Live Preview: sub-rotas /p/{id}/live/rota e #/rota; recarrega quando o back-end sobe.
- Docker: Node/Yarn + Python no backend; Mongo da plataforma com senha (MONGO_ROOT_PASSWORD).
- Limitação na prévia Emergent: sem iptables/unshare, e o Mongo da plataforma não tem senha, então a trava de rede pode ser contornada (python -S). Na VPS, o Mongo com senha fecha essa brecha.

## 2026-11 — Velocidade e estabilidade
- Back-end da prévia só inicia no clique "Rodar back-end"; ao abrir, só consulta o status; reinicia nas edições apenas se já estava iniciado. O iframe do front nunca some. Com o back-end parado, chamadas /api recebem 503 "Back-end parado".
- Fallback de modelo: 429/502/503/529 da OpenRouter → próximo modelo liberado (evento "fallback" no terminal); a mensagem salva registra o modelo que respondeu. tests/test_model_fallback.py.
- create_file sobrescreve arquivos de qualquer tamanho; bloqueia conteúdo vazio em arquivo existente e sobrescrita de binário.
