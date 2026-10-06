"""Testes de `services/errors.py`: hierarquia, política de retry e limpeza de credenciais."""

from __future__ import annotations

import pytest

from condor.services.errors import (
    AuthError,
    CancelledError,
    CondorError,
    EmptyResponseError,
    NetworkError,
    RateLimitError,
    RequestError,
    scrub,
)

TODAS = (AuthError, RequestError, RateLimitError, NetworkError, EmptyResponseError, CancelledError)


@pytest.mark.parametrize("classe", TODAS)
def test_tudo_descende_de_condor_error(classe) -> None:
    assert issubclass(classe, CondorError)
    assert str(classe("mensagem")) == "mensagem"


@pytest.mark.parametrize("classe", (RateLimitError, NetworkError))
def test_erros_transitorios_sao_repetiveis(classe) -> None:
    assert classe("x").retryable is True


@pytest.mark.parametrize("classe", (AuthError, RequestError, EmptyResponseError, CancelledError))
def test_erros_definitivos_nao_sao_repetiveis(classe) -> None:
    assert classe("x").retryable is False


def test_causa_original_fica_guardada() -> None:
    causa = ValueError("raiz")
    erro = NetworkError("falhou", cause=causa)
    assert erro.cause is causa
    assert erro.message == "falhou"


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("chave pplx-abcdef123456 vazou", "chave pplx-*** vazou"),
        ("Authorization: Bearer pplx-abcdef123456", "Authorization: Bearer ***"),
        ("bearer XYZ123", "bearer ***"),
        ("duas: pplx-aaaa1111 e pplx-bbbb2222", "duas: pplx-*** e pplx-***"),
        ("PPLX-MAIUSCULO1234", "PPLX-***"),
    ],
)
def test_scrub_troca_credenciais(entrada: str, esperado: str) -> None:
    assert scrub(entrada) == esperado


@pytest.mark.parametrize(
    "entrada",
    ["sem segredo nenhum", "pplx", "o termo pplx- sozinho", "Bearer", "rede indisponível"],
)
def test_scrub_nao_mexe_no_que_nao_e_credencial(entrada: str) -> None:
    assert scrub(entrada) == entrada


@pytest.mark.parametrize("classe", TODAS)
def test_toda_exceção_limpa_a_mensagem(classe) -> None:
    erro = classe("falha com pplx-SEGREDO123456")
    assert "pplx-***" in str(erro)
    assert "SEGREDO" not in str(erro)
    assert "SEGREDO" not in erro.message
