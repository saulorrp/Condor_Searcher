"""Testes de `services/client.py` com um SDK falso — nenhuma chamada real à API.

As exceções usadas são as **classes reais** do SDK (`perplexity`), construídas à mão: é o que
garante que a tradução para `services/errors.py` continua valendo se o SDK mudar de hierarquia.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx
import pytest
from perplexity import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    NotFoundError,
    PermissionDeniedError,
    PerplexityError,
)
from perplexity import RateLimitError as SdkRateLimitError

from condor.core.models import AgentRequest
from condor.services.client import AgentClient
from condor.services.errors import (
    AuthError,
    CancelledError,
    CondorError,
    EmptyResponseError,
    NetworkError,
    RateLimitError,
    RequestError,
)

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures"
CHAVE_FALSA = "pplx-SEGREDOqueNAOpodeAPARECER123"


@pytest.fixture(scope="module")
def raw_ok() -> dict:
    return json.loads((FIXTURES / "agent_fast.json").read_text(encoding="utf-8"))


@pytest.fixture
def req() -> AgentRequest:
    return AgentRequest(payload={"preset": "fast", "input": "pergunta"}, briefing="b", timeout_s=60)


# ----------------------------------------------------------------- SDK falso


def _httpx_response(status: int) -> httpx.Response:
    pedido = httpx.Request("POST", "https://api.perplexity.ai/v1/agent")
    return httpx.Response(status_code=status, request=pedido)


def erro(classe, status: int = 500, mensagem: str = "falhou"):
    """Constrói uma exceção real do SDK."""
    if classe in (APITimeoutError,):
        return classe(request=httpx.Request("POST", "https://api.perplexity.ai/v1/agent"))
    if classe in (APIConnectionError,):
        return classe(message=mensagem, request=httpx.Request("POST", "https://x"))
    return classe(mensagem, response=_httpx_response(status), body=None)


class FakeSdk:
    """Devolve/levanta, em ordem, o que a lista `roteiro` manda. Conta as chamadas."""

    def __init__(self, *roteiro, api_key: str = CHAVE_FALSA) -> None:
        self.roteiro = list(roteiro)
        self.chamadas: list[dict] = []
        self.api_key = api_key
        self.responses = self

    def create(self, **kwargs):
        self.chamadas.append(kwargs)
        item = self.roteiro.pop(0) if self.roteiro else None
        if isinstance(item, BaseException):
            raise item
        return item


def _client(sdk: FakeSdk, **kwargs) -> tuple[AgentClient, list[float]]:
    """Cliente com o SDK falso e o sono instrumentado (nenhum teste espera de verdade)."""
    esperas: list[float] = []

    def sleep(segundos: float) -> bool:
        esperas.append(segundos)
        return False  # não foi cancelado

    return AgentClient(lambda: sdk, sleep=kwargs.pop("sleep", sleep), **kwargs), esperas


# ----------------------------------------------------------------- caminho feliz


def test_sucesso_devolve_o_dict_cru(raw_ok, req) -> None:
    sdk = FakeSdk(raw_ok)
    client, esperas = _client(sdk)
    assert client.run(req) == raw_ok
    assert len(sdk.chamadas) == 1
    assert esperas == []


def test_payload_e_timeout_chegam_ao_sdk(raw_ok, req) -> None:
    sdk = FakeSdk(raw_ok)
    client, _ = _client(sdk)
    client.run(req)
    assert sdk.chamadas[0] == {"preset": "fast", "input": "pergunta", "timeout": 60}


def test_objeto_do_sdk_com_model_dump_e_convertido(raw_ok, req) -> None:
    class Resposta:
        def model_dump(self, mode: str = "python") -> dict:
            return raw_ok

    client, _ = _client(FakeSdk(Resposta()))
    assert client.run(req)["id"] == raw_ok["id"]


def test_cliente_do_sdk_e_criado_uma_vez_so(raw_ok, req) -> None:
    criacoes = []

    def factory():
        criacoes.append(1)
        return FakeSdk(raw_ok, raw_ok)

    client = AgentClient(factory, sleep=lambda s: False)
    client.run(req)
    client.run(req)
    assert len(criacoes) == 1


# ----------------------------------------------------------------- retries (aceite da F5)


def test_429_depois_sucesso_na_segunda_tentativa(raw_ok, req) -> None:
    sdk = FakeSdk(erro(SdkRateLimitError, 429), raw_ok)
    client, esperas = _client(sdk)
    assert client.run(req) == raw_ok
    assert len(sdk.chamadas) == 2
    assert esperas == [2.0]  # primeiro backoff


def test_timeout_esgota_as_tres_tentativas(req) -> None:
    sdk = FakeSdk(*[erro(APITimeoutError)] * 3)
    client, esperas = _client(sdk)
    with pytest.raises(NetworkError, match="rede ou tempo esgotado"):
        client.run(req)
    assert len(sdk.chamadas) == 3
    assert esperas == [2.0, 4.0]  # 2 esperas entre 3 tentativas


def test_401_nao_repete(req) -> None:
    sdk = FakeSdk(erro(AuthenticationError, 401), erro(AuthenticationError, 401))
    client, esperas = _client(sdk)
    with pytest.raises(AuthError, match="recusada"):
        client.run(req)
    assert len(sdk.chamadas) == 1  # sem retry
    assert esperas == []


def test_erro_de_pedido_nao_repete(req) -> None:
    sdk = FakeSdk(erro(BadRequestError, 400), erro(BadRequestError, 400))
    client, _ = _client(sdk)
    with pytest.raises(RequestError, match="recusou o pedido"):
        client.run(req)
    assert len(sdk.chamadas) == 1


def test_500_repete_e_pode_dar_certo(raw_ok, req) -> None:
    sdk = FakeSdk(erro(InternalServerError, 503), raw_ok)
    client, esperas = _client(sdk)
    assert client.run(req) == raw_ok
    assert esperas == [2.0]


def test_backoff_usa_2_e_4_com_tres_tentativas(req) -> None:
    sdk = FakeSdk(*[erro(SdkRateLimitError, 429)] * 3)
    client, esperas = _client(sdk)
    with pytest.raises(RateLimitError):
        client.run(req)
    assert esperas == [2.0, 4.0]


def test_numero_de_tentativas_e_configuravel(req) -> None:
    sdk = FakeSdk(*[erro(APITimeoutError)] * 5)
    client, esperas = _client(sdk, max_attempts=4)
    with pytest.raises(NetworkError):
        client.run(req)
    assert len(sdk.chamadas) == 4
    assert esperas == [2.0, 4.0, 8.0]


# ----------------------------------------------------------------- tradução de erros


@pytest.mark.parametrize(
    ("classe", "status", "esperada"),
    [
        (AuthenticationError, 401, AuthError),
        (PermissionDeniedError, 403, AuthError),
        (SdkRateLimitError, 429, RateLimitError),
        (BadRequestError, 400, RequestError),
        (NotFoundError, 404, RequestError),
        (InternalServerError, 500, NetworkError),
        (APITimeoutError, 0, NetworkError),
        (APIConnectionError, 0, NetworkError),
    ],
)
def test_cada_erro_do_sdk_vira_o_nosso(req, classe, status: int, esperada) -> None:
    client, _ = _client(FakeSdk(*[erro(classe, status)] * 3))
    with pytest.raises(esperada):
        client.run(req)


def test_erro_generico_do_sdk_vira_network_error(req) -> None:
    client, _ = _client(FakeSdk(*[PerplexityError("coisa estranha")] * 3))
    with pytest.raises(NetworkError, match="SDK da Perplexity"):
        client.run(req)


def test_erro_totalmente_inesperado_vira_condor_error(req) -> None:
    client, _ = _client(FakeSdk(RuntimeError("explodiu")))
    with pytest.raises(CondorError, match="Erro inesperado"):
        client.run(req)


def test_todas_as_mensagens_sao_em_portugues(req) -> None:
    for classe, status in ((AuthenticationError, 401), (BadRequestError, 400), (InternalServerError, 500)):
        client, _ = _client(FakeSdk(*[erro(classe, status)] * 3))
        with pytest.raises(CondorError) as info:
            client.run(req)
        assert any(p in str(info.value) for p in ("chave", "pedido", "API", "rede"))


# ----------------------------------------------------------------- chave ausente / vazamento


def test_chave_ausente_na_criacao_vira_auth_error(req) -> None:
    def factory():
        raise PerplexityError("The api_key client option must be set")

    with pytest.raises(AuthError, match="Configure a chave"):
        AgentClient(factory).run(req)


def test_falha_desconhecida_na_criacao_nao_e_auth_error(req) -> None:
    def factory():
        raise RuntimeError("disco cheio")

    with pytest.raises(CondorError, match="iniciar a conexão"):
        AgentClient(factory).run(req)


def test_mensagem_de_erro_nunca_expoe_a_chave(req) -> None:
    """Erro do SDK que ecoa a credencial não pode chegar inteiro ao usuário."""
    vazando = PerplexityError(f"401 unauthorized for key {CHAVE_FALSA} (Bearer {CHAVE_FALSA})")
    client, _ = _client(FakeSdk(*[vazando] * 3))
    with pytest.raises(CondorError) as info:
        client.run(req)
    texto = str(info.value)
    assert CHAVE_FALSA not in texto
    assert "pplx-***" in texto


def test_nenhum_log_contem_a_chave(req, caplog) -> None:
    vazando = PerplexityError(f"erro com a chave {CHAVE_FALSA}")
    client, _ = _client(FakeSdk(vazando, vazando, vazando))
    with caplog.at_level(logging.DEBUG), pytest.raises(CondorError):
        client.run(req)
    tudo = "\n".join(r.getMessage() for r in caplog.records)
    assert caplog.records  # o aviso de retry saiu
    assert CHAVE_FALSA not in tudo
    assert "pplx-" not in tudo


# ----------------------------------------------------------------- resposta vazia


def test_resposta_sem_texto_vira_empty_response_error(req) -> None:
    vazia = {
        "id": "resp_x",
        "output": [{"type": "message", "content": [{"type": "output_text", "text": " "}]}],
    }
    client, _ = _client(FakeSdk(vazia))
    with pytest.raises(EmptyResponseError, match="sem texto de resposta"):
        client.run(req)


def test_resposta_vazia_nao_repete(req) -> None:
    sdk = FakeSdk({}, {})
    client, _ = _client(sdk)
    with pytest.raises(EmptyResponseError):
        client.run(req)
    assert len(sdk.chamadas) == 1


def test_resposta_em_formato_inesperado(req) -> None:
    client, _ = _client(FakeSdk("isto nao e um dict"))
    with pytest.raises(NetworkError, match="formato inesperado"):
        client.run(req)


# ----------------------------------------------------------------- cancelamento


def test_cancelar_antes_de_rodar_nao_chama_a_api(raw_ok, req) -> None:
    sdk = FakeSdk(raw_ok)
    client, _ = _client(sdk)
    client.cancel()
    with pytest.raises(CancelledError, match="cancelada"):
        client.run(req)
    assert sdk.chamadas == []


def test_cancelamento_durante_o_backoff_interrompe(req) -> None:
    sdk = FakeSdk(erro(SdkRateLimitError, 429), erro(SdkRateLimitError, 429))
    client, _ = _client(sdk, sleep=lambda s: True)  # a espera informa "cancelado"
    with pytest.raises(CancelledError):
        client.run(req)
    assert len(sdk.chamadas) == 1  # não começou a segunda tentativa


def test_cancelar_depois_da_resposta_descarta_o_resultado(raw_ok, req) -> None:
    """A chamada em andamento não é abortável; o que garantimos é não usar o resultado."""

    class CancelaDurante(FakeSdk):
        def create(self, **kwargs):
            client.cancel()
            return super().create(**kwargs)

    sdk = CancelaDurante(raw_ok)
    client, _ = _client(sdk)
    with pytest.raises(CancelledError):
        client.run(req)
    assert len(sdk.chamadas) == 1


def test_cancelamento_sobrevive_ao_run_e_so_reset_limpa(raw_ok, req) -> None:
    """Limpar a flag dentro do `run()` engoliria um cancelamento pedido logo antes."""
    sdk = FakeSdk(raw_ok, raw_ok)
    client, _ = _client(sdk)
    client.cancel()

    with pytest.raises(CancelledError):
        client.run(req)
    with pytest.raises(CancelledError):
        client.run(req)  # continua valendo
    assert sdk.chamadas == []

    client.reset()
    assert client.run(req) == raw_ok  # só agora a instância volta a servir
    assert not client.cancelled


# ----------------------------------------------------------------- a chave chega ao SDK
# Regressão do defeito achado depois da F7: o app não injeta o `.env` no ambiente (F6), então a
# chave tem de ser passada ao SDK explicitamente — senão a chave gravada pelo diálogo do RF7
# existia no `.env` e o SDK dizia "nenhuma chave encontrada".


def test_a_chave_do_provider_chega_ao_construtor_do_sdk(raw_ok, req, monkeypatch) -> None:
    recebidas: list[str | None] = []

    def fake_build(api_key):
        recebidas.append(api_key)
        return FakeSdk(raw_ok)

    monkeypatch.setattr("condor.services.client._build_sdk_client", fake_build)
    client = AgentClient(api_key_provider=lambda: CHAVE_FALSA, sleep=lambda s: False)
    client.run(req)

    assert recebidas == [CHAVE_FALSA]


def test_provider_e_relido_depois_de_forget_client(raw_ok, req, monkeypatch) -> None:
    """Trocar a chave no diálogo tem de valer na busca seguinte, sem reiniciar (RF7)."""
    recebidas: list[str | None] = []
    chaves = iter(["pplx-primeira1234567890", "pplx-segunda12345678901"])
    atual = {"chave": next(chaves)}

    def fake_build(api_key):
        recebidas.append(api_key)
        return FakeSdk(raw_ok, raw_ok)

    monkeypatch.setattr("condor.services.client._build_sdk_client", fake_build)
    client = AgentClient(api_key_provider=lambda: atual["chave"], sleep=lambda s: False)
    client.run(req)

    atual["chave"] = next(chaves)
    client.forget_client()
    client.run(req)

    assert recebidas == ["pplx-primeira1234567890", "pplx-segunda12345678901"]


def test_sem_provider_o_sdk_decide_e_a_falta_de_chave_vira_auth_error(req, monkeypatch) -> None:
    def fake_build(api_key):
        assert api_key is None
        raise PerplexityError("The api_key client option must be set")

    monkeypatch.setattr("condor.services.client._build_sdk_client", fake_build)
    with pytest.raises(AuthError, match="Configure a chave"):
        AgentClient().run(req)
