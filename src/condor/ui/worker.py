"""A busca fora da thread da interface (TECHSPEC RF1: "A UI nunca congela").

O fluxo em si mora em `services/search_runner.py`, sem Qt nenhum — aqui ele só é embalado num
`QRunnable` e convertido em sinais. `SearchContext` e `execute_search` continuam sendo importáveis
deste módulo por conveniência de quem já os usava.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from condor.core.models import SearchOptions
from condor.services.errors import AuthError, CancelledError, CondorError
from condor.services.search_runner import SearchContext, execute_search

logger = logging.getLogger(__name__)

__all__ = ["SearchContext", "SearchWorker", "SignalSink", "WorkerSignals", "execute_search"]


class WorkerSignals(QObject):
    """Sinais do worker. `QRunnable` não é `QObject`, então eles moram aqui."""

    #: `SearchRecord` da busca concluída (passa como `object` porque não é tipo do Qt).
    finished = Signal(object)
    #: Mensagem de erro já em português, pronta para exibir.
    failed = Signal(str)
    #: Falha de autenticação — a janela oferece "Trocar chave…" (RF7). **Substitui** o `failed`
    #: nesse caso: emitir os dois abriria duas caixas de diálogo para o mesmo erro.
    auth_failed = Signal(str)
    #: Texto curto para a barra de status.
    progress = Signal(str)
    #: O usuário cancelou; a janela só volta ao estado normal, sem caixa de erro.
    cancelled = Signal()
    #: Pedaço de texto recebido em modo streaming.
    delta = Signal(str)
    #: Uma tentativa falhou e outra vai começar: o texto mostrado até aqui não vale mais.
    restarted = Signal()


class SignalSink:
    """Liga o `StreamSink` do cliente aos sinais do worker (protocolo de `services/client.py`)."""

    def __init__(self, signals: WorkerSignals) -> None:
        self._signals = signals

    def delta(self, texto: str) -> None:
        if texto:
            self._signals.delta.emit(texto)

    def restart(self) -> None:
        self._signals.restarted.emit()

    def note(self, mensagem: str) -> None:
        self._signals.progress.emit(mensagem)


class SearchWorker(QRunnable):
    """Roda uma busca no `QThreadPool` e reporta por sinais."""

    def __init__(
        self,
        ctx: SearchContext,
        prompt: str,
        options: SearchOptions,
        stream: bool = True,
    ) -> None:
        super().__init__()
        self.signals = WorkerSignals()
        self._ctx = ctx
        self._prompt = prompt
        self._options = options
        self._sink = SignalSink(self.signals) if stream else None

    @Slot()
    def run(self) -> None:  # noqa: D102 — contrato do QRunnable
        try:
            record = execute_search(
                self._ctx,
                self._prompt,
                self._options,
                self.signals.progress.emit,
                self._sink,
            )
        except CancelledError:
            self.signals.cancelled.emit()
        except AuthError as exc:
            self.signals.auth_failed.emit(str(exc))
        except (CondorError, ValueError) as exc:
            self.signals.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 — um erro aqui não pode derrubar a thread
            logger.exception("Falha inesperada na busca")
            self.signals.failed.emit(f"Falha inesperada: {exc}")
        else:
            self.signals.finished.emit(record)
