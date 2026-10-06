"""Teste de fumaça da interface com cliente falso (aceite da F7).

Exercita o caminho inteiro — digitar, buscar, worker em outra thread, aba de resultado, arquivo
salvo — sem rede nenhuma. O `AgentClient` é real; o que é falso é o SDK que ele recebe.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from perplexity import AuthenticationError
from PySide6.QtCore import Qt

from condor.core.models import SearchOptions
from condor.services.client import AgentClient
from condor.services.errors import NetworkError
from condor.services.storage import Storage
from condor.ui.main_window import MainWindow
from condor.ui.result_tab import ResultTab, footer_text, strip_front_matter, tab_title
from condor.ui.search_panel import SearchPanel
from condor.ui.worker import SearchContext, execute_search
from tests.ui.fakes import SdkFalso

PERGUNTA = "Qual é a capital de Portugal?"


@pytest.fixture
def janela(qtbot, defaults, snippets, storage, secrets, raw_fast):
    """Janela pronta, com SDK falso. Devolve (janela, sdk)."""
    sdk = SdkFalso(raw_fast)
    window = MainWindow(
        defaults=defaults,
        snippets=snippets,
        storage=storage,
        secrets=secrets,
        client=AgentClient(lambda: sdk, sleep=lambda s: False),
    )
    qtbot.addWidget(window)
    return window, sdk


# ----------------------------------------------------------------- busca ponta a ponta


def test_busca_abre_aba_e_salva_o_md(qtbot, janela) -> None:
    window, sdk = janela
    assert window.tabs.count() == 1

    window.search_panel.set_prompt(PERGUNTA)
    window.search_panel.action_button.click()

    qtbot.waitUntil(lambda: isinstance(window.tabs.currentWidget(), ResultTab), timeout=5000)

    aba = window.tabs.currentWidget()
    assert isinstance(aba, ResultTab)
    assert window.tabs.count() == 2  # a aba temporária do streaming foi substituída
    assert window.tabs.tabText(1).startswith("Qual é a capital")

    # o arquivo existe e tem o conteúdo renderizado
    assert aba.record.md_path.exists()
    assert aba.record.md_path.suffix == ".md"
    assert "## Fontes" in aba.record.md_path.read_text(encoding="utf-8")
    assert aba.record.md_path.with_suffix(".json").exists()
    assert len(sdk.chamadas) == 1


def test_aba_de_resultado_tem_links_clicaveis(qtbot, janela) -> None:
    window, _ = janela
    window.search_panel.set_prompt(PERGUNTA)
    window.search_panel.action_button.click()
    qtbot.waitUntil(lambda: isinstance(window.tabs.currentWidget(), ResultTab), timeout=5000)

    aba = window.tabs.currentWidget()
    assert aba.viewer.openExternalLinks() is True
    assert "https://" in aba.markdown
    assert aba.viewer.toPlainText().strip()  # algo foi renderizado


def test_botao_volta_a_buscar_no_fim(qtbot, janela) -> None:
    window, _ = janela
    window.search_panel.set_prompt(PERGUNTA)
    window.search_panel.action_button.click()
    qtbot.waitUntil(lambda: isinstance(window.tabs.currentWidget(), ResultTab), timeout=5000)

    assert window.search_panel.action_button.text() == "Buscar"
    assert window.search_panel.running is False
    assert not window.search_panel.prompt_edit.isReadOnly()


def test_ctrl_enter_dispara_a_busca(qtbot, janela) -> None:
    window, sdk = janela
    window.show()
    qtbot.waitExposed(window)
    window.search_panel.set_prompt(PERGUNTA)
    qtbot.keyClick(window.search_panel.prompt_edit, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    qtbot.waitUntil(lambda: len(sdk.chamadas) == 1, timeout=5000)


def test_prompt_vazio_nao_busca(qtbot, janela) -> None:
    window, sdk = janela
    window.search_panel.action_button.click()
    assert sdk.chamadas == []
    assert window.tabs.count() == 1


def test_falha_mostra_mensagem_e_libera_o_botao(qtbot, defaults, snippets, storage, secrets, monkeypatch):
    """Erro de rede: a janela mostra o erro e a UI volta ao normal."""
    vistos: list[tuple[str, str]] = []
    monkeypatch.setattr(MainWindow, "show_error", lambda self, t, m: vistos.append((t, m)))

    sdk = SdkFalso({}, erro=NetworkError("Não foi possível falar com a API."))
    window = MainWindow(
        defaults=defaults,
        snippets=snippets,
        storage=storage,
        secrets=secrets,
        client=AgentClient(lambda: sdk, sleep=lambda s: False, max_attempts=1),
    )
    qtbot.addWidget(window)

    window.search_panel.set_prompt(PERGUNTA)
    window.search_panel.action_button.click()
    qtbot.waitUntil(lambda: bool(vistos), timeout=5000)

    assert vistos[0][0] == "A busca falhou"
    assert "API" in vistos[0][1]
    assert window.tabs.count() == 1
    assert window.search_panel.running is False


def test_401_oferece_trocar_a_chave(qtbot, defaults, snippets, storage, secrets, monkeypatch, raw_fast):
    """RF7: chave recusada pergunta se quer trocar, e trocar abre o diálogo."""
    perguntou: list[str] = []
    abriu: list[bool] = []
    monkeypatch.setattr(MainWindow, "ask_change_key", lambda self, m: bool(perguntou.append(m)) or True)
    monkeypatch.setattr(MainWindow, "open_api_key_dialog", lambda self: bool(abriu.append(True)))
    erros: list[str] = []
    monkeypatch.setattr(MainWindow, "show_error", lambda self, t, m: erros.append(m))

    erro = AuthenticationError("401", response=_resposta(401), body=None)
    window = MainWindow(
        defaults=defaults,
        snippets=snippets,
        storage=storage,
        secrets=secrets,
        client=AgentClient(lambda: SdkFalso(raw_fast, erro=erro), sleep=lambda s: False),
    )
    qtbot.addWidget(window)

    window.search_panel.set_prompt(PERGUNTA)
    window.search_panel.action_button.click()
    qtbot.waitUntil(lambda: bool(perguntou), timeout=5000)

    assert "chave" in perguntou[0].lower()
    assert abriu == [True]
    assert erros == []  # uma caixa só, não duas
    assert window.search_panel.running is False


def _resposta(status: int):
    import httpx

    return httpx.Response(status_code=status, request=httpx.Request("POST", "https://x"))


# ----------------------------------------------------------------- sem chave (RF7)


def test_sem_chave_a_janela_pede_a_chave(qtbot, defaults, snippets, storage, secrets_sem_chave, monkeypatch):
    abriu: list[bool] = []
    monkeypatch.setattr(MainWindow, "open_api_key_dialog", lambda self: abriu.append(True) or False)

    window = MainWindow(
        defaults=defaults,
        snippets=snippets,
        storage=storage,
        secrets=secrets_sem_chave,
        client=AgentClient(lambda: SdkFalso({}), sleep=lambda s: False),
    )
    qtbot.addWidget(window)

    assert window.ensure_key() is False
    assert abriu == [True]


def test_sem_chave_a_busca_nao_sai(qtbot, defaults, snippets, storage, secrets_sem_chave, monkeypatch):
    monkeypatch.setattr(MainWindow, "open_api_key_dialog", lambda self: False)
    sdk = SdkFalso({})
    window = MainWindow(
        defaults=defaults,
        snippets=snippets,
        storage=storage,
        secrets=secrets_sem_chave,
        client=AgentClient(lambda: sdk, sleep=lambda s: False),
    )
    qtbot.addWidget(window)

    window.search_panel.set_prompt(PERGUNTA)
    window.search_panel.action_button.click()
    assert sdk.chamadas == []


def test_chave_nova_vale_sem_reiniciar(qtbot, janela) -> None:
    """RF7: trocar a chave recria o cliente do SDK na próxima busca."""
    window, _ = janela
    window.client._ensure_client()
    assert window.client._client is not None
    window.client.forget_client()
    assert window.client._client is None


# ----------------------------------------------------------------- painel e aba, isolados


def test_painel_alterna_buscar_e_cancelar(qtbot) -> None:
    painel = SearchPanel()
    qtbot.addWidget(painel)

    assert painel.action_button.text() == "Buscar"
    painel.set_running(True)
    assert painel.action_button.text() == "Cancelar"
    assert painel.prompt_edit.isReadOnly()
    painel.set_running(False)
    assert painel.action_button.text() == "Buscar"


def test_painel_emite_cancelamento_durante_a_busca(qtbot) -> None:
    painel = SearchPanel()
    qtbot.addWidget(painel)
    painel.set_prompt(PERGUNTA)
    painel.set_running(True)

    with qtbot.waitSignal(painel.cancel_requested, timeout=1000):
        painel.action_button.click()


def test_painel_apara_o_prompt(qtbot) -> None:
    painel = SearchPanel()
    qtbot.addWidget(painel)
    painel.set_prompt("   olá   ")
    assert painel.prompt() == "olá"


@pytest.mark.parametrize(
    ("prompt", "esperado"),
    [
        ("curto", "curto"),
        ("", "Busca"),
        ("a" * 50, "a" * 40 + "…"),
        ("com\nquebra", "com quebra"),
    ],
)
def test_titulo_da_aba(prompt: str, esperado: str) -> None:
    assert tab_title(prompt) == esperado


def test_strip_front_matter_remove_o_bloco() -> None:
    md = '---\nprompt: "x"\n---\n\n# Título\n\ncorpo'
    assert strip_front_matter(md) == "# Título\n\ncorpo"


def test_strip_front_matter_sem_bloco_nao_mexe() -> None:
    assert strip_front_matter("# Só o corpo") == "# Só o corpo"


def test_rodape_mostra_custo_tokens_e_buscas() -> None:
    from condor.core.models import Usage

    texto = footer_text(Usage(input_tokens=2880, output_tokens=13, search_calls=2, cost_usd=0.00137))
    assert "US$ 0.00137" in texto
    assert "2.880 tokens" in texto
    assert "2 busca(s)" in texto


def test_rodape_sem_custo() -> None:
    from condor.core.models import Usage

    assert "custo não informado" in footer_text(Usage(1, 2, 1, None))


# ----------------------------------------------------------------- execute_search sem Qt


def test_execute_search_reporta_progresso(storage, snippets, defaults, raw_fast) -> None:
    """O fluxo do §7 é testável sem interface nenhuma."""
    passos: list[str] = []
    ctx = SearchContext(
        client=AgentClient(lambda: SdkFalso(raw_fast), sleep=lambda s: False),
        storage=storage,
        snippets=snippets,
        timeouts=defaults.timeouts,
    )
    record = execute_search(ctx, PERGUNTA, SearchOptions(), passos.append)

    assert record.md_path.exists()
    assert record.prompt == PERGUNTA
    assert len(passos) == 5
    assert passos[0].startswith("Montando")


def test_execute_search_propaga_erro_de_validacao(storage, snippets, defaults, raw_fast) -> None:
    ctx = SearchContext(
        client=AgentClient(lambda: SdkFalso(raw_fast), sleep=lambda s: False),
        storage=storage,
        snippets=snippets,
        timeouts=defaults.timeouts,
    )
    with pytest.raises(ValueError, match="Escreva a sua pergunta"):
        execute_search(ctx, "   ", SearchOptions())


def test_nada_de_rede_nos_testes_de_ui(storage: Storage, tmp_path: Path) -> None:
    """Guarda-corpo: a pasta de saída dos testes é sempre temporária."""
    assert str(tmp_path) in str(storage.output_dir)
