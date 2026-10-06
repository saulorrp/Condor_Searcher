"""Chamada à Perplexity Agent API (API_NOTES §1, §3, §6).

**Único arquivo do projeto que importa o SDK `perplexity`.** Quem está acima recebe dicionários e
exceções do `services/errors.py`, nunca tipos do SDK — é o que permite trocar de SDK sem mexer na UI.

O SDK é injetável (`client_factory`), e é assim que os testes rodam sem tocar na rede.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any, Protocol

from condor.core.models import AgentRequest
from condor.core.response_parser import parse
from condor.services.error_mapping import from_startup_error, from_stream_event, translate
from condor.services.errors import (
    CancelledError,
    CondorError,
    EmptyResponseError,
    NetworkError,
)

logger = logging.getLogger(__name__)

#: Tentativas totais por busca (RF6).
MAX_ATTEMPTS = 3

#: Espera antes de cada nova tentativa. Com `MAX_ATTEMPTS = 3` usamos 2s e 4s;
#: o 8 fica para quem quiser subir o número de tentativas sem mudar o resto.
BACKOFF_SECONDS = (2.0, 4.0, 8.0)


KeyProvider = Callable[[], str | None]


class StreamSink(Protocol):
    """Quem recebe o texto enquanto ele chega (F10: streaming).

    `restart()` existe porque uma tentativa pode falhar no meio do fluxo: quem está mostrando o
    texto precisa apagar o pedaço recebido antes de a próxima tentativa recomeçar do zero.
    """

    def delta(self, texto: str) -> None: ...

    def restart(self) -> None: ...

    def note(self, mensagem: str) -> None: ...


def _build_sdk_client(api_key: str | None) -> Any:
    """Cria o cliente do SDK.

    A chave é passada **explicitamente**. O SDK sabe ler `PERPLEXITY_API_KEY` do ambiente, mas o
    app não injeta o `.env` no ambiente de propósito (decisão da F6, para distinguir variável de
    sistema de arquivo). Sem passar a chave aqui, uma chave gravada no `.env` pelo diálogo do RF7
    nunca chegaria ao SDK — foi exatamente o defeito corrigido depois da F7.
    """
    from perplexity import Perplexity

    return Perplexity(api_key=api_key) if api_key else Perplexity()


class AgentClient:
    """Executa um `AgentRequest` com retries, backoff e cancelamento cooperativo.

    O cancelamento é verificado antes de cada tentativa e interrompe a espera do backoff na hora.
    Ele **não** aborta uma chamada HTTP já em andamento: o SDK é bloqueante, então a tentativa
    corrente ainda termina: o que garantimos é que nenhuma nova tentativa começa e que o resultado
    é descartado. Para o usuário, quem solta a interface é a thread da UI (F7).
    """

    def __init__(
        self,
        client_factory: Callable[[], Any] | None = None,
        *,
        api_key_provider: KeyProvider | None = None,
        max_attempts: int = MAX_ATTEMPTS,
        backoff: tuple[float, ...] = BACKOFF_SECONDS,
        sleep: Callable[[float], bool] | None = None,
    ) -> None:
        self._api_key_provider = api_key_provider
        self._factory = client_factory or (lambda: _build_sdk_client(self._current_key()))
        self._max_attempts = max(1, max_attempts)
        self._backoff = backoff
        self._cancelled = threading.Event()
        self._sleep = sleep
        self._client: Any | None = None

    # ------------------------------------------------------------------ API pública

    def cancel(self) -> None:
        """Pede o cancelamento. Vale até alguém chamar `reset()`."""
        self._cancelled.set()

    def forget_client(self) -> None:
        """Descarta o cliente do SDK para que o próximo `run()` releia a chave.

        É o que faz a chave nova valer sem reiniciar o app (RF7).
        """
        self._client = None

    def reset(self) -> None:
        """Limpa um cancelamento anterior, liberando a instância para uma busca nova.

        Deve ser chamado **ao iniciar a busca** (quando o usuário clica em Buscar), não dentro do
        `run()`: entre enfileirar o worker e a chamada começar de fato existe uma janela em que o
        usuário pode cancelar, e limpar a flag no `run()` engoliria esse cancelamento.
        """
        self._cancelled.clear()

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def run(self, req: AgentRequest, sink: StreamSink | None = None) -> dict:
        """Envia o pedido e devolve a resposta crua (`model_dump()`).

        Com `sink`, a chamada vai em modo streaming (`stream=True`) e o texto é entregue em
        pedaços enquanto chega; o valor de retorno é o mesmo nos dois modos, para o resto do app
        não precisar saber a diferença.

        Levanta sempre uma subclasse de `CondorError`, com mensagem em português.
        Um cancelamento pedido **antes** do `run()` continua valendo: quem começa uma busca
        nova chama `reset()` primeiro (ver o aviso em `reset`).
        """
        client = self._ensure_client()
        ultima: CondorError | None = None

        for tentativa in range(1, self._max_attempts + 1):
            self._raise_if_cancelled()
            try:
                raw = self._stream(client, req, sink) if sink is not None else self._call(client, req)
            except CondorError as exc:
                ultima = exc
                if not exc.retryable or tentativa == self._max_attempts:
                    raise
                espera = self._backoff[min(tentativa - 1, len(self._backoff) - 1)]
                logger.warning(
                    "Tentativa %d de %d falhou (%s); repetindo em %.0fs.",
                    tentativa,
                    self._max_attempts,
                    type(exc).__name__,
                    espera,
                )
                if self._wait(espera):
                    raise CancelledError("Busca cancelada.") from exc
                if sink is not None:
                    sink.restart()  # a próxima tentativa recomeça o texto do zero
                continue

            self._raise_if_cancelled()
            return self._validated(raw)

        raise ultima or NetworkError("A busca não pôde ser concluída.")

    # ------------------------------------------------------------------ interno

    def _current_key(self) -> str | None:
        """A chave de agora — relida a cada criação de cliente, para `forget_client()` valer."""
        return self._api_key_provider() if self._api_key_provider is not None else None

    def _ensure_client(self) -> Any:
        """Cria o cliente do SDK uma vez. Falta de chave aparece aqui, como `AuthError`."""
        if self._client is None:
            try:
                self._client = self._factory()
            except Exception as exc:  # noqa: BLE001 — qualquer falha aqui é "não deu para iniciar"
                raise from_startup_error(exc) from exc
        return self._client

    def _call(self, client: Any, req: AgentRequest) -> Any:
        """Uma tentativa. Converte a exceção do SDK na nossa antes de sair."""
        try:
            return client.responses.create(**req.payload, timeout=req.timeout_s)
        except Exception as exc:  # noqa: BLE001 — traduzido logo abaixo
            raise translate(exc) from exc

    def _stream(self, client: Any, req: AgentRequest, sink: StreamSink) -> Any:
        """Uma tentativa em modo streaming. Devolve a resposta final do evento `response.completed`.

        Os eventos que interessam (API_NOTES §8): `response.output_text.delta` traz o pedaço de
        texto, `response.reasoning.search_results` conta quantas fontes já apareceram, e
        `response.completed` carrega a resposta inteira — é dela que sai o mesmo dict do modo
        normal. Qualquer outro tipo de evento é ignorado.
        """
        final: Any = None
        try:
            fluxo = client.responses.create(**req.payload, stream=True, timeout=req.timeout_s)
        except Exception as exc:  # noqa: BLE001 — traduzido como no modo normal
            raise translate(exc) from exc

        try:
            for evento in fluxo:
                if self._cancelled.is_set():
                    raise CancelledError("Busca cancelada.")
                tipo = getattr(evento, "type", "")
                if tipo == "response.output_text.delta":
                    sink.delta(str(getattr(evento, "delta", "") or ""))
                elif tipo == "response.reasoning.search_results":
                    quantas = len(getattr(evento, "results", None) or ())
                    sink.note(f"{quantas} fonte(s) encontradas…")
                elif tipo == "response.completed":
                    final = getattr(evento, "response", None)
                elif tipo == "response.failed":
                    raise from_stream_event(getattr(evento, "error", None))
        except CondorError:
            raise
        except Exception as exc:  # noqa: BLE001 — falha no meio do fluxo
            raise translate(exc) from exc
        finally:
            fechar = getattr(fluxo, "close", None)
            if callable(fechar):
                fechar()

        if final is None:
            raise NetworkError(
                "O fluxo da resposta terminou sem o evento final. Tente de novo; se persistir, "
                "desligue o streaming nas opções."
            )
        return final

    def _validated(self, raw: Any) -> dict:
        """Normaliza para dict e recusa resposta sem texto (API_NOTES §6)."""
        if hasattr(raw, "model_dump"):
            raw = raw.model_dump(mode="json")
        if not isinstance(raw, dict):
            raise NetworkError("A API devolveu uma resposta em formato inesperado.")
        if not parse(raw).text:
            raise EmptyResponseError(
                "A busca terminou sem texto de resposta. Tente reformular a pergunta "
                "ou usar uma profundidade maior."
            )
        return raw

    def _raise_if_cancelled(self) -> None:
        if self._cancelled.is_set():
            raise CancelledError("Busca cancelada.")

    def _wait(self, seconds: float) -> bool:
        """Espera o backoff. Devolve `True` se foi interrompida por cancelamento."""
        if self._sleep is not None:
            return bool(self._sleep(seconds))
        return self._cancelled.wait(seconds)
