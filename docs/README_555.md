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

## Frontend (pasta `web/`)

React + Vite + TypeScript. O serviço `web` do compose sobe em `http://localhost:5173` e repassa
`/rh`, `/auth`, `/oauth` e `/.well-known` para a API, então tudo fica na mesma origem e o cookie
de sessão funciona sem ajuste. No `.env`, `FRONTEND_URL=http://localhost:5173/` faz o login voltar
para o frontend. Telas: entrada, painel do diagnóstico (com impressão) e lista nominal por regra.
O frontend não guarda regra de negócio: títulos, gravidades e números vêm da API.

Fora do Docker: `cd web && npm install && npm run dev`. Para publicar: `npm run build` gera `web/dist`.

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
| `GET /rh/dominios/{nome}` | códigos e nomes (situações, vínculos, cargos, divisões...) | `rh:servidores:listar` |
| `GET /rh/diagnostico` | painel: contagem por regra | `rh:diagnostico:painel` |
| `GET /rh/diagnostico/por-divisao` | situação dos vínculos por secretaria | `rh:diagnostico:painel` |
| `GET /rh/diagnostico/{codigo}?formato=json\|csv` | lista nominal de uma regra | `rh:diagnostico:listar` |
| `GET /rh/servidores/{registro}/pendencias` | ficha de pendências do vínculo | `rh:diagnostico:listar` |
| `GET /rh/admin/roles` | perfis e o que cada um pode | `rh:usuarios:gerenciar` |
| `GET /rh/admin/usuarios` | usuários da aplicação | `rh:usuarios:gerenciar` |
| `POST /rh/admin/usuarios` | pré-cadastro por e-mail | `rh:usuarios:gerenciar` |
| `PATCH /rh/admin/usuarios/{id}` | trocar nome, perfil, ativar/desativar | `rh:usuarios:gerenciar` |
| `GET /rh/admin/sessoes?somente_ativas&usuario_id` | sessões abertas | `rh:usuarios:gerenciar` |
| `DELETE /rh/admin/sessoes/{id}` | encerrar uma sessão | `rh:usuarios:gerenciar` |
| `DELETE /rh/admin/usuarios/{id}/sessoes` | encerrar todas as sessões da pessoa | `rh:usuarios:gerenciar` |
| `GET /rh/admin/auditoria?usuario_id&acao&alvo&de&ate` | registro de auditoria | `rh:auditoria:ler` |

## Perfis

| Perfil | Pode |
|---|---|
| `admin` | tudo, inclusive usuários e auditoria |
| `rh` | listar, ver dados pessoais e dependentes, diagnóstico completo |
| `consulta` | lista de servidores sem CPF e painel do diagnóstico (só contagens) |

Perfis e permissões ficam em `app/auth/rbac.py` e são sincronizados com o banco a cada subida.
O acesso é conferido no banco a cada requisição: desativar alguém ou trocar o perfil vale na hora.

## Diagnóstico cadastral (Pré-Censo)

Universo: empresa 001, vínculos nas situações de `SIP_SITUACOES_ATIVAS` (1 = Normal, 3 = Afastado)
e os dependentes presos a esses registros. As regras ficam em `app/rh/regras.py`, como funções puras:

- `D01` a `D10`: dependentes (sem CPF, CPF inválido, IRRF e salário-família acima da idade do vínculo,
  parentesco incoerente, duplicados).
- `S01` a `S06`: servidor (contato, título, PIS, mãe, CPF). Preenchimento falso conta como ausente.
- `V01`, `V02`: vínculo (término vencido, CPF com mais de um vínculo ativo).
- `I01`, `I02`: sem dependentes; `I02` é quando há dependentes em outro registro do mesmo CPF.

Os limites de idade vêm da tabela `VINCULO` do SIP. O resultado fica em memória por
`DIAGNOSTICO_CACHE_MINUTES` (10); `GET /rh/diagnostico?atualizar=true` recalcula.
O diagnóstico mede o cadastro, não o que a folha paga ou deduz.

## Sessão

O login cria uma sessão de 8 horas (`SESSION_HOURS`) em cookie HttpOnly. O JWT continua com 15 minutos
e é renovado sozinho enquanto a sessão vale, sem novo login no Google. A sessão termina no logout,
após 30 minutos sem uso (`SESSION_IDLE_MINUTES`, 0 desliga), quando o admin a encerra ou desativa o usuário.
Clientes de API continuam usando `Authorization: Bearer` com o JWT, sem sessão.

## Auditoria

Tabela `audit_logs`: `login.sucesso`, `login.negado`, `servidores.listar`, `servidores.detalhar`,
`dependentes.listar`, `diagnostico.painel`, `diagnostico.listar`, `diagnostico.ficha`, `usuarios.criar`, `usuarios.alterar`, `sessoes.encerrar`, `logout`, com usuário, alvo, detalhe, data e IP.

O primeiro administrador é criado por `docker compose exec api python -m scripts.seed email "Nome"`.
Os demais usuários, pelas rotas `/rh/admin/usuarios`. Quem não está cadastrado recebe `access_denied`.
Nova dependência: `uv add pacote` e depois `docker compose up -d --build`.
