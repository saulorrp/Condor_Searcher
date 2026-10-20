"""O fluxo de uma busca, do prompt ao arquivo salvo (TECHSPEC §7).

Vive aqui, e não em `ui/`, porque **não depende de interface nenhuma**: a janela (`ui/worker.py`)
e a linha de comando (`cli/`) usam exatamente esta função. Foi o que permitiu a F11 — um agente
rodando sem ninguém na frente do computador percorre o mesmo caminho que o botão Buscar.

Nada de Qt aqui. O progresso é relatado por um callback simples, e o streaming por um `StreamSink`
(ver `services/client.py`); quem chama decide o que fazer com cada um.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime

from condor.core.config import Snippets
from condor.core.markdown_report import render
from condor.core.models import SearchOptions, SearchRecord
from condor.core.prompt_builder import build
from condor.core.response_parser import parse
from condor.services.client import AgentClient, StreamSink
from condor.services.storage import Storage

logger = logging.getLogger(__name__)

Progress = Callable[[str], None]


@dataclass(frozen=True)
class SearchContext:
    """Tudo o que uma busca precisa. Injetado para os testes trocarem o cliente por um falso."""

    client: AgentClient
    storage: Storage
    snippets: Snippets
    timeouts: Mapping[str, int]


def execute_search(
    ctx: SearchContext,
    prompt: str,
    options: SearchOptions,
    progress: Progress | None = None,
    sink: StreamSink | None = None,
) -> SearchRecord:
    """Monta, envia, interpreta, renderiza e grava — o fluxo do TECHSPEC §7.

    Levanta `ValueError` (validação das opções) ou `CondorError` (API, disco).
    """
    aviso = progress or (lambda _: None)

    aviso("Montando a busca…")
    req = build(prompt, options, ctx.snippets, ctx.timeouts)

    aviso(f"Consultando a Perplexity (preset {options.preset})…")
    raw = ctx.client.run(req, sink)

    aviso("Interpretando a resposta…")
    result = parse(raw)

    aviso("Gerando o relatório…")
    criado_em = datetime.now()
    md = render(result, prompt, options, req.briefing, criado_em)

    aviso("Salvando…")
    record = ctx.storage.save(result, md, prompt, options, created_at=criado_em)
    logger.info("Busca concluída: %s", record.md_path.name)
    return record
