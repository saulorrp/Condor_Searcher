"""Converte o JSON cru da Agent API em `SearchResult` (API_NOTES §4).

Princípio: **nunca quebrar por causa da resposta**. A API devolve campos que o SDK não tipa e
tipos de item que ainda não existiam quando isto foi escrito; tudo o que não reconhecemos é
ignorado em silêncio, e tudo o que falta vira um default vazio. Um relatório com uma fonte sem
data é útil; uma exceção no meio da busca não é.

A única coisa que o parser não faz é julgar: texto vazio devolve `text=""`, e quem decide se
isso é um erro é o `services/client.py` (RF6 → `EmptyResponseError`).
"""

from __future__ import annotations

import logging
from typing import Any

from condor.core.models import SearchResult, Source, Usage

logger = logging.getLogger(__name__)

#: Ferramentas de `usage.tool_calls_details` que contam como "busca" no rodapé (RF2).
_SEARCH_TOOL_PREFIX = "search"


def parse(raw: dict) -> SearchResult:
    """Lê a resposta crua (`resp.model_dump()`) e devolve o resultado já utilizável."""
    output = _items(raw.get("output"))
    sources = _sources(output)
    return SearchResult(
        response_id=_text_of(raw.get("id")),
        model=_text_of(raw.get("model")),
        text=_answer(output),
        sources=sources,
        queries=_queries(output),
        usage=_usage(raw.get("usage"), output),
        raw=raw,
    )


# --------------------------------------------------------------------------- texto


def _answer(output: list[dict]) -> str:
    """Concatena o `output_text` dos itens `message` — equivalente ao `resp.output_text`."""
    partes: list[str] = []
    for item in output:
        if item.get("type") != "message":
            continue
        for bloco in _items(item.get("content")):
            if bloco.get("type") == "output_text":
                texto = _text_of(bloco.get("text"))
                if texto:
                    partes.append(texto)
    return "\n".join(partes).strip()


# --------------------------------------------------------------------------- fontes


def _sources(output: list[dict]) -> tuple[Source, ...]:
    """Junta todos os itens `search_results`, deduplica por URL e ordena por `id`.

    Dois cuidados do API_NOTES §4: os `id` são contíguos *dentro de cada item*, então com vários
    itens o mesmo número pode aparecer para URLs diferentes — nesse caso o primeiro vence e o
    conflito é registrado, porque trocar o destino de uma citação é pior do que perder uma fonte.
    Resultados sem `id` utilizável entram no fim, numerados depois do maior `id` válido.
    """
    por_url: dict[str, dict[str, Any]] = {}
    por_id: dict[int, str] = {}
    sem_id: list[dict[str, Any]] = []

    for item in output:
        if item.get("type") != "search_results":
            continue
        for bruto in _items(item.get("results")):
            url = _text_of(bruto.get("url"))
            if not url or url in por_url:
                continue

            campos = {
                "url": url,
                "title": _text_of(bruto.get("title")),
                "date": _optional_text(bruto.get("date")),
                "last_updated": _optional_text(bruto.get("last_updated")),
                "snippet": _text_of(bruto.get("snippet")),
            }

            ident = _as_int(bruto.get("id"))
            if ident is None:
                sem_id.append(campos)
                continue
            if ident in por_id:
                logger.warning(
                    "Dois resultados com id=%d (%s e %s); mantendo o primeiro para não trocar "
                    "o destino da citação [%d].",
                    ident,
                    por_id[ident],
                    url,
                    ident,
                )
                continue
            por_id[ident] = url
            por_url[url] = {"id": ident, **campos}

    proximo = max(por_id, default=0) + 1
    for campos in sem_id:
        por_url[campos["url"]] = {"id": proximo, **campos}
        proximo += 1

    return tuple(Source(**campos) for campos in sorted(por_url.values(), key=lambda c: c["id"]))


def _queries(output: list[dict]) -> tuple[str, ...]:
    """Todas as buscas que o agente fez, na ordem, sem repetir."""
    vistas: list[str] = []
    for item in output:
        if item.get("type") != "search_results":
            continue
        valor = item.get("queries")
        if not isinstance(valor, list):
            continue
        for query in valor:
            texto = _text_of(query)
            if texto and texto not in vistas:
                vistas.append(texto)
    return tuple(vistas)


# --------------------------------------------------------------------------- consumo


def _usage(bruto: Any, output: list[dict]) -> Usage:
    """Monta o `Usage`. Sem `usage`, conta as buscas pelos itens e deixa o custo em `None`."""
    usage = bruto if isinstance(bruto, dict) else {}
    return Usage(
        input_tokens=_as_int(usage.get("input_tokens")) or 0,
        output_tokens=_as_int(usage.get("output_tokens")) or 0,
        search_calls=_search_calls(usage, output),
        cost_usd=_cost(usage),
    )


def _search_calls(usage: dict[str, Any], output: list[dict]) -> int:
    """Soma as invocações das ferramentas de busca; sem essa informação, conta os itens."""
    detalhes = usage.get("tool_calls_details")
    if isinstance(detalhes, dict):
        total = 0
        encontrou = False
        for nome, dados in detalhes.items():
            if not str(nome).startswith(_SEARCH_TOOL_PREFIX) or not isinstance(dados, dict):
                continue
            encontrou = True
            total += _as_int(dados.get("invocation")) or 0
        if encontrou:
            return total
    return sum(1 for item in output if item.get("type") == "search_results")


def _cost(usage: dict[str, Any]) -> float | None:
    """`usage.cost.total_cost`, ou `None` se a API não informar (API_NOTES §4)."""
    cost = usage.get("cost")
    if not isinstance(cost, dict):
        return None
    return _as_float(cost.get("total_cost"))


# --------------------------------------------------------------------------- auxiliares


def _items(valor: Any) -> list[dict]:
    """Lista de dicionários, descartando o que não for dicionário (e o que não for lista)."""
    if not isinstance(valor, list):
        return []
    return [item for item in valor if isinstance(item, dict)]


def _text_of(valor: Any) -> str:
    if valor is None or isinstance(valor, (dict, list, bool)):
        return ""
    return str(valor).strip()


def _optional_text(valor: Any) -> str | None:
    texto = _text_of(valor)
    return texto or None


def _as_int(valor: Any) -> int | None:
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return None


def _as_float(valor: Any) -> float | None:
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    try:
        return float(str(valor).strip())
    except (TypeError, ValueError):
        return None
