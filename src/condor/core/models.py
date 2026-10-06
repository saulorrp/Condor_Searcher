"""Modelos de dados do Condor (TECHSPEC §8).

Camada pura: só `dataclasses` e tipos da stdlib. Nada de Qt, SDK, sqlite ou I/O.
As validações de combinação (prompt vazio, recency vs. datas, nº de domínios) ficam em
`core/prompt_builder.py` — aqui os campos só guardam valores.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Literal

Preset = Literal["fast", "low", "medium", "high", "xhigh"]
DomainMode = Literal["allow", "deny"]
Recency = Literal["hour", "day", "week", "month", "year"]
ContextSize = Literal["low", "medium", "high"]

#: Limite da API para `filters.search_domain_filter` (API_NOTES §3).
MAX_DOMAINS = 20

#: Faixa aceita por `max_results` no tool `web_search` (API_NOTES §3).
MIN_RESULTS = 1
MAX_RESULTS = 50

PRESETS: tuple[Preset, ...] = ("fast", "low", "medium", "high", "xhigh")
DOMAIN_MODES: tuple[DomainMode, ...] = ("allow", "deny")
RECENCIES: tuple[Recency, ...] = ("hour", "day", "week", "month", "year")
CONTEXT_SIZES: tuple[ContextSize, ...] = ("low", "medium", "high")


@dataclass(frozen=True)
class LocationOpt:
    """Localização do usuário enviada em `tools[0].user_location` (opcional)."""

    country: str  # ISO-3166 alfa-2, ex.: "PT"
    region: str = ""
    city: str = ""


@dataclass(frozen=True)
class SearchOptions:
    """Tudo o que o usuário escolhe no painel "Opções" (RF4)."""

    preset: Preset = "low"
    domains: tuple[str, ...] = ()  # já sem o "-" do modo denylist
    domain_mode: DomainMode = "allow"
    recency: Recency | None = None
    after: date | None = None
    before: date | None = None
    location: LocationOpt | None = None
    context_size: ContextSize = "medium"
    max_results: int = 15
    language: str = "pt-BR"
    output_format: str = "relatorio"
    priorities: tuple[str, ...] = ("primarias", "divergencias")
    custom_instructions: str = ""


@dataclass(frozen=True)
class AgentRequest:
    """Resultado do `prompt_builder`: o que o `services/client.py` vai enviar."""

    payload: dict
    briefing: str
    timeout_s: int


@dataclass(frozen=True)
class Source:
    """Um item de `search_results.results[]` (API_NOTES §4)."""

    id: int
    url: str
    title: str
    date: str | None
    last_updated: str | None
    snippet: str


@dataclass(frozen=True)
class Usage:
    """Consumo da chamada. `cost_usd` é `None` quando a API não informa."""

    input_tokens: int
    output_tokens: int
    search_calls: int
    cost_usd: float | None


@dataclass(frozen=True)
class SearchResult:
    """Resposta já interpretada pelo `response_parser`."""

    response_id: str
    model: str
    text: str
    sources: tuple[Source, ...]
    queries: tuple[str, ...]
    usage: Usage
    raw: dict = field(repr=False)


@dataclass(frozen=True)
class SearchRecord:
    """Linha do histórico (TECHSPEC §9)."""

    id: int
    created_at: datetime
    prompt: str
    options: SearchOptions
    md_path: Path
    cost_usd: float | None


# --------------------------------------------------------------------------- serialização


def options_to_dict(options: SearchOptions) -> dict[str, object]:
    """`SearchOptions` → dicionário pronto para JSON (datas em ISO, tuplas em lista).

    Mora aqui, e não nos `services`, porque é conversão pura: tanto o histórico (`storage.py`)
    quanto a última configuração (`settings_store.py`) precisam dela.
    """
    dados: dict[str, object] = {
        "preset": options.preset,
        "domains": list(options.domains),
        "domain_mode": options.domain_mode,
        "recency": options.recency,
        "after": options.after.isoformat() if options.after else None,
        "before": options.before.isoformat() if options.before else None,
        "context_size": options.context_size,
        "max_results": options.max_results,
        "language": options.language,
        "output_format": options.output_format,
        "priorities": list(options.priorities),
        "custom_instructions": options.custom_instructions,
        "location": None,
    }
    if options.location is not None:
        dados["location"] = {
            "country": options.location.country,
            "region": options.location.region,
            "city": options.location.city,
        }
    return dados


def options_from_dict(dados: dict) -> SearchOptions:
    """Dicionário → `SearchOptions`, caindo no default de cada campo que faltar ou estiver torto.

    Tolerante de propósito: configuração salva por uma versão anterior do app não deve impedir
    o app de abrir. Quem valida de verdade é o `core/prompt_builder.py`.
    """
    padrao = SearchOptions()
    if not isinstance(dados, dict):
        return padrao

    local = dados.get("location")
    location = None
    if isinstance(local, dict) and str(local.get("country", "")).strip():
        location = LocationOpt(
            country=str(local.get("country", "")).strip(),
            region=str(local.get("region") or ""),
            city=str(local.get("city") or ""),
        )

    return SearchOptions(
        preset=_one_of(dados.get("preset"), PRESETS, padrao.preset),  # type: ignore[arg-type]
        domains=_str_tuple(dados.get("domains")),
        domain_mode=_one_of(dados.get("domain_mode"), DOMAIN_MODES, padrao.domain_mode),  # type: ignore[arg-type]
        recency=_one_of(dados.get("recency"), RECENCIES, None),  # type: ignore[arg-type]
        after=_iso_date(dados.get("after")),
        before=_iso_date(dados.get("before")),
        location=location,
        context_size=_one_of(dados.get("context_size"), CONTEXT_SIZES, padrao.context_size),  # type: ignore[arg-type]
        max_results=_bounded_int(dados.get("max_results"), padrao.max_results),
        language=str(dados.get("language") or padrao.language),
        output_format=str(dados.get("output_format") or padrao.output_format),
        priorities=_str_tuple(dados.get("priorities"), padrao.priorities),
        custom_instructions=str(dados.get("custom_instructions") or ""),
    )


def _one_of(valor: object, aceitos: tuple[str, ...], padrao: str | None) -> str | None:
    return str(valor) if isinstance(valor, str) and valor in aceitos else padrao


def _str_tuple(valor: object, padrao: tuple[str, ...] = ()) -> tuple[str, ...]:
    if not isinstance(valor, list):
        return padrao
    return tuple(str(item).strip() for item in valor if str(item).strip())


def _iso_date(valor: object) -> date | None:
    if not isinstance(valor, str) or not valor.strip():
        return None
    try:
        return date.fromisoformat(valor.strip())
    except ValueError:
        return None


def _bounded_int(valor: object, padrao: int) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int):
        return padrao
    return valor if MIN_RESULTS <= valor <= MAX_RESULTS else padrao
