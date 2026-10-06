"""Testes do painel de opções (TECHSPEC RF4, aceite da F8).

Os dois critérios de aceite estão aqui: cada opção muda o payload do "Ver prompt final", e
combinação inválida desabilita o Buscar com uma dica em português.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from PySide6.QtCore import Qt

from condor.core.config import load_source_packs
from condor.core.models import MAX_DOMAINS, LocationOpt, SearchOptions
from condor.ui.options_form import PRESET_ADVANCED
from condor.ui.options_widget import OptionsWidget
from condor.ui.search_panel import SearchPanel

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def packs():
    return load_source_packs(ROOT / "config" / "source_packs.toml")


@pytest.fixture
def painel(qtbot, defaults, snippets, packs) -> OptionsWidget:
    widget = OptionsWidget(defaults, snippets, packs)
    qtbot.addWidget(widget)
    return widget


def _payload(painel: OptionsWidget) -> dict:
    texto = painel.payload_preview()
    return json.loads(texto[texto.index("{") :])


def _tool(painel: OptionsWidget) -> dict:
    return _payload(painel)["tools"][0]


# ----------------------------------------------------------------- estado inicial


def test_comeca_nos_defaults_do_toml(painel: OptionsWidget, defaults) -> None:
    assert painel.options() == defaults.options


def test_comeca_recolhido(painel: OptionsWidget) -> None:
    """`isHidden`, e não `isVisible`: o painel não está dentro de uma janela mostrada no teste."""
    assert painel.body.isHidden() is True
    painel.toggle.setChecked(True)
    assert painel.body.isHidden() is False


def test_resumo_mostra_o_que_esta_valendo(painel: OptionsWidget) -> None:
    assert "Padrão" in painel.summary.text()
    painel.form.extra_domains.setPlainText("a.pt\nb.pt")
    assert "2 domínio(s)" in painel.summary.text()


def test_rotulos_vem_dos_toml(painel: OptionsWidget, snippets) -> None:
    rotulos = [painel.form.format_combo.itemText(i) for i in range(painel.form.format_combo.count())]
    assert rotulos == [s.label for s in snippets.formats]
    assert set(painel.form.priority_checks) == {s.key for s in snippets.priorities}


# ----------------------------------------------------------------- cada opção muda o payload


def test_preset_muda_o_payload(painel: OptionsWidget) -> None:
    assert _payload(painel)["preset"] == "low"
    painel.form.preset_combo.setCurrentIndex(painel.form.preset_combo.findData("high"))
    assert _payload(painel)["preset"] == "high"


def test_profundidade_de_leitura_muda_o_payload(painel: OptionsWidget) -> None:
    painel.form.context_combo.setCurrentIndex(painel.form.context_combo.findData("high"))
    assert _tool(painel)["search_context_size"] == "high"


def test_max_resultados_muda_o_payload(painel: OptionsWidget) -> None:
    painel.form.max_results_spin.setValue(42)
    assert _tool(painel)["max_results"] == 42


def test_dominios_extras_viram_filtro(painel: OptionsWidget) -> None:
    painel.form.extra_domains.setPlainText("dglab.gov.pt\narquivos.pt")
    assert _tool(painel)["filters"]["search_domain_filter"] == ["dglab.gov.pt", "arquivos.pt"]


def test_modo_excluir_prefixa_com_hifen(painel: OptionsWidget) -> None:
    painel.form.extra_domains.setPlainText("pinterest.com")
    painel.form.mode_combo.setCurrentIndex(painel.form.mode_combo.findData("deny"))
    assert _tool(painel)["filters"]["search_domain_filter"] == ["-pinterest.com"]


def test_pacote_de_fontes_entra_no_filtro(painel: OptionsWidget, packs) -> None:
    item = painel.form.packs_list.item(0)
    item.setCheckState(Qt.CheckState.Checked)
    enviados = _tool(painel)["filters"]["search_domain_filter"]
    assert enviados[: len(packs[0].domains)] == list(packs[0].domains)


def test_periodo_vira_recency(painel: OptionsWidget) -> None:
    painel.form.period_combo.setCurrentIndex(painel.form.period_combo.findData("month"))
    assert _tool(painel)["filters"]["search_recency_filter"] == "month"


def test_intervalo_de_datas_vira_mm_dd_yyyy(painel: OptionsWidget) -> None:
    from PySide6.QtCore import QDate

    painel.form.period_combo.setCurrentIndex(painel.form.period_combo.findData("range"))
    painel.form.after_edit.setDate(QDate(2026, 1, 31))
    painel.form.before_edit.setDate(QDate(2026, 6, 30))
    filtros = _tool(painel)["filters"]
    assert filtros["search_after_date_filter"] == "01/31/2026"
    assert filtros["search_before_date_filter"] == "06/30/2026"
    assert "search_recency_filter" not in filtros


def test_localizacao_entra_e_sai_do_payload(painel: OptionsWidget) -> None:
    assert "user_location" not in _tool(painel)
    painel.form.location_check.setChecked(True)
    painel.form.country_edit.setText("br")
    assert _tool(painel)["user_location"]["country"] == "BR"
    painel.form.location_check.setChecked(False)
    assert "user_location" not in _tool(painel)


def test_idioma_e_formato_mudam_o_briefing(painel: OptionsWidget) -> None:
    painel.form.language_combo.setCurrentIndex(painel.form.language_combo.findData("en"))
    painel.form.format_combo.setCurrentIndex(painel.form.format_combo.findData("tabela"))
    entrada = _payload(painel)["input"]
    assert "Idioma da resposta: inglês." in entrada
    assert "tabela comparativa" in entrada


def test_prioridades_mudam_o_briefing(painel: OptionsWidget) -> None:
    for check in painel.form.priority_checks.values():
        check.setChecked(False)
    assert "Prioridades:" not in _payload(painel)["input"]
    painel.form.priority_checks["confianca"].setChecked(True)
    assert "nível de confiança" in _payload(painel)["input"]


def test_instrucoes_proprias_so_valem_no_avancado(painel: OptionsWidget) -> None:
    painel.form.instructions_edit.setPlainText("responda como arquivista")
    assert "instructions" not in _payload(painel)

    painel.form.advanced_check.setChecked(True)
    painel.form.instructions_edit.setPlainText("responda como arquivista")
    payload = _payload(painel)
    assert payload["instructions"].startswith("responda como arquivista")
    assert "[1] ou [1][2]" in payload["instructions"]  # regras de citação reanexadas


def test_preset_agente_so_aparece_no_avancado(painel: OptionsWidget) -> None:
    assert painel.form.preset_combo.findData(PRESET_ADVANCED[0]) == -1
    painel.form.advanced_check.setChecked(True)
    assert painel.form.preset_combo.findData(PRESET_ADVANCED[0]) != -1

    painel.form.preset_combo.setCurrentIndex(painel.form.preset_combo.findData("xhigh"))
    painel.form.advanced_check.setChecked(False)
    assert painel.options().preset == "low"  # volta para o padrão ao esconder


def test_previa_nunca_traz_a_chave(painel: OptionsWidget) -> None:
    assert "pplx-" not in painel.payload_preview()
    assert "timeout:" in painel.payload_preview()


def test_previa_usa_o_prompt_digitado(painel: OptionsWidget) -> None:
    texto = painel.payload_preview("minha pergunta")
    payload = json.loads(texto[texto.index("{") :])
    assert "<pergunta>\nminha pergunta\n</pergunta>" in payload["input"]


# ----------------------------------------------------------------- contador e validade


def test_contador_de_dominios(painel: OptionsWidget) -> None:
    assert painel.form.domain_counter.text() == f"0/{MAX_DOMAINS} domínios"
    painel.form.extra_domains.setPlainText("a.pt\nb.pt\nc.pt")
    assert painel.form.domain_counter.text() == f"3/{MAX_DOMAINS} domínios"


def test_dominios_repetidos_contam_uma_vez(painel: OptionsWidget) -> None:
    painel.form.extra_domains.setPlainText("a.pt\na.pt\n-a.pt\n  a.pt  ")
    assert painel.domains() == ("a.pt",)


def test_passar_de_20_dominios_invalida_a_busca(qtbot, painel: OptionsWidget) -> None:
    """Aceite da F8: combinação inválida desabilita o Buscar com dica."""
    with qtbot.waitSignal(painel.validity_changed) as sinal:
        painel.form.extra_domains.setPlainText("\n".join(f"d{i}.pt" for i in range(MAX_DOMAINS + 1)))

    ok, dica = sinal.args
    assert ok is False
    assert "20 domínios" in dica
    assert painel.validate()[0] is False
    assert "⚠" in painel.summary.text()


def test_voltar_para_20_revalida(painel: OptionsWidget) -> None:
    painel.form.extra_domains.setPlainText("\n".join(f"d{i}.pt" for i in range(MAX_DOMAINS + 1)))
    assert painel.validate()[0] is False
    painel.form.extra_domains.setPlainText("\n".join(f"d{i}.pt" for i in range(MAX_DOMAINS)))
    assert painel.validate()[0] is True


def test_localizacao_sem_pais_invalida(painel: OptionsWidget) -> None:
    painel.form.location_check.setChecked(True)
    painel.form.country_edit.setText("Portugal")
    ok, dica = painel.validate()
    assert ok is False
    assert "duas letras" in dica


def test_previa_explica_quando_invalido(painel: OptionsWidget) -> None:
    painel.form.extra_domains.setPlainText("\n".join(f"d{i}.pt" for i in range(MAX_DOMAINS + 1)))
    assert "não formam uma busca válida" in painel.payload_preview()


# ----------------------------------------------------------------- ida e volta / padrões


def test_set_options_e_options_fazem_ida_e_volta(painel: OptionsWidget) -> None:
    opcoes = SearchOptions(
        preset="medium",
        domains=("x.pt", "y.pt"),
        domain_mode="deny",
        after=date(2026, 1, 31),
        before=date(2026, 6, 30),
        location=LocationOpt("BR", "SC", "Florianópolis"),
        context_size="high",
        max_results=7,
        language="es",
        output_format="bibliografia",
        priorities=("foruns",),
        custom_instructions="seja breve",
    )
    painel.set_options(opcoes)
    assert painel.options() == opcoes


def test_dominio_de_pacote_marcado_nao_duplica_nos_extras(painel: OptionsWidget, packs) -> None:
    pack = packs[0]
    painel.set_options(SearchOptions(domains=pack.domains + ("extra.pt",)), source_packs=(pack.key,))
    assert painel.form.extra_domains.toPlainText() == "extra.pt"
    assert painel.options().domains == pack.domains + ("extra.pt",)


def test_restaurar_padroes(painel: OptionsWidget, defaults) -> None:
    painel.form.preset_combo.setCurrentIndex(painel.form.preset_combo.findData("high"))
    painel.form.extra_domains.setPlainText("lixo.pt")
    painel.restore_defaults()
    assert painel.options() == defaults.options


def test_mudanca_emite_changed(qtbot, painel: OptionsWidget) -> None:
    with qtbot.waitSignal(painel.changed, timeout=1000):
        painel.form.max_results_spin.setValue(9)


# ----------------------------------------------------------------- integração com o painel


def test_painel_de_busca_desabilita_o_botao_com_dica(qtbot) -> None:
    painel = SearchPanel()
    qtbot.addWidget(painel)

    painel.set_search_enabled(False, "Escolheu domínios demais.")
    assert painel.action_button.isEnabled() is False
    assert painel.action_button.toolTip() == "Escolheu domínios demais."
    assert "demais" in painel.hint.text()

    painel.set_search_enabled(True)
    assert painel.action_button.isEnabled() is True
    assert painel.hint.text() == "Ctrl+Enter para buscar"


def test_botao_desabilitado_nao_dispara_busca(qtbot) -> None:
    painel = SearchPanel()
    qtbot.addWidget(painel)
    painel.set_prompt("pergunta")
    painel.set_search_enabled(False, "inválido")

    disparos: list[str] = []
    painel.search_requested.connect(disparos.append)
    painel.action_button.click()
    painel.prompt_edit.submitted.emit()  # Ctrl+Enter também não passa
    assert disparos == []


def test_cancelar_continua_clicavel_com_opcoes_invalidas(qtbot) -> None:
    """Desabilitar o Buscar não pode prender uma busca em andamento."""
    painel = SearchPanel()
    qtbot.addWidget(painel)
    painel.set_search_enabled(False, "inválido")
    painel.set_running(True)
    assert painel.action_button.isEnabled() is True
    assert painel.action_button.text() == "Cancelar"
