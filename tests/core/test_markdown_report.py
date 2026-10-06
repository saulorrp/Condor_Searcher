"""Testes de `core/markdown_report.py` (TECHSPEC RF3, API_NOTES §5)."""

from __future__ import annotations

import dataclasses
import json
from datetime import date, datetime
from pathlib import Path

import pytest
import yaml  # só nos testes: confirma que o front matter é YAML de verdade

from condor.core.config import load_defaults, load_snippets
from condor.core.markdown_report import link_citations, render
from condor.core.models import LocationOpt, SearchOptions, SearchResult, Source, Usage
from condor.core.prompt_builder import build
from condor.core.response_parser import parse

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
FIXTURES = ROOT / "tests" / "fixtures"
GOLDEN = FIXTURES / "report_expected.md"

QUANDO = datetime(2026, 10, 6, 11, 49)

FONTES = (
    Source(1, "https://a.pt/um", "Primeira", "2026-01-01", None, "..."),
    Source(2, "https://www.b.pt/dois", "Segunda", None, "2026-02-02", "..."),
)


def _result(text: str, sources: tuple[Source, ...] = FONTES, **changes) -> SearchResult:
    base = {
        "response_id": "resp_teste",
        "model": "openai/gpt-6-luna",
        "text": text,
        "sources": sources,
        "queries": ("busca",),
        "usage": Usage(input_tokens=10, output_tokens=5, search_calls=1, cost_usd=0.001),
        "raw": {},
    }
    return SearchResult(**{**base, **changes})


def _render(text: str, options: SearchOptions | None = None, briefing: str = "Idioma: pt-BR.") -> str:
    return render(_result(text), "Pergunta de teste", options or SearchOptions(), briefing, QUANDO)


def _front_matter(md: str) -> dict:
    assert md.startswith("---\n")
    bloco = md.split("---\n", 2)[1]
    return yaml.safe_load(bloco)


# ----------------------------------------------------------------- citações (aceite da F4)


def test_citacao_simples_vira_link() -> None:
    assert link_citations("Fato. [1]", FONTES) == "Fato. [[1]](https://a.pt/um)"


def test_citacao_com_prefixo_web_vira_link_sem_o_prefixo() -> None:
    assert link_citations("Fato. [web:2]", FONTES) == "Fato. [[2]](https://www.b.pt/dois)"


def test_citacoes_seguidas_viram_links_separados() -> None:
    esperado = "x [[1]](https://a.pt/um)[[2]](https://www.b.pt/dois)"
    assert link_citations("x [1][2]", FONTES) == esperado
    assert link_citations("x [web:1][web:2]", FONTES) == esperado


def test_id_inexistente_fica_como_estava() -> None:
    """Melhor um marcador órfão do que um link para a fonte errada."""
    assert link_citations("x [7] e [web:99]", FONTES) == "x [7] e [web:99]"


def test_citacao_dentro_de_bloco_de_codigo_nao_muda() -> None:
    texto = "Antes [1].\n\n```\nexemplo [1] e [web:2]\n```\n\nDepois [2]."
    saida = link_citations(texto, FONTES)
    assert "```\nexemplo [1] e [web:2]\n```" in saida
    assert "Antes [[1]](https://a.pt/um)." in saida
    assert "Depois [[2]](https://www.b.pt/dois)." in saida


def test_bloco_de_codigo_com_til_tambem_e_respeitado() -> None:
    texto = "~~~\n[1]\n~~~\n[1]"
    saida = link_citations(texto, FONTES)
    assert "~~~\n[1]\n~~~" in saida
    assert saida.endswith("[[1]](https://a.pt/um)")


def test_bloco_de_codigo_com_linguagem_e_respeitado() -> None:
    assert "[1]" in link_citations("```python\nx = [1]\n```", FONTES).split("\n")[1]


def test_cerca_mais_longa_fecha_o_bloco_e_cerca_interna_nao() -> None:
    texto = "````\n```\n[1]\n```\n````\n[1]"
    saida = link_citations(texto, FONTES)
    assert saida.count("[[1]]") == 1  # só o de fora do bloco


def test_bloco_de_codigo_nao_fechado_protege_ate_o_fim() -> None:
    saida = link_citations("[1]\n```\n[1]\n[2]", FONTES)
    assert saida.startswith("[[1]](https://a.pt/um)")
    assert saida.endswith("```\n[1]\n[2]")


def test_sem_fontes_o_texto_nao_e_tocado() -> None:
    assert link_citations("x [1]", ()) == "x [1]"


def test_texto_sem_citacao_passa_intacto() -> None:
    assert link_citations("nada aqui", FONTES) == "nada aqui"


# ----------------------------------------------------------------- front matter


def test_front_matter_e_yaml_valido() -> None:
    dados = _front_matter(_render("texto [1]"))
    assert dados["prompt"] == "Pergunta de teste"
    assert dados["created_at"] == "2026-10-06T11:49:00"
    assert dados["preset"] == "low"
    assert dados["response_id"] == "resp_teste"
    assert dados["cost_usd"] == pytest.approx(0.001)
    assert dados["sources"] == 2
    assert dados["options"]["language"] == "pt-BR"


@pytest.mark.parametrize(
    "prompt",
    [
        'com "aspas duplas" no meio',
        "com 'aspas simples'",
        "com barra invertida \\ solta",
        "com: dois pontos",
        "com # cerquilha e - hifen",
        "com {chaves} e [colchetes]",
        "linha um\nlinha dois",
        "tab\tno meio",
        'aspas no fim "',
        "\\",
    ],
)
def test_front_matter_sobrevive_a_prompt_hostil(prompt: str) -> None:
    md = render(_result("texto"), prompt, SearchOptions(), "b", QUANDO)
    dados = _front_matter(md)
    assert dados["prompt"] == " ".join(prompt.split())  # colapsado para uma linha, mas intacto


def test_front_matter_com_custo_ausente_vira_null() -> None:
    result = _result("x", usage=Usage(1, 2, 1, None))
    dados = _front_matter(render(result, "p", SearchOptions(), "b", QUANDO))
    assert dados["cost_usd"] is None


def test_front_matter_registra_as_opcoes_usadas() -> None:
    options = dataclasses.replace(
        SearchOptions(),
        domains=("a.pt", "b.pt"),
        domain_mode="deny",
        recency="month",
        location=LocationOpt("PT", "Lisboa", "Lisboa"),
        custom_instructions="seja breve",
    )
    dados = _front_matter(_render("x", options))["options"]
    assert dados["domains"] == ["a.pt", "b.pt"]
    assert dados["domain_mode"] == "deny"
    assert dados["recency"] == "month"
    assert dados["location"] == {"country": "PT", "region": "Lisboa", "city": "Lisboa"}
    assert dados["custom_instructions"] == "seja breve"


def test_front_matter_omite_opcoes_vazias() -> None:
    dados = _front_matter(_render("x"))["options"]
    for chave in ("domains", "recency", "after", "before", "location", "custom_instructions"):
        assert chave not in dados


def test_datas_das_opcoes_saem_em_iso() -> None:
    options = dataclasses.replace(SearchOptions(), after=date(2026, 1, 31), before=date(2026, 6, 30))
    dados = _front_matter(_render("x", options))["options"]
    assert (dados["after"], dados["before"]) == ("2026-01-31", "2026-06-30")


# ----------------------------------------------------------------- seções


def test_secao_fontes_lista_titulo_dominio_data_e_url() -> None:
    md = _render("x")
    assert "## Fontes" in md
    assert "1. [Primeira](https://a.pt/um) — a.pt · 2026-01-01" in md
    assert "2. [Segunda](https://www.b.pt/dois) — b.pt" in md  # www. removido; sem data


def test_fontes_sem_resultado_tem_aviso_em_portugues() -> None:
    md = render(_result("x", sources=()), "p", SearchOptions(), "b", QUANDO)
    assert "A busca não devolveu fontes." in md


def test_colchetes_no_titulo_sao_escapados() -> None:
    fonte = (Source(1, "https://a.pt", "Titulo [com] colchetes", None, None, ""),)
    md = render(_result("x", sources=fonte), "p", SearchOptions(), "b", QUANDO)
    assert r"[Titulo \[com\] colchetes](https://a.pt)" in md


def test_titulo_vazio_cai_para_a_url() -> None:
    fonte = (Source(1, "https://a.pt/x", "", None, None, ""),)
    md = render(_result("x", sources=fonte), "p", SearchOptions(), "b", QUANDO)
    assert "1. [https://a.pt/x](https://a.pt/x)" in md


def test_secao_parametros_traz_o_briefing_exato() -> None:
    briefing = "Idioma da resposta: português do Brasil.\nFormato: relatório."
    md = _render("x", briefing=briefing)
    assert "## Parâmetros da busca" in md
    assert f"```\n{briefing}\n```" in md


def test_briefing_com_cerca_usa_til_para_nao_quebrar() -> None:
    md = _render("x", briefing="tem ``` no meio")
    assert "~~~\ntem ``` no meio\n~~~" in md


def test_briefing_vazio_omite_a_secao() -> None:
    assert "Parâmetros da busca" not in _render("x", briefing="   ")


def test_ordem_das_secoes_segue_o_rf3() -> None:
    md = _render("corpo [1]")
    assert md.index("# Pergunta de teste") < md.index("corpo")
    assert md.index("corpo") < md.index("## Fontes") < md.index("## Parâmetros da busca")


def test_relatorio_termina_com_uma_unica_quebra() -> None:
    md = _render("x")
    assert md.endswith("\n") and not md.endswith("\n\n")


# ----------------------------------------------------------------- golden file


def test_relatorio_bate_com_o_golden_file() -> None:
    """Qualquer mudança de layout tem de ser consciente: regenere a fixture de propósito."""
    defaults = load_defaults(CONFIG_DIR / "defaults.toml")
    snippets = load_snippets(CONFIG_DIR / "prompt_snippets.toml")
    prompt = "Arquivo Historico Ultramarino: horario da sala de leitura"
    options = dataclasses.replace(
        defaults.options,
        domains=("ahu.dglab.gov.pt", "arquivos.pt"),
        after=date(2026, 1, 31),
        before=date(2026, 6, 30),
        location=LocationOpt("PT", "Lisboa", "Lisboa"),
        priorities=("primarias", "confianca"),
        language="pt-PT",
        output_format="dossie",
        max_results=3,
    )
    req = build(prompt, options, snippets, defaults.timeouts)
    raw = json.loads((FIXTURES / "agent_low_maxresults.json").read_text(encoding="utf-8"))
    md = render(parse(raw), prompt, options, req.briefing, QUANDO)

    assert md == GOLDEN.read_text(encoding="utf-8")


def test_golden_file_tem_front_matter_yaml_valido() -> None:
    dados = _front_matter(GOLDEN.read_text(encoding="utf-8"))
    assert dados["preset"] == "low"
    assert dados["options"]["location"]["city"] == "Lisboa"


def test_relatorio_das_fixtures_reais_nao_quebra() -> None:
    defaults = load_defaults(CONFIG_DIR / "defaults.toml")
    for nome in FIXTURES.glob("agent_*.json"):
        result = parse(json.loads(nome.read_text(encoding="utf-8")))
        md = render(result, "p", defaults.options, "b", QUANDO)
        assert _front_matter(md)["sources"] == len(result.sources)
        assert "## Fontes" in md


def test_relatorio_nao_contem_credencial() -> None:
    assert "pplx-" not in GOLDEN.read_text(encoding="utf-8")
