# RH Backend + Auth Service (FastAPI)

Um único projeto FastAPI com duas partes:

- **Auth** (`app/auth`): login Google, RBAC por aplicação, Authorization Code de uso único,
  `POST /oauth/token` com `client_secret`, JWT RS256 e `/.well-known/jwks.json`.
- **RH** (`app/rh`): rotas protegidas por JWT que leem o SIP (Firebird, somente leitura, empresa 001).

## Subir

```bash
uv sync                                              # cria o .venv e instala tudo
cp .env.example .env                                 # preencher (Windows: copy)
uv run python -m scripts.gerar_chaves                # par RS256 em keys/
createdb rh_auth                                     # banco PostgreSQL do serviço
uv run python -m scripts.seed voce@gmail.com "Seu Nome"   # imprime RH_CLIENT_SECRET -> .env
uv run uvicorn app.main:app --reload
```

No Google Cloud, autorize o redirect `http://localhost:8000/auth/google/callback`.

Teste no navegador: `http://localhost:8000/rh/login` → Google → `/rh/me`.
Documentação interativa em `/docs`. Testes: `uv run pytest -q`.

## Rotas

| Rota | Função |
|---|---|
| `GET /auth/google?client_id&redirect_uri&state` | valida o cliente e envia ao Google |
| `GET /auth/google/callback` | identidade → acesso → código → volta ao cliente |
| `POST /oauth/token` | código + segredo → JWT RS256 (15 min) |
| `GET /.well-known/jwks.json` | chave pública |
| `GET /rh/login`, `/rh/callback`, `/rh/logout`, `/rh/me` | login do RH (cookie HttpOnly) |
| `GET /rh/servidores`, `/rh/servidores/{registro}`, `/rh/servidores/{registro}/dependentes` | dados do SIP |

Outros usuários: `uv run python -m scripts.seed fulano@gmail.com "Fulano" rh`.
Quem não está pré-cadastrado recebe `access_denied`.
