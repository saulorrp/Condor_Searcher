"""Como a linha de comando responde: texto para humano, JSON para agente (F11).

O JSON é **contrato**: um agente vai ler estes campos sem supervisão. Acrescentar campo é
seguro; renomear ou remover quebra quem já dependia. Os nomes ficam em inglês porque são chaves
de dados, não texto de tela.

Nada aqui imprime a chave da API: o payload não a contém (F2) e o `scrub` de `services/errors.py`
já limpa as mensagens de erro.
"""

from __future__ import annotations

import json
from typing import Any

from condor.core.models import SearchRecord, SearchResult

#: Quantas fontes entram no JSON por padrão. O relatório `.md` tem todas.
MAX_SOURCES_JSON = 20


def dump(dados: dict[str, Any]) -> str:
    """JSON de uma linha só por chamada, com acentos preservados."""
    return json.dumps(dados, ensure_ascii=False, indent=2)


def search_payload(record: SearchRecord, result: SearchResult, texto_completo: bool) -> dict[str, Any]:
    """Resultado de uma busca, para consumo por agente."""
    return {
        "ok": True,
        "id": record.id,
        "created_at": record.created_at.isoformat(timespec="seconds"),
        "prompt": record.prompt,
        "preset": record.options.preset,
        "md_path": str(record.md_path),
        "json_path": str(record.md_path.with_suffix(".json")),
        "cost_usd": record.cost_usd,
        "usage": {
            "input_tokens": result.usage.input_tokens,
            "output_tokens": result.usage.output_tokens,
            "search_calls": result.usage.search_calls,
        },
        "queries": list(result.queries),
        "sources": [
            {"id": s.id, "url": s.url, "title": s.title, "date": s.date}
            for s in result.sources[:MAX_SOURCES_JSON]
        ],
        "sources_total": len(result.sources),
        "text": result.text if texto_completo else _resumo(result.text),
    }


def record_payload(record: SearchRecord) -> dict[str, Any]:
    """Uma linha do histórico."""
    return {
        "id": record.id,
        "created_at": record.created_at.isoformat(timespec="seconds"),
        "prompt": record.prompt,
        "preset": record.options.preset,
        "cost_usd": record.cost_usd,
        "md_path": str(record.md_path),
    }


def error_payload(mensagem: str, codigo: str) -> dict[str, Any]:
    """Falha, no mesmo formato para qualquer comando."""
    return {"ok": False, "error": mensagem, "error_code": codigo}


def human_search(record: SearchRecord, result: SearchResult) -> str:
    """Resumo para quem está lendo no terminal."""
    custo = f"US$ {record.cost_usd:.5f}" if record.cost_usd is not None else "custo não informado"
    linhas = [
        f"Busca #{record.id} concluída — {custo}",
        f"Relatório: {record.md_path}",
        f"Fontes: {len(result.sources)} · buscas: {result.usage.search_calls} · "
        f"tokens: {result.usage.input_tokens}/{result.usage.output_tokens}",
        "",
        result.text,
    ]
    return "\n".join(linhas)


def human_history(registros: tuple[SearchRecord, ...]) -> str:
    if not registros:
        return "Nenhuma busca no histórico ainda."
    linhas = []
    for r in registros:
        custo = f"US$ {r.cost_usd:.5f}" if r.cost_usd is not None else "—"
        quando = r.created_at.strftime("%d/%m/%Y %H:%M")
        linhas.append(f"{r.id:>4}  {quando}  {r.options.preset:<6}  {custo:>12}  {_uma_linha(r.prompt)}")
    return "\n".join(linhas)


def _resumo(texto: str, limite: int = 600) -> str:
    """Começo do texto, para o JSON não carregar um relatório inteiro sem necessidade."""
    limpo = texto.strip()
    return limpo if len(limpo) <= limite else limpo[:limite].rstrip() + "…"


def _uma_linha(texto: str, limite: int = 70) -> str:
    junto = " ".join(texto.split())
    return junto if len(junto) <= limite else junto[: limite - 1] + "…"
