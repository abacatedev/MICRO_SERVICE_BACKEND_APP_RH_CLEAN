"""
Peças do catálogo de relatórios: coluna, filtro e relatório.

Um relatório é: de onde vêm as linhas (`carregar`), que colunas existem, que
filtros aceita e quem pode ver. A tela de Relatórios se monta a partir disso
(GET /rh/relatorios), então um relatório novo aparece sem mexer no frontend.
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable

# Permissões que já existem no backend do RH
PERM_PAINEL = "rh:diagnostico:painel"        # só números
PERM_NOMINAL = "rh:diagnostico:listar"       # listas com nome e REGISTRO
PERM_SERVIDORES = "rh:servidores:listar"     # lista geral de vínculos
PERM_SENSIVEL = "rh:servidores:detalhar"     # CPF, celular, e-mail (mesma regra de /rh/servidores)

TIPOS_COLUNA = {"texto", "numero", "data", "sim_nao", "percentual", "lista"}
TIPOS_FILTRO = {"selecao", "multipla", "numero", "data", "booleano"}


@dataclass(frozen=True)
class Coluna:
    id: str
    rotulo: str
    tipo: str = "texto"
    padrao: bool = True          # aparece marcada quando o usuário não escolhe colunas
    sensivel: bool = False       # só para quem tem PERM_SENSIVEL
    busca: bool = False          # entra na busca por texto

    def descrever(self) -> dict:
        return {"id": self.id, "rotulo": self.rotulo, "tipo": self.tipo, "padrao": self.padrao,
                "sensivel": self.sensivel}


Opcoes = list[tuple[str, str]] | Callable[[], list[tuple[str, str]]] | None


@dataclass(frozen=True)
class Filtro:
    id: str
    rotulo: str
    tipo: str = "selecao"
    campo: str | None = None          # filtra a linha por este campo (e gera contagem por valor)
    campo_rotulo: str | None = None   # campo com o nome que aparece na lista de opções
    opcoes: Opcoes = None             # fixas; sem opções e com `campo`, a lista vem das linhas
    dominio: str | None = None        # sugestão para a tela: GET /rh/dominios/{dominio}
    padrao: Any = None
    obrigatorio: bool = False
    minimo: int | None = None
    maximo: int | None = None
    ajuda: str | None = None
    somente: bool = False             # booleano "Somente ...": falso não filtra (mostra todos)

    def lista_opcoes(self) -> list[tuple[str, str]] | None:
        return self.opcoes() if callable(self.opcoes) else self.opcoes

    def descrever(self) -> dict:
        ops = self.lista_opcoes()
        padrao = self.padrao.isoformat() if isinstance(self.padrao, date) else self.padrao
        return {
            "id": self.id, "rotulo": self.rotulo, "tipo": self.tipo,
            "opcoes": [{"valor": v, "rotulo": r} for v, r in ops] if ops is not None else None,
            "opcoes_das_linhas": ops is None and self.campo is not None and self.tipo in ("selecao", "multipla"),
            "dominio": self.dominio, "padrao": padrao, "obrigatorio": self.obrigatorio,
            "minimo": self.minimo, "maximo": self.maximo, "ajuda": self.ajuda, "somente": self.somente,
        }


@dataclass(frozen=True)
class Relatorio:
    id: str
    grupo: str
    titulo: str
    descricao: str
    natureza: str                         # "nominal" (uma linha por vínculo) ou "agregado"
    permissao: str
    colunas: list[Coluna]
    carregar: Callable[[dict], dict]      # recebe os filtros sem `campo`; devolve {"linhas": [...], ...}
    filtros: list[Filtro] = field(default_factory=list)
    ordem_padrao: tuple[str, bool] | None = None   # (coluna, decrescente)
    fichas: tuple[str, ...] = ()          # "pendencias" e/ou "afastamentos": link de cada linha

    @property
    def nominal(self) -> bool:
        return self.natureza == "nominal"

    def coluna(self, cid: str) -> Coluna | None:
        return next((c for c in self.colunas if c.id == cid), None)

    def descrever(self, pode_ver_sensivel: bool) -> dict:
        return {
            "id": self.id, "grupo": self.grupo, "titulo": self.titulo, "descricao": self.descricao,
            "natureza": self.natureza, "permissao": self.permissao,
            "busca": any(c.busca for c in self.colunas),
            "agrupar_por_pessoa": self.nominal,
            "colunas": [c.descrever() for c in self.colunas if pode_ver_sensivel or not c.sensivel],
            "filtros": [f.descrever() for f in self.filtros],
            "ordem_padrao": {"coluna": self.ordem_padrao[0], "decrescente": self.ordem_padrao[1]}
            if self.ordem_padrao else None,
            "fichas": list(self.fichas),
        }
