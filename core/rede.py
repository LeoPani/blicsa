"""Ajustes de rede compartilhados por todas as conexões do app (urllib).

Certificados: o Python do macOS (Homebrew, python.org e o app empacotado pelo PyInstaller)
nem sempre enxerga os certificados do sistema. Na verificação ao vivo de 04/10, repositórios
de PDFs falharam com "CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate".
Usar a lista do `certifi` (a mesma do Firefox) em todo contexto HTTPS resolve isso sem
desligar a verificação. Sem o `certifi`, fica o padrão do sistema.
"""

from __future__ import annotations

import ssl

_configurado = False


def contexto_ssl() -> ssl.SSLContext:
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def configurar_certificados() -> None:
    """Faz o `urllib` usar `contexto_ssl()` por padrão (idempotente)."""
    global _configurado
    if _configurado:
        return
    try:
        import certifi  # noqa: F401
    except Exception:
        return
    ssl._create_default_https_context = contexto_ssl   # noqa: SLF001 — gancho oficial do urllib
    _configurado = True
