# Deploy do Donas Build apps with ai na sua VPS (Linux + Docker + Nginx)

Guia para rodar o Donas 100% na sua máquina, sem depender do Emergent. O login
é por **e-mail e senha do administrador** (modo `selfhost`).

## 1. Pré-requisitos na VPS
- Uma VPS Linux (Ubuntu 22.04+ recomendado) com acesso root/sudo.
- Docker e Docker Compose:
  ```bash
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker $USER   # saia e entre de novo
  ```
- (Opcional) um domínio apontando para o IP da VPS, para usar HTTPS.

## 2. Suba o código
Envie a pasta do projeto para a VPS (git clone, scp ou rsync). A raiz deve ter
`docker-compose.yml`, `nginx.conf`, `backend/` e `frontend/`.

## 3. Configure os segredos
```bash
cp .env.example .env
cp backend/.env.example backend/.env
```
Edite **`.env`** (raiz):
- `PUBLIC_ORIGIN` = o endereço público, ex.: `http://203.0.113.10` ou `https://donas.seudominio.com`.
- `MONGO_ROOT_PASSWORD` = `openssl rand -hex 24` (o banco principal passa a exigir senha; o código dos projetos em prévia não tem acesso a ela).

Edite **`backend/.env`**:
- `ADMIN_EMAIL` = seu e-mail (será o login admin).
- `ADMIN_PASSWORD` = uma senha forte.
- `JWT_SECRET` = `openssl rand -hex 32`
- `FORJA_ENCRYPTION_KEY` = `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- `OPENROUTER_API_KEY` = sua chave da OpenRouter (o "cérebro" da IA). Pegue em https://openrouter.ai/keys
- `DEFAULT_DAILY_LIMIT_USD` = limite diário em dólares por usuário (ex.: `2`).

> `MONGO_URL`, `DB_NAME`, `AUTH_MODE` e `CORS_ORIGINS` já são definidos pelo
> `docker-compose.yml`; não precisa mexer.

## 4. Suba tudo
```bash
docker compose up -d --build
```
Isso sobe 4 contêineres: **mongodb**, **backend** (FastAPI), **frontend** (React
compilado) e **nginx** (porta 80/443). O Mongo guarda os dados num volume
(`mongo_data`), então eles sobrevivem a reinícios.

Acompanhe os logs:
```bash
docker compose logs -f backend
```

### Prévia full-stack (back-end real dos projetos)
O contêiner do backend tem Python e Node/Yarn. Quando um projeto tem `backend/server.py`,
o Donas cria um ambiente virtual em `/tmp/donas_previews/{id}`, instala o `requirements.txt`
e roda `uvicorn server:app` numa porta livre, com um MongoDB só para prévias (com senha e
um usuário por projeto, banco `preview_{id}`). Cada projeto roda com um usuário Linux
próprio, sem privilégios: não lê o `.env` da plataforma nem os arquivos de outros projetos.
Processos ociosos por 30 min são encerrados, e o back-end reinicia sozinho quando os
arquivos em `backend/` ou as variáveis do projeto mudam.

## 5. Acesse
Abra `PUBLIC_ORIGIN` no navegador. Vai aparecer a tela de login do Donas: entre
com o `ADMIN_EMAIL` e `ADMIN_PASSWORD` que você definiu.

## 6. HTTPS (recomendado)
Com um domínio apontando para a VPS, gere um certificado (ex.: certbot) e coloque
`fullchain.pem` e `privkey.pem` na pasta `certs/` da raiz. Depois descomente o
bloco `server { listen 443 ssl; ... }` no `nginx.conf`, ajuste `server_name` e o
redirecionamento da porta 80 para 443, e rode `docker compose restart nginx`.
Lembre de usar `https://...` em `PUBLIC_ORIGIN` e refazer o build do frontend
(`docker compose up -d --build frontend`), pois a URL do backend é embutida na
compilação do React.

## 7. Comandos úteis
```bash
docker compose ps                 # status
docker compose restart backend    # reiniciar o backend
docker compose down               # parar tudo (dados ficam no volume)
docker compose up -d --build      # aplicar mudanças de código
```

### Backup do banco
```bash
docker compose exec mongodb mongodump --archive=/data/db/backup.archive --db donas
docker compose cp mongodb:/data/db/backup.archive ./backup.archive
```

## Observações
- **Modo de login:** na VPS, `AUTH_MODE=selfhost` (e-mail/senha do admin). Só o
  `ADMIN_EMAIL` entra; não há cadastro aberto nem Google. O login tem proteção
  contra força bruta (5 tentativas por minuto por IP).
- **Uploads/imagens:** ficam em disco no contêiner do backend (`STORAGE_BACKEND=local`,
  volume `backend_storage`), sem depender do Emergent.
- **Prévia:** a prévia ao vivo e o Link Preview público mostram o front-end
  (React) dos projetos. O back-end Python gerado é salvo e sincronizado com o
  GitHub, mas não roda dentro da plataforma.
- **Trocar a senha do admin:** edite `ADMIN_PASSWORD` em `backend/.env` e rode
  `docker compose restart backend`.
