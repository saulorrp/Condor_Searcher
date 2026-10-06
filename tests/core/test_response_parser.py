"""Testes de `core/response_parser.py` (API_NOTES §4).

Usa as 4 fixtures reais gravadas na F0 e uma fixture sintética "esquisita" que junta de propósito
tudo o que pode dar errado: sem `usage`, item de tipo desconhecido, resultado sem data, sem id,
sem URL, id repetido em outra URL, id como texto e lixo que não é objeto.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from condor.core.models import SearchResult
from condor.core.response_parser import parse

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures"
REAIS = (
    "agent_fast.json",
    "agent_low_filtered.json",
    "agent_low_maxresults.json",
    "agent_low_searchtype.json",
)


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def estranho() -> SearchResult:
    return parse(_load("agent_estranho.json"))


# ----------------------------------------------------------------- fixtures reais da F0


@pytest.mark.parametrize("nome", REAIS)
def test_fixtures_reais_sao_parseadas(nome: str) -> None:
    result = parse(_load(nome))
    assert result.response_id.startswith("resp_")
    assert result.model
    assert result.text
    assert result.sources
    assert result.queries
    assert result.usage.input_tokens > 0
    assert result.usage.output_tokens > 0
    assert result.usage.search_calls >= 1
    assert result.usage.cost_usd is not None and result.usage.cost_usd > 0


@pytest.mark.parametrize(
    ("nome", "n_fontes", "n_queries", "custo"),
    [
        ("agent_fast.json", 10, 1, 0.00137),
        ("agent_low_filtered.json", 15, 3, 0.00244),
        ("agent_low_maxresults.json", 2, 2, 0.00113),
        ("agent_low_searchtype.json", 15, 2, 0.00287),
    ],
)
def test_contagens_batem_com_o_que_a_f0_observou(
    nome: str, n_fontes: int, n_queries: int, custo: float
) -> None:
    """Os números aqui são os que o smoke da F0 imprimiu — servem de âncora."""
    result = parse(_load(nome))
    assert len(result.sources) == n_fontes
    assert len(result.queries) == n_queries
    assert result.usage.cost_usd == pytest.approx(custo)


@pytest.mark.parametrize("nome", REAIS)
def test_fontes_reais_tem_id_unico_contiguo_e_url(nome: str) -> None:
    sources = parse(_load(nome)).sources
    ids = [s.id for s in sources]
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)
    assert ids == list(range(1, len(ids) + 1))
    assert all(s.url.startswith("http") for s in sources)


def test_fixture_com_fetch_url_ignora_o_item_extra() -> None:
    """A `low` com `fetch_url_results` não deve contaminar as fontes nem o texto."""
    raw = _load("agent_low_filtered.json")
    assert any(i.get("type") == "fetch_url_results" for i in raw["output"])
    result = parse(raw)
    assert len(result.sources) == 15  # só os de `search_results`
    assert "[web:" in result.text


def test_datas_ausentes_viram_none_nas_fixtures_reais() -> None:
    sources = parse(_load("agent_low_filtered.json")).sources
    assert any(s.date is None for s in sources)
    assert all(s.date is None or len(s.date) == 10 for s in sources)


def test_raw_e_preservado_sem_alteracao() -> None:
    raw = _load("agent_fast.json")
    copia = json.loads(json.dumps(raw))
    result = parse(raw)
    assert result.raw == copia  # o parser não mexe no que recebeu


# ----------------------------------------------------------------- fixture esquisita


def test_sem_usage_zera_tokens_e_deixa_custo_none(estranho: SearchResult) -> None:
    assert "usage" not in _load("agent_estranho.json")
    assert estranho.usage.input_tokens == 0
    assert estranho.usage.output_tokens == 0
    assert estranho.usage.cost_usd is None


def test_sem_usage_conta_buscas_pelos_itens(estranho: SearchResult) -> None:
    """Sem `tool_calls_details`, o nº de buscas cai para a contagem de itens `search_results`."""
    assert estranho.usage.search_calls == 2


def test_itens_e_blocos_desconhecidos_sao_ignorados(estranho: SearchResult) -> None:
    assert "advisor_result" not in estranho.text
    assert "nao deve entrar" not in estranho.text
    assert estranho.text == "Primeiro bloco com citacao [1].\nSegundo bloco [web:3]."


def test_campos_ausentes_viram_vazio_ou_none(estranho: SearchResult) -> None:
    por_id = {s.id: s for s in estranho.sources}
    assert por_id[1].date is None and por_id[1].last_updated is None
    assert por_id[2].date is None and por_id[2].last_updated == "2026-01-02"
    assert estranho.model == ""  # a fixture não traz "model"


def test_resultado_sem_url_e_descartado(estranho: SearchResult) -> None:
    assert all(s.url for s in estranho.sources)
    assert 9 not in {s.id for s in estranho.sources}  # o id=9 não tinha URL


def test_dedupe_por_url_mantem_a_primeira_ocorrencia(estranho: SearchResult) -> None:
    urls = [s.url for s in estranho.sources]
    assert len(urls) == len(set(urls))
    assert next(s for s in estranho.sources if s.url == "https://b.pt/2").title == "Data nula"


def test_id_repetido_em_outra_url_mantem_o_primeiro_e_avisa(caplog) -> None:
    with caplog.at_level(logging.WARNING):
        result = parse(_load("agent_estranho.json"))
    por_id = {s.id: s for s in result.sources}
    assert por_id[1].url == "https://a.pt/1"  # o primeiro id=1 venceu
    assert "https://d.pt/4" not in {s.url for s in result.sources}
    assert any("id=1" in r.getMessage() for r in caplog.records)


def test_id_como_texto_vira_inteiro(estranho: SearchResult) -> None:
    assert {s.id for s in estranho.sources} >= {4}
    assert next(s for s in estranho.sources if s.id == 4).url == "https://f.pt/6"


def test_resultados_sem_id_entram_depois_do_maior_id(estranho: SearchResult) -> None:
    por_url = {s.url: s.id for s in estranho.sources}
    assert por_url["https://c.pt/3"] == 5
    assert por_url["https://g.pt/7"] == 6


def test_varios_search_results_sao_juntados_e_ordenados(estranho: SearchResult) -> None:
    assert [s.id for s in estranho.sources] == [1, 2, 3, 4, 5, 6]
    assert [s.url for s in estranho.sources][:3] == ["https://a.pt/1", "https://b.pt/2", "https://e.pt/5"]


def test_queries_sao_juntadas_sem_repetir_nem_vazias(estranho: SearchResult) -> None:
    assert estranho.queries == ("primeira busca", "segunda busca", "terceira busca")


# ----------------------------------------------------------------- respostas degeneradas


def test_dict_vazio_nao_quebra() -> None:
    result = parse({})
    assert result == SearchResult(
        response_id="",
        model="",
        text="",
        sources=(),
        queries=(),
        usage=result.usage,
        raw={},
    )
    assert result.usage.search_calls == 0
    assert result.usage.cost_usd is None


@pytest.mark.parametrize("output", [None, "texto", 42, {}, [], ["lixo", 1, None]])
def test_output_de_tipo_errado_nao_quebra(output) -> None:
    result = parse({"id": "resp_x", "output": output})
    assert result.sources == () and result.text == ""


@pytest.mark.parametrize(
    "usage",
    [None, "texto", {}, {"cost": None}, {"cost": "grátis"}, {"cost": {}}, {"cost": {"total_cost": None}}],
)
def test_custo_ausente_ou_invalido_vira_none(usage) -> None:
    assert parse({"usage": usage}).usage.cost_usd is None


def test_custo_como_texto_numerico_e_aceito() -> None:
    assert parse({"usage": {"cost": {"total_cost": "0.0025"}}}).usage.cost_usd == pytest.approx(0.0025)


def test_tokens_invalidos_viram_zero() -> None:
    usage = {"input_tokens": "muitos", "output_tokens": None}
    assert parse({"usage": usage}).usage.input_tokens == 0
    assert parse({"usage": usage}).usage.output_tokens == 0


def test_soma_invocacoes_de_varias_ferramentas_de_busca() -> None:
    usage = {
        "tool_calls_details": {
            "search_web": {"invocation": 2, "cost_usd": 0.002},
            "search_people": {"invocation": 1},
            "fetch_url": {"invocation": 5},
        }
    }
    assert parse({"usage": usage}).usage.search_calls == 3  # fetch_url não é busca


def test_texto_vazio_nao_e_erro_aqui() -> None:
    """Resposta vazia é decisão do client (RF6), não do parser."""
    raw = {"output": [{"type": "message", "content": [{"type": "output_text", "text": "   "}]}]}
    assert parse(raw).text == ""
