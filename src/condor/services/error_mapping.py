"""Exceção do SDK → exceção nossa, com mensagem em português (API_NOTES §6).

Separado do `client.py` porque é uma tabela de tradução, não lógica de chamada: quando a
Perplexity acrescentar um erro novo, é aqui que se mexe, sem tocar em retries nem cancelamento.

Junto com `client.py`, é o único lugar que conhece os tipos do SDK.
"""

from __future__ import annotations

from typing import Any

from perplexity import (
    APIConnectionError,
    APIStatusError,
    AuthenticationError,
    PermissionDeniedError,
    PerplexityError,
)
from perplexity import RateLimitError as SdkRateLimitError

from condor.services.errors import (
    AuthError,
    CondorError,
    NetworkError,
    RateLimitError,
    RequestError,
)

AVISO_CHAVE = "Verifique a chave em Configurações → Chave da API."


def from_startup_error(exc: Exception) -> CondorError:
    """Falha ao criar o cliente do SDK: quase sempre é chave ausente."""
    texto = str(exc).lower()
    if "api_key" in texto or "api key" in texto or isinstance(exc, AuthenticationError):
        return AuthError(
            "Nenhuma chave da API encontrada. Configure a chave em Configurações → Chave da API."
        )
    return CondorError(f"Não foi possível iniciar a conexão com a API: {exc}")


def translate(exc: Exception) -> CondorError:
    """Traduz qualquer exceção vinda do SDK.

    A classe do SDK vem primeiro; o `status_code` entra como rede de segurança para erros que o
    SDK desta versão ainda não modela em classe própria.
    """
    if isinstance(exc, CondorError):
        return exc
    if isinstance(exc, (AuthenticationError, PermissionDeniedError)):
        return AuthError(f"A chave da API foi recusada (401). {AVISO_CHAVE}")
    if isinstance(exc, SdkRateLimitError):
        return RateLimitError("A API está limitando as chamadas (429). Vou tentar de novo em instantes.")
    if isinstance(exc, APIConnectionError):
        # APITimeoutError é subclasse desta.
        return NetworkError("Não foi possível falar com a API (rede ou tempo esgotado). Verifique a conexão.")
    if isinstance(exc, APIStatusError):
        return from_status(getattr(exc, "status_code", None), exc)
    if isinstance(exc, PerplexityError):
        return NetworkError(f"Erro do SDK da Perplexity: {exc}")
    return CondorError(f"Erro inesperado ao chamar a API: {exc}")


def from_status(status: int | None, exc: Exception) -> CondorError:
    """Erro HTTP sem classe própria no SDK."""
    if status in (401, 403):
        return AuthError(f"A chave da API foi recusada ({status}). {AVISO_CHAVE}")
    if status == 429:
        return RateLimitError("A API está limitando as chamadas (429). Vou tentar de novo em instantes.")
    if status is not None and 500 <= status < 600:
        return NetworkError(f"A API respondeu com erro interno ({status}). Vou tentar de novo.")
    if status is not None and 400 <= status < 500:
        return RequestError(
            f"A API recusou o pedido ({status}). Revise as opções da busca — "
            "domínios, datas ou instruções próprias."
        )
    return NetworkError(f"A API respondeu com um erro não esperado: {exc}")


def from_stream_event(erro: Any) -> CondorError:
    """Evento `response.failed`: a API avisou da falha dentro do próprio fluxo (streaming)."""
    mensagem = str(getattr(erro, "message", "") or "a API não detalhou o motivo")
    codigo = str(getattr(erro, "code", "") or "")
    if codigo in ("401", "403") or "api_key" in mensagem.lower():
        return AuthError(f"A chave da API foi recusada durante a busca ({mensagem}). {AVISO_CHAVE}")
    return NetworkError(f"A busca falhou no meio do caminho: {mensagem}")
