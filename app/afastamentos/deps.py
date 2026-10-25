"""
Autenticação/permissão do módulo de afastamentos.

Usa o mesmo controle do backend do RH (app.rh.deps): sessão por cookie ou
Bearer, e permissões por slug (ex.: "rh:diagnostico:painel").

Fora do backend (testes isolados do módulo), cai num modo fechado:
as rotas respondem 503 até um teste substituir `obter_usuario_atual`.
"""
from fastapi import Depends, HTTPException, status

try:  # dentro do MICRO_SERVICE_BACKEND_RH_CLEAN
    from app.rh.deps import current_user as obter_usuario_atual
    from app.rh.deps import require_permission as _require_permission

    INTEGRADO = True
except ImportError:  # módulo testado sozinho
    INTEGRADO = False

    def obter_usuario_atual():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Autenticação não disponível fora do backend do RH.",
        )

    def _require_permission(slug: str):
        def dependency(user: dict = Depends(obter_usuario_atual)) -> dict:
            if slug not in user.get("permissions", []):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissão")
            return user

        return dependency


def exigir_permissao(slug: str):
    """Dependência FastAPI: exige a permissão `slug` do usuário logado."""
    return _require_permission(slug)
