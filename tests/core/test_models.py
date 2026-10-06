"""Testes de `core/models.py`: defaults do RF4 e imutabilidade das dataclasses."""

from __future__ import annotations

import dataclasses
import json
from datetime import date

import pytest

from condor.core.models import (
    CONTEXT_SIZES,
    MAX_DOMAINS,
    MAX_RESULTS,
    MIN_RESULTS,
    PRESETS,
    LocationOpt,
    SearchOptions,
    Source,
    Usage,
    options_from_dict,
    options_to_dict,
)


def test_defaults_do_search_options_batem_com_o_rf4() -> None:
    options = SearchOptions()
    assert options.preset == "low"
    assert options.domains == ()
    assert options.domain_mode == "allow"
    assert options.recency is None
    assert options.after is None and options.before is None
    assert options.location is None
    assert options.context_size == "medium"
    assert options.max_results == 15
    assert options.language == "pt-BR"
    assert options.output_format == "relatorio"
    assert options.priorities == ("primarias", "divergencias")
    assert options.custom_instructions == ""


def test_constantes_refletem_os_limites_da_api() -> None:
    assert MAX_DOMAINS == 20
    assert (MIN_RESULTS, MAX_RESULTS) == (1, 50)
    assert PRESETS == ("fast", "low", "medium", "high", "xhigh")
    assert CONTEXT_SIZES == ("low", "medium", "high")


def test_search_options_e_imutavel() -> None:
    options = SearchOptions()
    with pytest.raises(dataclasses.FrozenInstanceError):
        options.preset = "high"  # type: ignore[misc]


def test_dataclasses_sao_comparaveis_por_valor() -> None:
    assert LocationOpt("PT", "Lisboa") == LocationOpt("PT", "Lisboa")
    assert SearchOptions(after=date(2026, 1, 31)) != SearchOptions()


def test_source_e_usage_aceitam_campos_ausentes_como_none() -> None:
    source = Source(id=1, url="https://x.pt", title="t", date=None, last_updated=None, snippet="")
    assert source.date is None
    assert Usage(input_tokens=1, output_tokens=2, search_calls=1, cost_usd=None).cost_usd is None


# ----------------------------------------------------------------- serialização (F6)


def test_options_round_trip_preserva_tudo() -> None:

    opcoes = SearchOptions(
        preset="xhigh",
        domains=("a.pt", "b.pt"),
        domain_mode="deny",
        after=date(2026, 1, 31),
        before=date(2026, 6, 30),
        location=LocationOpt("PT", "Lisboa", "Lisboa"),
        context_size="high",
        max_results=50,
        language="en",
        output_format="tabela",
        priorities=("foruns",),
        custom_instructions="x",
    )
    assert options_from_dict(options_to_dict(opcoes)) == opcoes


def test_options_to_dict_e_serializavel_em_json() -> None:

    texto = json.dumps(options_to_dict(SearchOptions(after=date(2026, 1, 31))))
    assert '"after": "2026-01-31"' in texto


@pytest.mark.parametrize(
    "entrada",
    [{}, None, "texto", [1], {"preset": None}, {"domains": "a.pt"}, {"location": {"country": ""}}],
)
def test_options_from_dict_tolera_lixo(entrada) -> None:

    assert options_from_dict(entrada) == SearchOptions()


def test_options_from_dict_descarta_valor_fora_do_dominio() -> None:

    opcoes = options_from_dict(
        {"preset": "turbo", "context_size": "gigante", "max_results": 0, "recency": "decada"}
    )
    assert (opcoes.preset, opcoes.context_size, opcoes.max_results, opcoes.recency) == (
        "low",
        "medium",
        15,
        None,
    )


def test_options_from_dict_aceita_data_invalida_como_none() -> None:

    assert options_from_dict({"after": "31/01/2026", "before": ""}).after is None
