"""Flags da linha de comando → `SearchOptions` (TECHSPEC RF4).

Mesmas opções do painel gráfico, mesmos valores. Quem valida a combinação continua sendo o
`core/prompt_builder`: aqui só se traduz texto digitado em dataclass, e os erros de formato
(data impossível, pacote inexistente) viram `ValueError` em português.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime

from condor.core.config import Defaults, SourcePack
from condor.core.models import LocationOpt, SearchOptions

#: Formato de data aceito na linha de comando: o brasileiro, como no briefing dos relatórios.
DATE_FORMAT = "%d/%m/%Y"


def add_search_flags(parser: argparse.ArgumentParser, defaults: Defaults) -> None:
    """Acrescenta ao parser todas as opções de busca do RF4."""
    padrao = defaults.options

    parser.add_argument(
        "--preset",
        choices=["fast", "low", "medium", "high", "xhigh"],
        default=padrao.preset,
        help=f"profundidade da busca (padrão: {padrao.preset})",
    )
    parser.add_argument(
        "--pacote",
        action="append",
        default=[],
        metavar="CHAVE",
        help="pacote de fontes de config/source_packs.toml (pode repetir)",
    )
    parser.add_argument(
        "--dominio",
        action="append",
        default=[],
        metavar="DOMINIO",
        help="domínio avulso, sem o '-' (pode repetir)",
    )
    parser.add_argument(
        "--modo",
        choices=["allow", "deny"],
        default=padrao.domain_mode,
        help="allow = somente estes domínios; deny = excluir estes",
    )
    parser.add_argument(
        "--periodo",
        choices=["hour", "day", "week", "month", "year"],
        default=padrao.recency,
        help="recorte de tempo; não combina com --de/--ate",
    )
    parser.add_argument("--de", metavar="DD/MM/AAAA", help="data inicial das publicações")
    parser.add_argument("--ate", metavar="DD/MM/AAAA", help="data final das publicações")
    parser.add_argument(
        "--leitura",
        choices=["low", "medium", "high"],
        default=padrao.context_size,
        help=f"profundidade de leitura das páginas (padrão: {padrao.context_size})",
    )
    parser.add_argument(
        "--max-resultados",
        type=int,
        default=padrao.max_results,
        metavar="N",
        help=f"de 1 a 50 (padrão: {padrao.max_results})",
    )
    parser.add_argument(
        "--idioma", default=padrao.language, help=f"chave de [languages] (padrão: {padrao.language})"
    )
    parser.add_argument(
        "--formato",
        default=padrao.output_format,
        help=f"chave de [formats] (padrão: {padrao.output_format})",
    )
    parser.add_argument(
        "--prioridade",
        action="append",
        default=None,
        metavar="CHAVE",
        help=f"chave de [priorities] (pode repetir; padrão: {', '.join(padrao.priorities)})",
    )
    parser.add_argument(
        "--local",
        metavar="PAIS[,REGIAO[,CIDADE]]",
        help='localização enviada à busca, ex.: "PT,Lisboa,Lisboa"',
    )
    parser.add_argument(
        "--instrucoes",
        metavar="TEXTO",
        help="instruções de sistema próprias (substituem as do preset; as regras de citação são reanexadas)",
    )


def options_from_args(
    args: argparse.Namespace,
    packs: tuple[SourcePack, ...],
    defaults: Defaults,
) -> SearchOptions:
    """Monta o `SearchOptions` a partir das flags já analisadas."""
    return SearchOptions(
        preset=args.preset,
        domains=_domains(args, packs),
        domain_mode=args.modo,
        recency=args.periodo,
        after=_parse_date(args.de, "--de"),
        before=_parse_date(args.ate, "--ate"),
        location=_parse_location(args.local),
        context_size=args.leitura,
        max_results=args.max_resultados,
        language=args.idioma,
        output_format=args.formato,
        priorities=(tuple(args.prioridade) if args.prioridade is not None else defaults.options.priorities),
        custom_instructions=(args.instrucoes or "").strip(),
    )


def _domains(args: argparse.Namespace, packs: tuple[SourcePack, ...]) -> tuple[str, ...]:
    """União dos pacotes escolhidos com os domínios avulsos, na ordem e sem repetir."""
    por_chave = {p.key: p for p in packs}
    escolhidos: list[str] = []

    for chave in args.pacote:
        pack = por_chave.get(chave)
        if pack is None:
            disponiveis = ", ".join(sorted(por_chave)) or "(nenhum)"
            raise ValueError(f"Pacote de fontes desconhecido: {chave!r}. Disponíveis: {disponiveis}.")
        escolhidos += [d for d in pack.domains if d not in escolhidos]

    for bruto in args.dominio:
        dominio = bruto.strip().lstrip("-").strip()
        if dominio and dominio not in escolhidos:
            escolhidos.append(dominio)
    return tuple(escolhidos)


def _parse_date(valor: str | None, flag: str) -> date | None:
    if not valor:
        return None
    try:
        return datetime.strptime(valor.strip(), DATE_FORMAT).date()
    except ValueError as exc:
        raise ValueError(f"{flag}: data inválida {valor!r}. Use DD/MM/AAAA, como 31/01/2026.") from exc


def _parse_location(valor: str | None) -> LocationOpt | None:
    """`"PT"`, `"PT,Lisboa"` ou `"PT,Lisboa,Lisboa"`."""
    if not valor:
        return None
    partes = [p.strip() for p in valor.split(",")]
    if not partes[0]:
        raise ValueError('--local: informe ao menos o país, como "PT" ou "PT,Lisboa,Lisboa".')
    if len(partes) > 3:
        raise ValueError('--local: use no máximo PAIS,REGIAO,CIDADE — ex.: "PT,Lisboa,Lisboa".')
    pais, regiao, cidade = (partes + ["", ""])[:3]
    return LocationOpt(country=pais.upper(), region=regiao, city=cidade)
