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

O usuário `SIP_DB_USER` vive dentro do contêiner Firebird. Se o contêiner for recriado,
a API recria esse usuário sozinha na primeira consulta, usando `SIP_DB_SYSDBA_PASSWORD`.

Não suba este compose junto com o do projeto anterior: dois servidores Firebird
não devem abrir o mesmo arquivo `.FDB` ao mesmo tempo.

## Rotas

| Rota | Função | Permissão |
|---|---|---|
| `GET /auth/google?client_id&redirect_uri&state` | valida o cliente e envia ao Google | pública |
| `GET /auth/google/callback` | identidade → acesso → código → volta ao cliente | pública |
| `POST /oauth/token` | código + segredo → JWT RS256 (15 min) | `client_secret` |
| `GET /.well-known/jwks.json` | chave pública | pública |
| `GET /rh/login`, `/rh/callback`, `/rh/logout` | login do RH (cookie HttpOnly) | pública |
| `GET /rh/me` | usuário, roles e permissões | autenticado |
| `GET /rh/servidores?nome&situacao&limite&pagina` | lista de servidores | `rh:servidores:listar` |
| `GET /rh/servidores/{registro}` | dados pessoais e documentos | `rh:servidores:detalhar` |
| `GET /rh/servidores/{registro}/dependentes` | dependentes | `rh:dependentes:ler` |
| `GET /rh/admin/roles` | perfis e o que cada um pode | `rh:usuarios:gerenciar` |
| `GET /rh/admin/usuarios` | usuários da aplicação | `rh:usuarios:gerenciar` |
| `POST /rh/admin/usuarios` | pré-cadastro por e-mail | `rh:usuarios:gerenciar` |
| `PATCH /rh/admin/usuarios/{id}` | trocar nome, perfil, ativar/desativar | `rh:usuarios:gerenciar` |
| `GET /rh/admin/auditoria?usuario_id&acao&alvo&de&ate` | registro de auditoria | `rh:auditoria:ler` |

## Perfis

| Perfil | Pode |
|---|---|
| `admin` | tudo, inclusive usuários e auditoria |
| `rh` | listar, ver dados pessoais e dependentes |
| `consulta` | só a lista de servidores, sem CPF |

Perfis e permissões ficam em `app/auth/rbac.py` e são sincronizados com o banco a cada subida.
O acesso é conferido no banco a cada requisição: desativar alguém ou trocar o perfil vale na hora.

## Auditoria

Tabela `audit_logs`: `login.sucesso`, `login.negado`, `servidores.listar`, `servidores.detalhar`,
`dependentes.listar`, `usuarios.criar`, `usuarios.alterar`, com usuário, alvo, detalhe, data e IP.

O primeiro administrador é criado por `docker compose exec api python -m scripts.seed email "Nome"`.
Os demais usuários, pelas rotas `/rh/admin/usuarios`. Quem não está cadastrado recebe `access_denied`.
Nova dependência: `uv add pacote` e depois `docker compose up -d --build`.
