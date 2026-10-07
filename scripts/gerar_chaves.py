"""Gera o par RS256 em keys/ (fora do Git).  Uso: python -m scripts.gerar_chaves"""
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def gerar(pasta: str = "keys") -> None:
    dir_ = Path(pasta)
    dir_.mkdir(exist_ok=True)
    priv, pub = dir_ / "private.pem", dir_ / "public.pem"
    if priv.exists():
        print("keys/private.pem já existe; nada foi alterado.")
        return
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    pub.write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )
    print("Chaves geradas em", dir_.resolve())


if __name__ == "__main__":
    gerar()
