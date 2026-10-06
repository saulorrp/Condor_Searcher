"""Testes do histórico (TECHSPEC RF5, aceite da F9).

Os dois critérios de aceite estão aqui: o histórico sobrevive a reiniciar o app, e "Repetir"
devolve prompt e opções **idênticos** aos da busca original.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from condor.core.config import load_source_packs
from condor.core.models import (
    LocationOpt,
    SearchOptions,
    SearchRecord,
    SearchResult,
    Source,
    Usage,
)
from condor.services.client import AgentClient
from condor.services.storage import Storage
from condor.ui.history_panel import HistoryPanel
from condor.ui.main_window import MainWindow
from condor.ui.result_tab import ResultTab

ROOT = Path(__file__).resolve().parents[2]
QUANDO = datetime(2026, 10, 6, 11, 49)


@pytest.fixture(scope="session")
def packs():
    return load_source_packs(ROOT / "config" / "source_packs.toml")


def _result(custo: float | None = 0.00137) -> SearchResult:
    return SearchResult(
        response_id="resp_abc",
        model="openai/gpt-6-luna",
        text="Lisboa. [1]",
        sources=(Source(1, "https://a.pt", "A", "2026-01-01", None, "..."),),
        queries=("q",),
        usage=Usage(input_tokens=100, output_tokens=20, search_calls=2, cost_usd=custo),
        raw={"id": "resp_abc", "usage": {"input_tokens": 100, "output_tokens": 20}},
    )


def _save(storage: Storage, prompt: str, options: SearchOptions | None = None, **kw) -> SearchRecord:
    return storage.save(
        _result(kw.pop("custo", 0.00137)),
        f"# {prompt}\n\nCorpo do relatório.\n\n## Fontes\n\n1. [A](https://a.pt)\n",
        prompt,
        options or SearchOptions(),
        created_at=kw.pop("created_at", QUANDO),
    )


@pytest.fixture
def painel(qtbot, storage: Storage) -> HistoryPanel:
    widget = HistoryPanel(storage)
    qtbot.addWidget(widget)
    return widget


# ----------------------------------------------------------------- listagem


def test_comeca_vazio_sem_buscas(painel: HistoryPanel) -> None:
    assert painel.count() == 0
    assert painel.current_record() is None


def test_mostra_data_prompt_preset_e_custo(qtbot, storage: Storage) -> None:
    _save(storage, "Qual é a capital de Portugal?", SearchOptions(preset="high"))
    painel = HistoryPanel(storage)
    qtbot.addWidget(painel)

    assert painel.count() == 1
    assert painel.table.item(0, 0).text() == "06/10/2026 11:49"
    assert painel.table.item(0, 1).text() == "Qual é a capital de Portugal?"
    assert painel.table.item(0, 2).text() == "high"
    assert painel.table.item(0, 3).text() == "US$ 0.00137"


def test_custo_ausente_vira_travessao(qtbot, storage: Storage) -> None:
    _save(storage, "sem custo", custo=None)
    painel = HistoryPanel(storage)
    qtbot.addWidget(painel)
    assert painel.table.item(0, 3).text() == "—"


def test_mais_recente_primeiro(qtbot, storage: Storage) -> None:
    for dia in (4, 6, 5):
        _save(storage, f"busca {dia}", created_at=datetime(2026, 10, dia, 10, 0))
    painel = HistoryPanel(storage)
    qtbot.addWidget(painel)
    assert [painel.record_at(i).prompt for i in range(3)] == ["busca 6", "busca 5", "busca 4"]


def test_refresh_pega_buscas_novas(painel: HistoryPanel, storage: Storage) -> None:
    assert painel.count() == 0
    _save(storage, "nova")
    painel.refresh()
    assert painel.count() == 1


def test_prompt_de_varias_linhas_vira_uma_linha(qtbot, storage: Storage) -> None:
    _save(storage, "linha um\nlinha dois")
    painel = HistoryPanel(storage)
    qtbot.addWidget(painel)
    assert painel.table.item(0, 1).text() == "linha um linha dois"
    assert "\n" in painel.table.item(0, 1).toolTip()  # o original fica na dica


# ----------------------------------------------------------------- sinais


def test_duplo_clique_pede_para_reabrir(qtbot, storage: Storage) -> None:
    record = _save(storage, "pergunta")
    painel = HistoryPanel(storage)
    qtbot.addWidget(painel)

    with qtbot.waitSignal(painel.reopen_requested, timeout=1000) as sinal:
        painel.table.itemDoubleClicked.emit(painel.table.item(0, 1))
    assert sinal.args[0].id == record.id


@pytest.mark.parametrize(
    ("posicao", "sinal_esperado"),
    [(0, "reopen_requested"), (1, "repeat_requested"), (2, "open_file_requested"), (4, "delete_requested")],
)
def test_menu_de_contexto_tem_as_acoes_do_rf5(qtbot, storage, posicao: int, sinal_esperado: str) -> None:
    record = _save(storage, "pergunta")
    painel = HistoryPanel(storage)
    qtbot.addWidget(painel)

    menu = painel.build_menu(record)
    acoes = menu.actions()
    assert [a.text() for a in acoes if a.text()][:3] == [
        "Abrir",
        "Repetir busca com as mesmas opções",
        "Abrir arquivo .md",
    ]
    assert "não apaga" in acoes[4].text()

    with qtbot.waitSignal(getattr(painel, sinal_esperado), timeout=1000):
        acoes[posicao].trigger()


# ----------------------------------------------------------------- janela: reabrir e repetir


@pytest.fixture
def janela(qtbot, defaults, snippets, storage, secrets, packs):
    window = MainWindow(
        defaults=defaults,
        snippets=snippets,
        storage=storage,
        secrets=secrets,
        client=AgentClient(lambda: object(), sleep=lambda s: False),
        packs=packs,
        project_root=ROOT,
    )
    qtbot.addWidget(window)
    return window


def test_janela_tem_o_painel_de_historico(janela) -> None:
    assert janela.history is not None
    assert janela.history.windowTitle() == "Histórico"


def test_reabrir_mostra_o_markdown_salvo(janela, storage: Storage) -> None:
    record = _save(storage, "Qual é a capital de Portugal?")
    janela.history.refresh()

    aba = janela.open_record(record)
    assert isinstance(aba, ResultTab)
    assert janela.tabs.count() == 2
    assert "Corpo do relatório." in aba.markdown
    assert janela.tabs.currentWidget() is aba


def test_reabrir_duas_vezes_nao_duplica_a_aba(janela, storage: Storage) -> None:
    record = _save(storage, "pergunta")
    primeira = janela.open_record(record)
    segunda = janela.open_record(record)
    assert primeira is segunda
    assert janela.tabs.count() == 2


def test_reabrir_sem_o_arquivo_avisa_em_portugues(janela, storage: Storage, monkeypatch) -> None:
    vistos: list[str] = []
    monkeypatch.setattr(MainWindow, "show_error", lambda self, t, m: vistos.append(m))

    record = _save(storage, "pergunta")
    record.md_path.unlink()

    assert janela.open_record(record) is None
    assert "Não consegui abrir o relatório" in vistos[0]
    assert janela.tabs.count() == 1


def test_rodape_sobrevive_a_json_ausente(janela, storage: Storage) -> None:
    record = _save(storage, "pergunta")
    record.md_path.with_suffix(".json").unlink()
    aba = janela.open_record(record)
    assert "0.00137" in aba.footer.text()  # custo vem do histórico


def test_repetir_preenche_prompt_e_opcoes_identicos(janela, storage: Storage) -> None:
    """Critério de aceite da F9."""
    opcoes = SearchOptions(
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
        priorities=("primarias", "confianca"),
    )
    record = _save(storage, "Pergunta original", opcoes)

    janela.repeat_record(record)

    assert janela.search_panel.prompt() == "Pergunta original"
    assert janela.options_widget.options() == opcoes
    assert janela.tabs.currentIndex() == 0  # volta para a aba de busca


def test_repetir_remarca_o_pacote_em_vez_de_jogar_nos_extras(janela, storage: Storage, packs) -> None:
    """O histórico só guarda os domínios; remarcar o pacote mantém a tela coerente."""
    pack = packs[0]
    record = _save(storage, "pergunta", SearchOptions(domains=pack.domains))

    janela.repeat_record(record)

    assert janela.options_widget.selected_packs() == (pack.key,)
    assert janela.options_widget.form.extra_domains.toPlainText() == ""
    assert janela.options_widget.options().domains == pack.domains


def test_repetir_nao_dispara_busca_sozinho(janela, storage: Storage) -> None:
    janela.repeat_record(_save(storage, "pergunta"))
    assert janela.search_panel.running is False


# ----------------------------------------------------------------- excluir


def test_excluir_tira_do_historico_e_preserva_os_arquivos(janela, storage: Storage, monkeypatch) -> None:
    monkeypatch.setattr(MainWindow, "ask_delete", lambda self, r: True)
    record = _save(storage, "pergunta")
    janela.history.refresh()
    assert janela.history.count() == 1

    janela.delete_record(record)

    assert janela.history.count() == 0
    assert storage.get(record.id) is None
    assert record.md_path.exists()
    assert record.md_path.with_suffix(".json").exists()


def test_excluir_respeita_o_cancelar(janela, storage: Storage, monkeypatch) -> None:
    monkeypatch.setattr(MainWindow, "ask_delete", lambda self, r: False)
    record = _save(storage, "pergunta")
    janela.history.refresh()

    janela.delete_record(record)

    assert janela.history.count() == 1
    assert storage.get(record.id) is not None


# ----------------------------------------------------------------- persistência (aceite)


def test_historico_sobrevive_a_reiniciar_o_app(qtbot, defaults, snippets, secrets, packs, tmp_path) -> None:
    """Critério de aceite da F9: fecha o app, abre de novo, histórico lá."""
    pasta = tmp_path / "saida"
    storage = Storage(pasta)
    _save(storage, "busca de ontem")

    def abrir() -> MainWindow:
        window = MainWindow(
            defaults=defaults,
            snippets=snippets,
            storage=Storage(pasta),
            secrets=secrets,
            client=AgentClient(lambda: object(), sleep=lambda s: False),
            packs=packs,
            project_root=ROOT,
        )
        qtbot.addWidget(window)
        return window

    primeira = abrir()
    assert primeira.history.count() == 1
    primeira.close()

    segunda = abrir()
    assert segunda.history.count() == 1
    assert segunda.history.record_at(0).prompt == "busca de ontem"


def test_registro_do_historico_reabre_com_as_opcoes_salvas(qtbot, storage: Storage) -> None:
    """Ida e volta pelo banco: as opções da linha são as mesmas que foram gravadas."""
    opcoes = SearchOptions(preset="xhigh", domains=("x.pt",), custom_instructions="seja breve")
    record = _save(storage, "pergunta", opcoes)
    painel = HistoryPanel(storage)
    qtbot.addWidget(painel)
    assert painel.record_at(0).options == opcoes
    assert painel.record_at(0).id == record.id


def test_json_salvo_continua_legivel_apos_reabrir(storage: Storage) -> None:
    record = _save(storage, "pergunta")
    bruto = json.loads(record.md_path.with_suffix(".json").read_text(encoding="utf-8"))
    assert bruto["id"] == "resp_abc"
