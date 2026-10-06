"""Testes de `core/prompt_builder.py` (TECHSPEC §6, API_NOTES §3 e §5)."""

from __future__ import annotations

import dataclasses
import json
from datetime import date
from pathlib import Path

import pytest

from condor.core.config import load_defaults, load_snippets
from condor.core.models import MAX_DOMAINS, LocationOpt, SearchOptions
from condor.core.prompt_builder import CITATION_RULES, build

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
PAYLOAD_DEFAULT = ROOT / "tests" / "fixtures" / "payload_default.json"

PROMPT = "Como funciona o Arquivo Historico Ultramarino?"


@pytest.fixture(scope="module")
def defaults():
    return load_defaults(CONFIG_DIR / "defaults.toml")


@pytest.fixture(scope="module")
def snippets():
    return load_snippets(CONFIG_DIR / "prompt_snippets.toml")


@pytest.fixture
def make(defaults, snippets):
    """Constrói um AgentRequest a partir dos defaults reais, com os campos trocados."""

    def _make(prompt: str = PROMPT, **changes):
        options = dataclasses.replace(defaults.options, **changes)
        return build(prompt, options, snippets, defaults.timeouts)

    return _make


def _tool(req) -> dict:
    assert len(req.payload["tools"]) == 1
    return req.payload["tools"][0]


# ----------------------------------------------------------------- caso default


def test_payload_default_bate_com_o_snapshot(make) -> None:
    """Qualquer mudança no payload default tem de ser consciente: atualize a fixture de propósito."""
    esperado = json.loads(PAYLOAD_DEFAULT.read_text(encoding="utf-8"))
    assert make().payload == esperado


def test_default_monta_input_no_formato_do_techspec(make) -> None:
    req = make()
    texto = req.payload["input"]
    assert texto.startswith("<briefing>\n")
    assert f"</briefing>\n\n<pergunta>\n{PROMPT}\n</pergunta>" in texto
    assert req.briefing in texto
    assert req.briefing.splitlines()[0] == "Idioma da resposta: português do Brasil."
    assert "Prioridades:" in req.briefing


def test_default_nao_envia_instructions_nem_filters(make) -> None:
    """Sem instruções próprias o prompt do preset é preservado; sem filtros, nada de `filters: {}`."""
    req = make()
    assert "instructions" not in req.payload
    assert "filters" not in _tool(req)
    assert _tool(req) == {"type": "web_search", "search_context_size": "medium", "max_results": 15}


def test_timeout_vem_da_configuracao_do_preset(make, defaults) -> None:
    assert make().timeout_s == defaults.timeouts["low"]
    assert make(preset="xhigh").timeout_s == defaults.timeouts["xhigh"]


def test_timeout_ausente_na_configuracao_e_erro(defaults, snippets) -> None:
    with pytest.raises(ValueError, match="timeout"):
        build(PROMPT, defaults.options, snippets, {"fast": 60})  # falta o do preset "low"


# ----------------------------------------------------------------- domínios: allow e deny


def test_allowlist_vai_sem_prefixo(make) -> None:
    req = make(domains=("dglab.gov.pt", "arquivos.pt"), domain_mode="allow")
    assert _tool(req)["filters"]["search_domain_filter"] == ["dglab.gov.pt", "arquivos.pt"]
    assert "domínios restritos a: dglab.gov.pt, arquivos.pt" in req.briefing


def test_denylist_prefixa_todos_os_dominios(make) -> None:
    req = make(domains=("pinterest.com", "quora.com"), domain_mode="deny")
    assert _tool(req)["filters"]["search_domain_filter"] == ["-pinterest.com", "-quora.com"]
    assert "não use estes domínios: pinterest.com, quora.com" in req.briefing


def test_dominios_sao_limpos_e_deduplicados(make) -> None:
    """Espaços, um `-` digitado à mão e repetições não devem chegar à API."""
    req = make(domains=("  dglab.gov.pt ", "-dglab.gov.pt", "", "arquivos.pt"))
    assert _tool(req)["filters"]["search_domain_filter"] == ["dglab.gov.pt", "arquivos.pt"]


def test_mais_de_20_dominios_e_erro_em_portugues(make) -> None:
    with pytest.raises(ValueError, match=f"no máximo {MAX_DOMAINS} domínios"):
        make(domains=tuple(f"d{i}.pt" for i in range(MAX_DOMAINS + 1)))


def test_exatamente_20_dominios_passa(make) -> None:
    req = make(domains=tuple(f"d{i}.pt" for i in range(MAX_DOMAINS)))
    assert len(_tool(req)["filters"]["search_domain_filter"]) == MAX_DOMAINS


def test_limite_conta_dominios_ja_deduplicados(make) -> None:
    """21 entradas com uma repetida dão 20 domínios reais — deve passar."""
    domains = tuple(f"d{i}.pt" for i in range(MAX_DOMAINS)) + ("d0.pt",)
    assert len(_tool(make(domains=domains))["filters"]["search_domain_filter"]) == MAX_DOMAINS


# ----------------------------------------------------------------- período


def test_recency_vai_para_o_filtro_e_para_o_briefing(make) -> None:
    req = make(recency="month")
    assert _tool(req)["filters"]["search_recency_filter"] == "month"
    assert "último mês" in req.briefing


def test_datas_viram_mm_dd_yyyy_no_payload_e_dd_mm_yyyy_no_briefing(make) -> None:
    req = make(after=date(2026, 1, 31), before=date(2026, 6, 30))
    filters = _tool(req)["filters"]
    assert filters["search_after_date_filter"] == "01/31/2026"
    assert filters["search_before_date_filter"] == "06/30/2026"
    assert "entre 31/01/2026 e 30/06/2026" in req.briefing


def test_apenas_data_inicial_ou_final(make) -> None:
    assert "search_before_date_filter" not in _tool(make(after=date(2026, 1, 31)))["filters"]
    assert "search_after_date_filter" not in _tool(make(before=date(2026, 6, 30)))["filters"]
    assert "a partir de 31/01/2026" in make(after=date(2026, 1, 31)).briefing
    assert "até 30/06/2026" in make(before=date(2026, 6, 30)).briefing


def test_recency_junto_com_datas_e_erro(make) -> None:
    with pytest.raises(ValueError, match="período OU um intervalo"):
        make(recency="month", after=date(2026, 1, 31))


def test_data_inicial_depois_da_final_e_erro(make) -> None:
    with pytest.raises(ValueError, match=r"31/06/2026|posterior"):
        make(after=date(2026, 6, 30), before=date(2026, 1, 31))


# ----------------------------------------------------------------- localização


def test_localizacao_vai_no_nivel_do_tool(make) -> None:
    req = make(location=LocationOpt(country="pt", region="Lisboa", city="Lisboa"))
    tool = _tool(req)
    assert tool["user_location"] == {"country": "PT", "region": "Lisboa", "city": "Lisboa"}
    assert "user_location" not in tool.get("filters", {})


def test_localizacao_omite_regiao_e_cidade_vazias(make) -> None:
    req = make(location=LocationOpt(country="BR"))
    assert _tool(req)["user_location"] == {"country": "BR"}


def test_pais_fora_do_iso2_e_erro(make) -> None:
    with pytest.raises(ValueError, match="duas letras"):
        make(location=LocationOpt(country="Portugal"))


# ----------------------------------------------------------------- instruções próprias


def test_instrucoes_proprias_recebem_as_regras_de_citacao(make) -> None:
    req = make(custom_instructions="Responda como um arquivista.")
    assert req.payload["instructions"] == f"Responda como um arquivista.\n\n{CITATION_RULES}"
    assert "[1] ou [1][2]" in req.payload["instructions"]


def test_instrucoes_so_de_espacos_nao_viram_instructions(make) -> None:
    assert "instructions" not in make(custom_instructions="   \n  ").payload


# ----------------------------------------------------------------- prompt e outras validações


@pytest.mark.parametrize("prompt", ["", "   ", "\n\t "])
def test_prompt_vazio_e_erro_em_portugues(make, prompt: str) -> None:
    with pytest.raises(ValueError, match="Escreva a sua pergunta"):
        make(prompt)


def test_prompt_e_aparado_antes_de_entrar_no_input(make) -> None:
    assert "<pergunta>\nolá\n</pergunta>" in make("  olá  ").payload["input"]


@pytest.mark.parametrize(
    ("changes", "trecho"),
    [
        ({"preset": "turbo"}, "Profundidade desconhecida"),
        ({"domain_mode": "ambos"}, "Modo do filtro desconhecido"),
        ({"context_size": "gigante"}, "Profundidade de leitura desconhecida"),
        ({"recency": "decada"}, "Período desconhecido"),
        ({"max_results": 0}, "entre 1 e 50"),
        ({"max_results": 51}, "entre 1 e 50"),
        ({"language": "tlh"}, "Idioma desconhecido na configuração"),
        ({"output_format": "inexistente"}, "Formato desconhecido na configuração"),
        ({"priorities": ("inexistente",)}, "Prioridade desconhecid"),
    ],
)
def test_opcao_invalida_e_value_error(make, changes: dict, trecho: str) -> None:
    with pytest.raises(ValueError, match=trecho):
        make(**changes)


def test_preset_e_profundidade_de_leitura_chegam_ao_payload(make) -> None:
    req = make(preset="high", context_size="high", max_results=50)
    assert req.payload["preset"] == "high"
    assert _tool(req)["search_context_size"] == "high"
    assert _tool(req)["max_results"] == 50


def test_sem_prioridades_o_briefing_omite_a_secao(make) -> None:
    req = make(priorities=())
    assert "Prioridades:" not in req.briefing
    assert req.briefing.count("\n") == 1  # só idioma e formato


def test_briefing_cobre_todas_as_linhas_do_techspec(make) -> None:
    """Caso completo: idioma, formato, prioridades, escopo e período, nessa ordem."""
    req = make(
        language="pt-PT",
        output_format="dossie",
        priorities=("primarias", "confianca"),
        domains=("dglab.gov.pt",),
        recency="year",
    )
    linhas = req.briefing.splitlines()
    assert linhas[0].startswith("Idioma da resposta: português europeu")
    assert linhas[1].startswith("Formato: dossiê tático")
    assert linhas[2] == "Prioridades:"
    assert linhas[3].startswith("- Prefira fontes primárias")
    assert linhas[4].startswith("- Indique o nível de confiança")
    assert linhas[5].startswith("Escopo de fontes:")
    assert linhas[6].startswith("Período:")


def test_payload_nao_leva_timeout_nem_a_chave(make) -> None:
    """O timeout é opção do SDK, não do payload; e nada de credencial aqui (RF4 "Ver prompt final")."""
    payload = make().payload
    assert "timeout" not in payload
    assert "pplx-" not in json.dumps(payload)
    assert set(payload) <= {"preset", "input", "instructions", "tools"}


def test_options_nao_e_modificado(make, defaults) -> None:
    antes = dataclasses.replace(defaults.options)
    build(PROMPT, defaults.options, load_snippets(CONFIG_DIR / "prompt_snippets.toml"), defaults.timeouts)
    assert defaults.options == antes


def test_search_options_padrao_tambem_funciona(snippets, defaults) -> None:
    """Garantia para a F7, que usa só `SearchOptions()`."""
    req = build(PROMPT, SearchOptions(), snippets, defaults.timeouts)
    assert req.payload["preset"] == "low"
    assert "filters" not in _tool(req)
