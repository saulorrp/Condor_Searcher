"""SDK falso para os testes — nenhuma chamada de rede.

Usado pela interface (F7/F10) e pela linha de comando (F11).

Fala os dois modos: resposta de uma vez e `stream=True`, este último devolvendo os eventos que o
`services/client.py` escuta (`response.output_text.delta`, `response.reasoning.search_results`,
`response.completed`). Os nomes e campos são os do SDK 0.43.7, conferidos na F10.
"""

from __future__ import annotations

from typing import Any


class FakeEvent:
    """Um evento do fluxo. Só precisa de `type` e dos campos que o cliente lê."""

    def __init__(self, type: str, **campos: Any) -> None:  # noqa: A002 — o campo do SDK se chama type
        self.type = type
        for nome, valor in campos.items():
            setattr(self, nome, valor)


class FakeResponse:
    """Objeto do SDK que o evento `response.completed` carrega."""

    def __init__(self, raw: dict) -> None:
        self._raw = raw

    def model_dump(self, mode: str = "python") -> dict:
        return self._raw


def stream_events(raw: dict, pedacos: tuple[str, ...] = ("Lis", "boa", "."), fontes: int = 2):
    """Fluxo típico: busca, texto em pedaços e a resposta final."""
    yield FakeEvent("response.created")
    yield FakeEvent(
        "response.reasoning.search_results", results=[{"url": f"https://{i}.pt"} for i in range(fontes)]
    )
    for pedaco in pedacos:
        yield FakeEvent("response.output_text.delta", delta=pedaco)
    yield FakeEvent("response.output_text.done", text="".join(pedacos))
    yield FakeEvent("tipo.desconhecido.do.futuro", seja_o_que_for=1)
    yield FakeEvent("response.completed", response=FakeResponse(raw))


class SdkFalso:
    """Devolve a fixture real da F0 (ou levanta o erro pedido). Conta as chamadas."""

    def __init__(
        self,
        raw: dict,
        erro: Exception | None = None,
        eventos=None,
    ) -> None:
        self.raw = raw
        self.erro = erro
        self.eventos = eventos  # gerador para o modo streaming; None usa o fluxo típico
        self.chamadas: list[dict] = []
        self.fechado = False
        self.responses = self

    def create(self, **kwargs):
        self.chamadas.append(kwargs)
        if self.erro is not None:
            raise self.erro
        if kwargs.get("stream"):
            return FakeStream(self, self.eventos if self.eventos is not None else stream_events(self.raw))
        return self.raw


class FakeStream:
    """O que o SDK devolve com `stream=True`: um iterável que o cliente fecha no fim."""

    def __init__(self, sdk: SdkFalso, eventos) -> None:
        self._sdk = sdk
        self._eventos = iter(eventos)

    def __iter__(self):
        return self._eventos

    def close(self) -> None:
        self._sdk.fechado = True
