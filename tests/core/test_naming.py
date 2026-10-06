"""Testes de `core/naming.py`: nomes de arquivo seguros no Windows (TECHSPEC §9)."""

from __future__ import annotations

import re
from datetime import datetime

import pytest

from condor.core.naming import FALLBACK_SLUG, MAX_BASENAME, report_basename, slugify

#: Proibidos pelo Windows, mais o que não é ASCII imprimível.
PROIBIDOS = '<>:"/\\|?*'

QUANDO = datetime(2026, 10, 6, 11, 49)


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("Arquivo Histórico Ultramarino", "arquivo-historico-ultramarino"),
        ("Qual é a capital de Portugal?", "qual-e-a-capital-de-portugal"),
        ("  espaços   demais  ", "espacos-demais"),
        ("CAIXA ALTA", "caixa-alta"),
        ("ação, cedilha e ~til", "acao-cedilha-e-til"),
        ("a/b\\c:d*e?f", "a-b-c-d-e-f"),
        ("já-tem-hifen", "ja-tem-hifen"),
        ("hífens---repetidos", "hifens-repetidos"),
        ("123 456", "123-456"),
    ],
)
def test_slugify_normaliza(entrada: str, esperado: str) -> None:
    assert slugify(entrada) == esperado


@pytest.mark.parametrize("entrada", ["", "   ", "!!!", "???", "🙂🙂", "...", "---", "\n\t"])
def test_slug_sem_nada_aproveitavel_cai_no_fallback(entrada: str) -> None:
    assert slugify(entrada) == FALLBACK_SLUG


@pytest.mark.parametrize("reservado", ["CON", "nul", "Aux", "com1", "LPT9", "prn"])
def test_nomes_reservados_do_windows_sao_evitados(reservado: str) -> None:
    assert slugify(reservado) == FALLBACK_SLUG


def test_slug_respeita_o_tamanho_maximo() -> None:
    assert len(slugify("palavra " * 50, max_len=20)) <= 20


def test_slug_corta_na_fronteira_de_palavra() -> None:
    """Preferimos perder a última palavra a cortá-la pelo meio."""
    assert slugify("arquivo historico ultramarino lisboa", max_len=25) == "arquivo-historico"


def test_slug_de_palavra_unica_longa_e_cortado_mesmo_assim() -> None:
    slug = slugify("a" * 100, max_len=10)
    assert slug == "a" * 10


def test_slug_nunca_comeca_ou_termina_com_hifen() -> None:
    for entrada in ("---abc---", "?abc?", " abc ", "a" * 30 + " b"):
        slug = slugify(entrada, max_len=12)
        assert not slug.startswith("-") and not slug.endswith("-")


# ----------------------------------------------------------------- report_basename


def test_basename_tem_o_formato_do_techspec() -> None:
    nome = report_basename(QUANDO, "Como funciona o Arquivo Histórico Ultramarino?")
    assert nome == "2026-10-06_1149_como-funciona-o-arquivo-historico-ultramarino"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}_\d{4}_[a-z0-9-]+", nome)


def test_basename_respeita_80_caracteres() -> None:
    nome = report_basename(QUANDO, "palavra " * 60)
    assert len(nome) <= MAX_BASENAME


def test_basename_com_prompt_vazio_ainda_e_valido() -> None:
    assert report_basename(QUANDO, "   ") == f"2026-10-06_1149_{FALLBACK_SLUG}"


@pytest.mark.parametrize(
    "prompt",
    [
        'aspas "duplas" e <tags>',
        "barra/invertida\\e|pipe",
        "dois:pontos*asterisco?interrogacao",
        "ponto final.",
        "espaço no fim ",
    ],
)
def test_basename_nunca_contem_caractere_proibido_no_windows(prompt: str) -> None:
    nome = report_basename(QUANDO, prompt)
    assert not any(c in nome for c in PROIBIDOS)
    assert not nome.endswith((".", " ", "-", "_"))
    assert nome.isascii()


def test_basename_muda_com_o_minuto() -> None:
    a = report_basename(datetime(2026, 10, 6, 11, 49), "x")
    b = report_basename(datetime(2026, 10, 6, 11, 50), "x")
    assert a != b
