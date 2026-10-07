# RH Backend + Auth Service (FastAPI)

Um único projeto FastAPI com duas partes:

- **Auth** (`app/auth`): login Google, RBAC por aplicação, Authorization Code de uso único,
  `POST /oauth/token` com `client_secret`, JWT RS256 e `/.well-known/jwks.json`.
- **RH** (`app/rh`): rotas protegidas por JWT que leem o SIP (Firebird, somente leitura, empresa 001).

## Subir (Docker Compose: api + postgres + firebird)

```bash
cp .env.example .env                                  # preencher
docker compose up -d --build
docker compose exec api python -m scripts.gerar_chaves
docker compose exec api python -m scripts.seed voce@gmail.com "Seu Nome"
# copie RH_CLIENT_SECRET=... para o .env e recarregue:
docker compose up -d
```

No Google Cloud, autorize o redirect `http://localhost:8000/auth/google/callback`.

Teste no navegador: `http://localhost:8000/rh/login` → Google → `/rh/me`.
Documentação interativa em `/docs`. Logs: `docker compose logs -f api`.

Testes (fora do Docker, sem Google nem Firebird): `uv sync && uv run pytest -q`.

O arquivo do SIP na máquina é definido por `SIP_DB_HOST_FILE` no `.env`
(padrão: `/media/ademar/Novo volume/SIP_ANALISE_2.FDB`). O disco precisa estar montado
antes do `docker compose up`.

Não suba este compose junto com o do projeto anterior: dois servidores Firebird
não devem abrir o mesmo arquivo `.FDB` ao mesmo tempo.

## Rotas

| Rota | Função |
|---|---|
| `GET /auth/google?client_id&redirect_uri&state` | valida o cliente e envia ao Google |
| `GET /auth/google/callback` | identidade → acesso → código → volta ao cliente |
| `POST /oauth/token` | código + segredo → JWT RS256 (15 min) |
| `GET /.well-known/jwks.json` | chave pública |
| `GET /rh/login`, `/rh/callback`, `/rh/logout`, `/rh/me` | login do RH (cookie HttpOnly) |
| `GET /rh/servidores`, `/rh/servidores/{registro}`, `/rh/servidores/{registro}/dependentes` | dados do SIP |

Outros usuários: `docker compose exec api python -m scripts.seed fulano@gmail.com "Fulano" rh`.
Quem não está pré-cadastrado recebe `access_denied`.
Nova dependência: `uv add pacote` e depois `docker compose up -d --build`.
