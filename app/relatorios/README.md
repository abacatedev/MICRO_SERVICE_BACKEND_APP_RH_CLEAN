# Módulo de relatórios (`app/relatorios`)

Página **Relatórios** do RH: escolhe o relatório, filtra, busca, escolhe colunas,
agrupa por pessoa e exporta em CSV ou Excel. Só lê o SIP.

## Instalar no backend

1. Copie a pasta `relatorios/` para `app/relatorios/`.
2. No `app/main.py`, junto dos outros routers:

   ```python
   from app.relatorios.router import router as relatorios_router
   app.include_router(relatorios_router)
   ```

3. Excel precisa do `openpyxl` e PDF do `reportlab` (`uv add openpyxl reportlab`). Sem eles,
   o CSV funciona e o formato que faltar responde 501.
4. Rebuild: `docker compose up -d --build api`.

Não cria tabela, não muda o `.env` e não cria permissão: usa as que já existem.

## Rotas

| Rota | O que faz |
|---|---|
| `GET /rh/relatorios` | Catálogo: relatórios que o usuário pode abrir, com colunas e filtros |
| `GET /rh/relatorios/{id}` | Linhas, com `q`, filtros, `colunas`, `agrupar`, `ordenar`, `direcao`, `pagina`, `por_pagina` |
| `GET /rh/relatorios/{id}/exportar?formato=csv\|xlsx\|pdf` | O mesmo resultado inteiro (até 50.000 linhas; PDF até 10.000) |

Os filtros vão na query com o id do filtro: `?secretaria=000003&secretaria=000010` ou `?secretaria=3,10`.

## Permissões

| Relatórios | Permissão |
|---|---|
| Vínculos do SIP | `rh:servidores:listar` |
| Listas nominais do diagnóstico e de afastamentos | `rh:diagnostico:listar` |
| Agregados (por secretaria, por tipo, por mês, faixa etária) | `rh:diagnostico:painel` |
| Colunas CPF, celular, e-mail, CPF e mãe do dependente, e busca por CPF | `rh:servidores:detalhar` |

Cada consulta e cada exportação vai para a auditoria (`relatorios.consultar` e `relatorios.exportar`).

## Testes

```bash
uv run pytest app/relatorios/tests -q
```
