"""Exceções do Condor (TECHSPEC §7, API_NOTES §6, RF6).

Todas carregam uma mensagem **em português, pronta para mostrar ao usuário**: a UI não decide
texto, só exibe `str(exc)`. Nenhuma mensagem inclui a chave da API nem o payload.

`retryable` diz se vale tentar de novo. Fica na exceção, e não numa tabela no cliente, para a
resposta a um erro novo ser decidida onde o erro é criado.
"""

from __future__ import annotations

import re

#: Qualquer coisa com cara de credencial. Algumas mensagens de erro de rede ecoam o cabeçalho
#: de autorização, e parte das nossas mensagens interpola o texto do erro original — então a
#: limpeza fica aqui, no caminho por onde toda mensagem passa (TECHSPEC §5: nada de chave em
#: logs ou mensagens de erro).
_SEGREDO = re.compile(r"(pplx-)[A-Za-z0-9_\-]{4,}|(Bearer\s+)\S+", re.IGNORECASE)


def scrub(text: str) -> str:
    """Troca credenciais por `***`, preservando o prefixo para a mensagem seguir legível."""
    return _SEGREDO.sub(lambda m: f"{m.group(1) or m.group(2)}***", text)


class CondorError(Exception):
    """Base de tudo o que o app sabe explicar ao usuário."""

    #: Erros de rede/limite valem nova tentativa; chave inválida ou payload errado, não.
    retryable: bool = False

    def __init__(self, message: str, *, cause: Exception | None = None) -> None:
        message = scrub(message)
        super().__init__(message)
        self.message = message
        self.cause = cause


class AuthError(CondorError):
    """Chave ausente, inválida ou sem permissão (401/403). Nunca repetir."""


class RequestError(CondorError):
    """A API recusou o pedido (400/404/422): o problema está no que enviamos, não na rede."""


class RateLimitError(CondorError):
    """Limite de taxa (429)."""

    retryable = True


class NetworkError(CondorError):
    """Rede, timeout ou erro do servidor (5xx)."""

    retryable = True


class EmptyResponseError(CondorError):
    """A chamada terminou sem texto de resposta."""


class CancelledError(CondorError):
    """O usuário cancelou a busca."""
