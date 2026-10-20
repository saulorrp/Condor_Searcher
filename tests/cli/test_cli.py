"""Testes da linha de comando (F11).

Nenhuma chamada de rede: o `ambiente` usa SDK falso, pasta temporária e `.env` próprio.
O foco é o contrato com quem vai usar isto sem supervisão — saída JSON estável, códigos de
saída que distinguem o tipo de falha, e o teto de gastos funcionando.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from condor.cli.app import (
    ERRO_API,
    ERRO_CHAVE,
    ERRO_TETO,
    ERRO_USO,
    NAO_ENCONTRADO,
    OK,
    cmd_buscar,
    cmd_gastos,
    cmd_historico,
    cmd_ver,
)
from condor.cli.main import build_parser
from condor.cli.options import options_from_args
from condor.core.config import Limits
from condor.core.models import LocationOpt, SearchOptions, SearchResult, Source, Usage
from condor.services.errors import NetworkError
from tests.fakes import SdkFalso

PERGUNTA = "Qual é a capital de Portugal?"


def _args(ambiente, *argv: str):
    return build_parser(ambiente.defaults).parse_args(list(argv))


def _json_da_saida(ambiente) -> dict:
    return json.loads(ambiente.escrever.texto)


def _salva_busca(ambiente, custo: float = 0.001, quando: datetime | None = None, prompt: str = PERGUNTA):
    resultado = SearchResult(
        response_id="resp_x",
        model="m",
        text="Lisboa. [1]",
        sources=(Source(1, "https://a.pt", "A", "2026-01-01", None, ""),),
        queries=("q",),
        usage=Usage(input_tokens=10, output_tokens=5, search_calls=1, cost_usd=custo),
        raw={"id": "resp_x"},
    )
    return ambiente.storage.save(
        resultado, "# relatório\n\ncorpo", prompt, SearchOptions(), created_at=quando or datetime.now()
    )


# ----------------------------------------------------------------- flags → SearchOptions


def test_sem_flags_usa_os_defaults_do_toml(ambiente) -> None:
    args = _args(ambiente, "buscar", PERGUNTA)
    assert options_from_args(args, ambiente.packs, ambiente.defaults) == ambiente.defaults.options


def test_flags_viram_search_options(ambiente) -> None:
    args = _args(
        ambiente,
        "buscar",
        PERGUNTA,
        "--preset",
        "medium",
        "--dominio",
        "dglab.gov.pt",
        "--dominio",
        "arquivos.pt",
        "--modo",
        "deny",
        "--de",
        "31/01/2026",
        "--ate",
        "30/06/2026",
        "--leitura",
        "high",
        "--max-resultados",
        "7",
        "--idioma",
        "pt-PT",
        "--formato",
        "dossie",
        "--prioridade",
        "primarias",
        "--local",
        "pt,Lisboa,Lisboa",
        "--instrucoes",
        "seja breve",
    )
    opcoes = options_from_args(args, ambiente.packs, ambiente.defaults)

    assert opcoes == SearchOptions(
        preset="medium",
        domains=("dglab.gov.pt", "arquivos.pt"),
        domain_mode="deny",
        after=date(2026, 1, 31),
        before=date(2026, 6, 30),
        location=LocationOpt("PT", "Lisboa", "Lisboa"),
        context_size="high",
        max_results=7,
        language="pt-PT",
        output_format="dossie",
        priorities=("primarias",),
        custom_instructions="seja breve",
    )


def test_pacote_vira_lista_de_dominios(ambiente) -> None:
    args = _args(ambiente, "buscar", PERGUNTA, "--pacote", "brasil_oficial", "--dominio", "extra.pt")
    opcoes = options_from_args(args, ambiente.packs, ambiente.defaults)
    assert opcoes.domains[-1] == "extra.pt"
    assert "gov.br" in opcoes.domains


def test_pacote_desconhecido_e_erro_em_portugues(ambiente) -> None:
    args = _args(ambiente, "buscar", PERGUNTA, "--pacote", "inexistente")
    with pytest.raises(ValueError, match="Pacote de fontes desconhecido"):
        options_from_args(args, ambiente.packs, ambiente.defaults)


@pytest.mark.parametrize("valor", ["31/31/2026", "2026-01-31", "amanhã", "1/2"])
def test_data_invalida_e_erro_com_dica(ambiente, valor: str) -> None:
    args = _args(ambiente, "buscar", PERGUNTA, "--de", valor)
    with pytest.raises(ValueError, match="DD/MM/AAAA"):
        options_from_args(args, ambiente.packs, ambiente.defaults)


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("PT", LocationOpt("PT", "", "")),
        ("br,SC", LocationOpt("BR", "SC", "")),
        ("PT, Lisboa , Lisboa", LocationOpt("PT", "Lisboa", "Lisboa")),
    ],
)
def test_local_aceita_uma_a_tres_partes(ambiente, entrada: str, esperado) -> None:
    args = _args(ambiente, "buscar", PERGUNTA, "--local", entrada)
    assert options_from_args(args, ambiente.packs, ambiente.defaults).location == esperado


def test_local_com_partes_demais_e_erro(ambiente) -> None:
    args = _args(ambiente, "buscar", PERGUNTA, "--local", "PT,a,b,c")
    with pytest.raises(ValueError, match="no máximo"):
        options_from_args(args, ambiente.packs, ambiente.defaults)


# ----------------------------------------------------------------- buscar


def test_buscar_grava_o_relatorio_e_devolve_ok(ambiente) -> None:
    args = _args(ambiente, "buscar", PERGUNTA)
    assert cmd_buscar(ambiente, args) == OK

    registros = ambiente.storage.list_recent()
    assert len(registros) == 1
    assert registros[0].md_path.exists()
    assert "Busca #1 concluída" in ambiente.escrever.texto


def test_buscar_json_tem_o_contrato_esperado(ambiente) -> None:
    """Campos que um agente vai ler sem supervisão: renomear aqui quebra quem já usa."""
    assert cmd_buscar(ambiente, _args(ambiente, "buscar", PERGUNTA, "--json")) == OK
    dados = _json_da_saida(ambiente)

    assert dados["ok"] is True
    assert set(dados) >= {
        "id",
        "created_at",
        "prompt",
        "preset",
        "md_path",
        "json_path",
        "cost_usd",
        "usage",
        "queries",
        "sources",
        "sources_total",
        "text",
    }
    assert Path(dados["md_path"]).exists()
    assert dados["sources"][0]["url"].startswith("http")
    assert dados["cost_usd"] == pytest.approx(0.00137)


def test_json_resume_o_texto_por_padrao(ambiente) -> None:
    cmd_buscar(ambiente, _args(ambiente, "buscar", PERGUNTA, "--json"))
    assert len(_json_da_saida(ambiente)["text"]) <= 601


def test_texto_completo_devolve_tudo(ambiente) -> None:
    cmd_buscar(ambiente, _args(ambiente, "buscar", PERGUNTA, "--json", "--texto-completo"))
    assert _json_da_saida(ambiente)["text"].startswith("A capital de Portugal")


def test_so_prompt_nao_chama_a_api(ambiente) -> None:
    """O jeito seguro de conferir as opções: mostra o payload e não gasta nada."""
    assert cmd_buscar(ambiente, _args(ambiente, "buscar", PERGUNTA, "--so-prompt")) == OK

    assert ambiente.sdk.chamadas == []
    assert ambiente.storage.list_recent() == ()
    assert "<pergunta>" in ambiente.escrever.texto


def test_so_prompt_em_json(ambiente) -> None:
    cmd_buscar(ambiente, _args(ambiente, "buscar", PERGUNTA, "--so-prompt", "--json"))
    dados = _json_da_saida(ambiente)
    assert dados["payload"]["preset"] == "low"
    assert dados["timeout_s"] == 180
    assert ambiente.sdk.chamadas == []


def test_opcao_invalida_nao_chama_a_api(ambiente) -> None:
    args = _args(ambiente, "buscar", PERGUNTA, "--max-resultados", "99")
    assert cmd_buscar(ambiente, args) == ERRO_USO
    assert ambiente.sdk.chamadas == []
    assert "entre 1 e 50" in ambiente.escrever.texto


def test_erro_de_uso_em_json(ambiente) -> None:
    args = _args(ambiente, "buscar", PERGUNTA, "--pacote", "inexistente", "--json")
    assert cmd_buscar(ambiente, args) == ERRO_USO
    dados = _json_da_saida(ambiente)
    assert dados["ok"] is False
    assert dados["error_code"] == "uso"


def test_sem_chave_recusa_antes_de_gastar(sem_chave) -> None:
    args = _args(sem_chave, "buscar", PERGUNTA)
    assert cmd_buscar(sem_chave, args) == ERRO_CHAVE
    assert sem_chave.sdk.chamadas == []
    assert "chave da API" in sem_chave.escrever.texto


def test_falha_da_api_tem_codigo_proprio(ambiente) -> None:
    ambiente.client = type(ambiente.client)(
        lambda: SdkFalso({}, erro=NetworkError("rede fora")), sleep=lambda s: False, max_attempts=1
    )
    args = _args(ambiente, "buscar", PERGUNTA, "--json")
    assert cmd_buscar(ambiente, args) == ERRO_API
    assert _json_da_saida(ambiente)["error_code"] == "api"


def test_nenhuma_saida_contem_a_chave(ambiente) -> None:
    cmd_buscar(ambiente, _args(ambiente, "buscar", PERGUNTA, "--json", "--texto-completo"))
    assert "pplx-" not in ambiente.escrever.texto


# ----------------------------------------------------------------- teto de gastos


def test_teto_bloqueia_quando_o_dia_estoura(ambiente) -> None:
    ambiente.defaults = dataclasses.replace(ambiente.defaults, limits=Limits(daily_usd=0.01))
    _salva_busca(ambiente, custo=0.02)

    args = _args(ambiente, "buscar", PERGUNTA)
    assert cmd_buscar(ambiente, args) == ERRO_TETO
    assert ambiente.sdk.chamadas == []
    assert "Teto diário atingido" in ambiente.escrever.texto


def test_teto_nao_bloqueia_abaixo_do_limite(ambiente) -> None:
    ambiente.defaults = dataclasses.replace(ambiente.defaults, limits=Limits(daily_usd=1.0))
    _salva_busca(ambiente, custo=0.002)
    assert cmd_buscar(ambiente, _args(ambiente, "buscar", PERGUNTA)) == OK


def test_gasto_de_ontem_nao_conta_para_hoje(ambiente) -> None:
    ambiente.defaults = dataclasses.replace(ambiente.defaults, limits=Limits(daily_usd=0.01))
    _salva_busca(ambiente, custo=5.0, quando=datetime.now() - timedelta(days=1))
    assert cmd_buscar(ambiente, _args(ambiente, "buscar", PERGUNTA)) == OK


def test_sem_limite_passa_por_cima(ambiente) -> None:
    ambiente.defaults = dataclasses.replace(ambiente.defaults, limits=Limits(daily_usd=0.01))
    _salva_busca(ambiente, custo=0.02)
    assert cmd_buscar(ambiente, _args(ambiente, "buscar", PERGUNTA, "--sem-limite")) == OK


def test_teto_zero_desliga_o_freio(ambiente) -> None:
    ambiente.defaults = dataclasses.replace(ambiente.defaults, limits=Limits(daily_usd=0.0))
    _salva_busca(ambiente, custo=99.0)
    assert cmd_buscar(ambiente, _args(ambiente, "buscar", PERGUNTA)) == OK


def test_teto_em_json_explica_o_bloqueio(ambiente) -> None:
    ambiente.defaults = dataclasses.replace(ambiente.defaults, limits=Limits(daily_usd=0.01))
    _salva_busca(ambiente, custo=0.02)
    assert cmd_buscar(ambiente, _args(ambiente, "buscar", PERGUNTA, "--json")) == ERRO_TETO
    assert _json_da_saida(ambiente)["error_code"] == "teto"


# ----------------------------------------------------------------- histórico, ver, gastos


def test_historico_lista_do_mais_novo(ambiente) -> None:
    _salva_busca(ambiente, prompt="antiga", quando=datetime(2026, 10, 1, 9, 0))
    _salva_busca(ambiente, prompt="recente", quando=datetime(2026, 10, 2, 9, 0))

    assert cmd_historico(ambiente, _args(ambiente, "historico", "--json")) == OK
    dados = _json_da_saida(ambiente)
    assert [s["prompt"] for s in dados["searches"]] == ["recente", "antiga"]
    assert dados["total"] == 2


def test_historico_vazio_tem_texto_amigavel(ambiente) -> None:
    assert cmd_historico(ambiente, _args(ambiente, "historico")) == OK
    assert "Nenhuma busca" in ambiente.escrever.texto


def test_historico_respeita_o_limite(ambiente) -> None:
    for i in range(4):
        _salva_busca(ambiente, prompt=f"b{i}", quando=datetime(2026, 10, 1, 9, i))
    cmd_historico(ambiente, _args(ambiente, "historico", "--limite", "2", "--json"))
    assert _json_da_saida(ambiente)["total"] == 2


def test_ver_imprime_o_markdown_salvo(ambiente) -> None:
    record = _salva_busca(ambiente)
    assert cmd_ver(ambiente, _args(ambiente, "ver", str(record.id))) == OK
    assert "# relatório" in ambiente.escrever.texto


def test_ver_em_json_traz_o_markdown_dentro(ambiente) -> None:
    record = _salva_busca(ambiente)
    cmd_ver(ambiente, _args(ambiente, "ver", str(record.id), "--json"))
    dados = _json_da_saida(ambiente)
    assert dados["id"] == record.id
    assert "# relatório" in dados["markdown"]


def test_ver_id_inexistente(ambiente) -> None:
    assert cmd_ver(ambiente, _args(ambiente, "ver", "999")) == NAO_ENCONTRADO
    assert "Não há busca #999" in ambiente.escrever.texto


def test_ver_com_arquivo_apagado(ambiente) -> None:
    record = _salva_busca(ambiente)
    record.md_path.unlink()
    assert cmd_ver(ambiente, _args(ambiente, "ver", str(record.id))) == NAO_ENCONTRADO


def test_gastos_mostra_o_dia_e_o_teto(ambiente) -> None:
    _salva_busca(ambiente, custo=0.003)
    assert cmd_gastos(ambiente, _args(ambiente, "gastos", "--json")) == OK
    dados = _json_da_saida(ambiente)
    assert dados["spent_usd"] == pytest.approx(0.003)
    assert dados["daily_limit_usd"] == pytest.approx(1.0)
    assert dados["blocked"] is False


def test_gastos_de_varios_dias(ambiente) -> None:
    _salva_busca(ambiente, custo=1.0, quando=datetime.now() - timedelta(days=3))
    cmd_gastos(ambiente, _args(ambiente, "gastos", "--dias", "7", "--json"))
    assert _json_da_saida(ambiente)["spent_usd"] == pytest.approx(1.0)


def test_gastos_sem_banco_nao_quebra(ambiente) -> None:
    assert cmd_gastos(ambiente, _args(ambiente, "gastos")) == OK
    assert "US$ 0.00000" in ambiente.escrever.texto
