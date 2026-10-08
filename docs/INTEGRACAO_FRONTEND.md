# Como ligar um frontend a esta API

Vale para qualquer frontend que rode em outra porta, por exemplo `http://localhost:3000`.
A documentação interativa fica em `http://localhost:8000/docs` e o contrato em
`http://localhost:8000/openapi.json` (cópia em `docs/openapi.json`).

## 1. Configuração da API

No `.env` do backend:

```dotenv
FRONTEND_URL=http://localhost:3000/
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
```

`CORS_ORIGINS` é a lista de frontends autorizados: sem barra no final e com a porta exata.
Depois de alterar, recrie a API: `docker compose up -d --force-recreate api`.

No Google Cloud nada muda: o retorno do Google continua em `http://localhost:8000/auth/google/callback`.

## 2. Fluxo de login

| Passo | O que o frontend faz |
|---|---|
| Entrar | Navega (não é `fetch`) para `http://localhost:8000/rh/login?retorno=http://localhost:3000/` |
| Voltar | A pessoa retorna ao endereço de `retorno`, já com a sessão em cookie HttpOnly |
| Saber quem é | `GET /rh/me` com credenciais: devolve nome, perfis e permissões |
| Acesso negado | A pessoa volta com `?acesso=negado` na URL: mostre o aviso |
| Sair | Navega para `http://localhost:8000/rh/logout?retorno=http://localhost:3000/` |

A sessão dura 8 horas (30 minutos sem uso a encerra). O frontend não guarda token nem senha.

## 3. Chamadas com o cookie (recomendado)

```ts
const API = "http://localhost:8000";

export async function api<T>(caminho: string, init?: RequestInit): Promise<T> {
  const r = await fetch(API + caminho, { ...init, credentials: "include" });
  if (r.status === 401) {
    const volta = encodeURIComponent(window.location.href);
    window.location.href = `${API}/rh/login?retorno=${volta}`;
    throw new Error("Sessão expirada");
  }
  if (r.status === 403) throw new Error("Sem permissão");
  if (!r.ok) throw new Error(`Falha ${r.status}`);
  return r.json();
}

// exemplos
const eu = await api("/rh/me");
const painel = await api("/rh/diagnostico");
```

O `credentials: "include"` é obrigatório: sem ele o navegador não envia o cookie para outra porta.
Com axios: `axios.create({ baseURL: API, withCredentials: true })`.

Para baixar a planilha, use um link comum: `<a href="http://localhost:8000/rh/diagnostico/D01?formato=csv">`.

## 4. Chamadas com token (alternativa)

Para quem prefere `Authorization: Bearer`, ou chama a API a partir do servidor do frontend:

```ts
const { access_token } = await api<{ access_token: string }>("/rh/token"); // exige a sessão aberta
await fetch(API + "/rh/diagnostico", { headers: { Authorization: `Bearer ${access_token}` } });
```

O token vale 15 minutos. Quando a API responder 401, peça outro em `/rh/token`.
Guarde-o só em memória, não em `localStorage`.

## 5. Menus conforme o perfil

Use o campo `permissions` do `/rh/me`:

| Permissão | Libera |
|---|---|
| `rh:diagnostico:painel` | Painel (contagens) |
| `rh:diagnostico:listar` | Listas nominais, planilhas e ficha de pendências |
| `rh:servidores:listar` | Busca de servidores e domínios |
| `rh:servidores:detalhar` | Dados completos do servidor |
| `rh:dependentes:ler` | Dependentes |
| `rh:usuarios:gerenciar` | Usuários e sessões |
| `rh:auditoria:ler` | Auditoria |

## 6. Cliente tipado a partir do contrato

```bash
npx openapi-typescript http://localhost:8000/openapi.json -o src/api/schema.d.ts
```

Para regravar a cópia do repositório: `docker compose exec api python -m scripts.exportar_openapi`.

## 7. Problemas comuns

| Sintoma | Causa |
|---|---|
| Erro de CORS no console | A origem do frontend não está em `CORS_ORIGINS`, ou a API não foi recriada |
| `/rh/me` devolve 401 logo após o login | Faltou `credentials: "include"` |
| "Endereço de retorno não autorizado" | O `retorno` aponta para uma origem fora de `CORS_ORIGINS` |
| Login volta para a porta errada | Faltou o `retorno`; sem ele vale o `FRONTEND_URL` |
| Funciona em `localhost` e falha em `127.0.0.1` | São origens diferentes; use sempre `localhost` |
