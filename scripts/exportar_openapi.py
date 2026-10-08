"""Grava o contrato da API em docs/openapi.json.  Uso: python -m scripts.exportar_openapi

Serve para gerar o cliente tipado no frontend, por exemplo:
  npx openapi-typescript docs/openapi.json -o src/api/schema.d.ts
"""
import json
from pathlib import Path

from app.main import app


def main(destino: str = "docs/openapi.json") -> None:
    Path(destino).parent.mkdir(exist_ok=True)
    Path(destino).write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2), encoding="utf-8")
    print("Contrato gravado em", destino)


if __name__ == "__main__":
    main()
