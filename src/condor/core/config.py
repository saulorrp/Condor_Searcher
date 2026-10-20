"""Leitura dos `config/*.toml` para dataclasses (TECHSPEC §7).

Recebe caminhos, não os descobre: quem sabe onde o app está instalado é a camada de cima.
A única I/O aqui é ler os TOML indicados; nada de rede, Qt ou sqlite.

Erros de configuração (valor fora do domínio, chave faltando) viram `ValueError` com mensagem
em português. Problemas que não impedem o uso — um pacote com mais domínios do que a API aceita,
um pacote vazio — viram aviso no `logging`, não exceção.
"""

from __future__ import annotations

import logging
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from condor.core.models import (
    CONTEXT_SIZES,
    DOMAIN_MODES,
    MAX_DOMAINS,
    MAX_RESULTS,
    MIN_RESULTS,
    PRESETS,
    RECENCIES,
    LocationOpt,
    SearchOptions,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourcePack:
    """Um pacote de domínios de `config/source_packs.toml`."""

    key: str
    label: str
    description: str
    domains: tuple[str, ...]
    mode: str = "allow"  # "allow" | "deny"


@dataclass(frozen=True)
class Snippet:
    """Um texto do briefing: `label` vai para a UI, `text` para o `<briefing>`."""

    key: str
    label: str
    text: str


@dataclass(frozen=True)
class Snippets:
    """Textos do briefing agrupados por idioma, formato e prioridade (TECHSPEC §6)."""

    languages: tuple[Snippet, ...]
    formats: tuple[Snippet, ...]
    priorities: tuple[Snippet, ...]

    def language(self, key: str) -> Snippet:
        return _pick(self.languages, key, "Idioma")

    def output_format(self, key: str) -> Snippet:
        return _pick(self.formats, key, "Formato")

    def priority(self, key: str) -> Snippet:
        return _pick(self.priorities, key, "Prioridade")


@dataclass(frozen=True)
class Limits:
    """Freios de uso. Hoje só o teto diário da linha de comando (F11)."""

    #: Teto de gasto por dia, em US$. `0` desliga.
    daily_usd: float = 0.0

    @property
    def enabled(self) -> bool:
        return self.daily_usd > 0


@dataclass(frozen=True)
class Defaults:
    """Conteúdo de `config/defaults.toml`."""

    output_dir: Path
    timeouts: Mapping[str, int]
    options: SearchOptions
    source_packs: tuple[str, ...]  # pacotes marcados por padrão
    location_shortcut: LocationOpt  # oferecido na UI mesmo com a localização desligada
    limits: Limits = Limits()


# --------------------------------------------------------------------------- leitura


def load_defaults(path: Path) -> Defaults:
    """Lê `defaults.toml`. `ValueError` se algum valor estiver fora do domínio."""
    data = _read_toml(path)
    search = _table(data, "search", path)
    timeouts = _table(data, "timeouts", path)
    output = _table(data, "output", path)
    location = _table(data, "location", path)

    faltando = [p for p in PRESETS if p not in timeouts]
    if faltando:
        raise ValueError(f"{path.name}: falta o timeout dos presets {', '.join(faltando)} em [timeouts].")
    for name in PRESETS:
        if not isinstance(timeouts[name], int) or timeouts[name] <= 0:
            raise ValueError(
                f"{path.name}: [timeouts].{name} deve ser um número inteiro de segundos acima de 0."
            )

    max_results = search.get("max_results", 15)
    if not isinstance(max_results, int) or not MIN_RESULTS <= max_results <= MAX_RESULTS:
        raise ValueError(
            f"{path.name}: [search].max_results deve ser um inteiro de {MIN_RESULTS} a {MAX_RESULTS} "
            f"(recebi {max_results!r})."
        )

    recency = search.get("recency", "") or None
    if recency is not None and recency not in RECENCIES:
        raise ValueError(
            f"{path.name}: [search].recency deve ser vazio (qualquer período) ou um de "
            f"{', '.join(RECENCIES)} (recebi {recency!r})."
        )

    domains = _str_list(search, "domains", path)
    if len(domains) > MAX_DOMAINS:
        logger.warning(
            "%s: [search].domains tem %d domínios; a API aceita %d por busca — o excedente será cortado.",
            path.name,
            len(domains),
            MAX_DOMAINS,
        )

    options = SearchOptions(
        preset=_choice(search, "preset", PRESETS, path),  # type: ignore[arg-type]
        domains=domains,
        domain_mode=_choice(search, "domain_mode", DOMAIN_MODES, path),  # type: ignore[arg-type]
        recency=recency,  # type: ignore[arg-type]
        context_size=_choice(search, "context_size", CONTEXT_SIZES, path),  # type: ignore[arg-type]
        max_results=max_results,
        language=str(search.get("language", "pt-BR")),
        output_format=str(search.get("output_format", "relatorio")),
        priorities=_str_list(search, "priorities", path),
        location=_location(location) if location.get("enabled", False) else None,
    )

    folder = str(output.get("folder", "~/Documents/CondorSearcher"))
    return Defaults(
        output_dir=Path(folder).expanduser(),
        timeouts=MappingProxyType({name: int(timeouts[name]) for name in PRESETS}),
        options=options,
        source_packs=_str_list(search, "source_packs", path),
        location_shortcut=_location(location),
        limits=_limits(data.get("limits"), path),
    )


def load_source_packs(path: Path) -> tuple[SourcePack, ...]:
    """Lê `source_packs.toml` na ordem do arquivo. Pacotes inválidos são avisados e ignorados."""
    data = _read_toml(path)
    packs: list[SourcePack] = []
    for key, raw in data.items():
        if not isinstance(raw, dict):
            logger.warning("%s: ignorando %r — cada pacote deve ser uma seção.", path.name, key)
            continue

        domains = _str_list(raw, "domains", path)
        if not domains:
            logger.warning("%s: pacote %r não tem domínios — ignorado.", path.name, key)
            continue
        if len(domains) > MAX_DOMAINS:
            logger.warning(
                "%s: o pacote %r tem %d domínios e a API aceita %d por busca; "
                "ao usá-lo sozinho será preciso cortar a lista.",
                path.name,
                key,
                len(domains),
                MAX_DOMAINS,
            )

        mode = str(raw.get("mode", "allow"))
        if mode not in DOMAIN_MODES:
            logger.warning(
                "%s: pacote %r tem mode=%r; use %s. Assumindo allow.",
                path.name,
                key,
                mode,
                " ou ".join(DOMAIN_MODES),
            )
            mode = "allow"

        packs.append(
            SourcePack(
                key=key,
                label=str(raw.get("label", key)),
                description=str(raw.get("description", "")),
                domains=domains,
                mode=mode,
            )
        )
    if not packs:
        logger.warning("%s: nenhum pacote de fontes válido encontrado.", path.name)
    return tuple(packs)


def load_snippets(path: Path) -> Snippets:
    """Lê `prompt_snippets.toml`. `ValueError` se faltar um dos três grupos."""
    data = _read_toml(path)
    return Snippets(
        languages=_snippet_group(data, "languages", path),
        formats=_snippet_group(data, "formats", path),
        priorities=_snippet_group(data, "priorities", path),
    )


# --------------------------------------------------------------------------- auxiliares


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Arquivo de configuração não encontrado: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"{path.name}: TOML inválido — {exc}") from exc


def _table(data: dict[str, Any], name: str, path: Path) -> dict[str, Any]:
    table = data.get(name)
    if table is None:
        raise ValueError(f"{path.name}: falta a seção [{name}].")
    if not isinstance(table, dict):
        raise ValueError(f"{path.name}: [{name}] deve ser uma seção.")
    return table


def _choice(table: dict[str, Any], key: str, allowed: tuple[str, ...], path: Path) -> str:
    value = table.get(key, allowed[0])
    if value not in allowed:
        raise ValueError(f"{path.name}: {key} deve ser um de {', '.join(allowed)} (recebi {value!r}).")
    return str(value)


def _str_list(table: dict[str, Any], key: str, path: Path) -> tuple[str, ...]:
    value = table.get(key, [])
    if isinstance(value, str) or not isinstance(value, list):
        raise ValueError(f"{path.name}: {key} deve ser uma lista de textos (recebi {value!r}).")
    return tuple(str(item).strip() for item in value if str(item).strip())


def _limits(table: Any, path: Path) -> Limits:
    """Seção `[limits]`, opcional: sem ela, não há teto."""
    if table is None:
        return Limits()
    if not isinstance(table, dict):
        raise ValueError(f"{path.name}: [limits] deve ser uma seção.")
    valor = table.get("daily_usd", 0)
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or valor < 0:
        raise ValueError(
            f"{path.name}: [limits].daily_usd deve ser um número de dólares maior ou igual a 0 "
            f"(recebi {valor!r})."
        )
    return Limits(daily_usd=float(valor))


def _location(table: dict[str, Any]) -> LocationOpt:
    return LocationOpt(
        country=str(table.get("country", "")).upper(),
        region=str(table.get("region", "")),
        city=str(table.get("city", "")),
    )


def _snippet_group(data: dict[str, Any], name: str, path: Path) -> tuple[Snippet, ...]:
    table = data.get(name)
    if not isinstance(table, dict) or not table:
        raise ValueError(f"{path.name}: falta a seção [{name}] com pelo menos um item.")
    group: list[Snippet] = []
    for key, raw in table.items():
        if not isinstance(raw, dict) or "text" not in raw:
            raise ValueError(f"{path.name}: [{name}.{key}] precisa de um campo text.")
        group.append(Snippet(key=key, label=str(raw.get("label", key)), text=str(raw["text"]).strip()))
    return tuple(group)


def _pick(group: tuple[Snippet, ...], key: str, what: str) -> Snippet:
    for snippet in group:
        if snippet.key == key:
            return snippet
    disponiveis = ", ".join(s.key for s in group)
    raise KeyError(f"{what} desconhecido: {key!r}. Disponíveis: {disponiveis}.")
