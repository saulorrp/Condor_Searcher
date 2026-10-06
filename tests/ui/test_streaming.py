"""Testes do streaming (F10): cliente, worker e a aba temporária.

Nenhuma chamada de rede: o SDK falso de `tests/ui/fakes.py` emite os mesmos eventos que o SDK
real (`response.output_text.delta`, `response.reasoning.search_results`, `response.completed`).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from perplexity import APITimeoutError, AuthenticationError

from condor.core.models import AgentRequest, SearchOptions
from condor.services.client import AgentClient
from condor.services.errors import AuthError, CancelledError, NetworkError
from condor.ui.main_window import MainWindow
from condor.ui.result_tab import ResultTab, StreamingTab
from condor.ui.worker import SearchContext, execute_search
from tests.ui.fakes import FakeEvent, FakeResponse, SdkFalso, stream_events

ROOT = Path(__file__).resolve().parents[2]
PERGUNTA = "Qual é a capital de Portugal?"


class Sink:
    """Coleta o que o cliente entrega, no lugar dos sinais do Qt."""

    def __init__(self) -> None:
        self.pedacos: list[str] = []
        self.reinicios = 0
        self.notas: list[str] = []

    def delta(self, texto: str) -> None:
        self.pedacos.append(texto)

    def restart(self) -> None:
        self.reinicios += 1
        self.pedacos.clear()

    def note(self, mensagem: str) -> None:
        self.notas.append(mensagem)

    @property
    def texto(self) -> str:
        return "".join(self.pedacos)


@pytest.fixture
def req() -> AgentRequest:
    return AgentRequest(payload={"preset": "fast", "input": "pergunta"}, briefing="b", timeout_s=60)


# ----------------------------------------------------------------- cliente


def test_sem_sink_nao_pede_streaming(raw_fast, req) -> None:
    """O modo normal continua intacto: quem não quer streaming não recebe `stream` no payload."""
    sdk = SdkFalso(raw_fast)
    AgentClient(lambda: sdk, sleep=lambda s: False).run(req)
    assert "stream" not in sdk.chamadas[0]


def test_com_sink_pede_streaming_e_devolve_o_mesmo_dict(raw_fast, req) -> None:
    sdk = SdkFalso(raw_fast)
    sink = Sink()
    saida = AgentClient(lambda: sdk, sleep=lambda s: False).run(req, sink)

    assert sdk.chamadas[0]["stream"] is True
    assert saida == raw_fast  # o resto do app não percebe diferença
    assert sink.texto == "Lisboa."


def test_notas_de_progresso_contam_as_fontes(raw_fast, req) -> None:
    sink = Sink()
    AgentClient(lambda: SdkFalso(raw_fast), sleep=lambda s: False).run(req, sink)
    assert sink.notas == ["2 fonte(s) encontradas…"]


def test_eventos_desconhecidos_sao_ignorados(raw_fast, req) -> None:
    """O fluxo típico do SDK falso já inclui um evento inventado; não pode quebrar nada."""
    sink = Sink()
    AgentClient(lambda: SdkFalso(raw_fast), sleep=lambda s: False).run(req, sink)
    assert sink.texto == "Lisboa."


def test_fluxo_e_fechado_no_fim(raw_fast, req) -> None:
    sdk = SdkFalso(raw_fast)
    AgentClient(lambda: sdk, sleep=lambda s: False).run(req, Sink())
    assert sdk.fechado is True


def test_sem_evento_final_e_erro_com_dica(raw_fast, req) -> None:
    eventos = [FakeEvent("response.output_text.delta", delta="Lis")]
    sdk = SdkFalso(raw_fast, eventos=eventos)
    with pytest.raises(NetworkError, match="sem o evento final"):
        AgentClient(lambda: sdk, sleep=lambda s: False, max_attempts=1).run(req, Sink())


def test_evento_de_falha_vira_erro_nosso(raw_fast, req) -> None:
    erro = type("Erro", (), {"message": "deu ruim no servidor", "code": "500"})()
    eventos = [FakeEvent("response.failed", error=erro)]
    with pytest.raises(NetworkError, match="falhou no meio do caminho"):
        AgentClient(lambda: SdkFalso(raw_fast, eventos=eventos), sleep=lambda s: False, max_attempts=1).run(
            req, Sink()
        )


def test_falha_de_chave_no_fluxo_vira_auth_error(raw_fast, req) -> None:
    erro = type("Erro", (), {"message": "invalid api_key", "code": "401"})()
    eventos = [FakeEvent("response.failed", error=erro)]
    with pytest.raises(AuthError, match="recusada durante a busca"):
        AgentClient(lambda: SdkFalso(raw_fast, eventos=eventos), sleep=lambda s: False).run(req, Sink())


def test_erro_do_sdk_ao_abrir_o_fluxo_e_traduzido(raw_fast, req) -> None:
    import httpx

    erro = AuthenticationError(
        "401", response=httpx.Response(401, request=httpx.Request("POST", "https://x")), body=None
    )
    with pytest.raises(AuthError):
        AgentClient(lambda: SdkFalso(raw_fast, erro=erro), sleep=lambda s: False).run(req, Sink())


def test_retry_avisa_o_sink_para_apagar_o_texto(raw_fast, req) -> None:
    """Critério do streaming com retry: o texto da tentativa que falhou não pode ficar na tela."""

    class SdkInstavel(SdkFalso):
        def create(self, **kwargs):
            self.chamadas.append(kwargs)
            if len(self.chamadas) == 1:
                raise APITimeoutError(request=__import__("httpx").Request("POST", "https://x"))
            from tests.ui.fakes import FakeStream

            return FakeStream(self, stream_events(self.raw))

    sdk = SdkInstavel(raw_fast)
    sink = Sink()
    saida = AgentClient(lambda: sdk, sleep=lambda s: False).run(req, sink)

    assert saida == raw_fast
    assert sink.reinicios == 1
    assert sink.texto == "Lisboa."  # só o texto da tentativa boa


def test_cancelamento_no_meio_do_fluxo(raw_fast, req) -> None:
    cliente = AgentClient(lambda: SdkFalso(raw_fast), sleep=lambda s: False)

    class SinkQueCancela(Sink):
        def delta(self, texto: str) -> None:
            super().delta(texto)
            cliente.cancel()

    with pytest.raises(CancelledError):
        cliente.run(req, SinkQueCancela())


def test_resposta_do_evento_final_passa_pelo_model_dump(req) -> None:
    raw = {
        "id": "resp_x",
        "output": [{"type": "message", "content": [{"type": "output_text", "text": "ok"}]}],
    }
    eventos = [FakeEvent("response.completed", response=FakeResponse(raw))]
    saida = AgentClient(lambda: SdkFalso(raw, eventos=eventos), sleep=lambda s: False).run(req, Sink())
    assert saida == raw


# ----------------------------------------------------------------- worker


def test_worker_sem_streaming_nao_cria_sink(storage, snippets, defaults, raw_fast) -> None:
    sdk = SdkFalso(raw_fast)
    ctx = SearchContext(
        client=AgentClient(lambda: sdk, sleep=lambda s: False),
        storage=storage,
        snippets=snippets,
        timeouts=defaults.timeouts,
    )
    execute_search(ctx, PERGUNTA, SearchOptions(), None, None)
    assert "stream" not in sdk.chamadas[0]


def test_execute_search_entrega_o_texto_ao_sink(storage, snippets, defaults, raw_fast) -> None:
    sink = Sink()
    ctx = SearchContext(
        client=AgentClient(lambda: SdkFalso(raw_fast), sleep=lambda s: False),
        storage=storage,
        snippets=snippets,
        timeouts=defaults.timeouts,
    )
    record = execute_search(ctx, PERGUNTA, SearchOptions(), None, sink)
    assert sink.texto == "Lisboa."
    assert record.md_path.exists()


# ----------------------------------------------------------------- aba temporária


def test_aba_de_streaming_acumula_e_reseta(qtbot) -> None:
    aba = StreamingTab("pergunta")
    qtbot.addWidget(aba)

    aba.append("Lis")
    aba.append("boa.")
    assert aba.text() == "Lisboa."
    assert aba.viewer.toPlainText() == "Lisboa."

    aba.reset()
    assert aba.text() == ""
    assert "recomeçando" in aba.footer.text()


# ----------------------------------------------------------------- janela


@pytest.fixture
def janela(qtbot, defaults, snippets, storage, secrets, raw_fast, settings_tmp):
    sdk = SdkFalso(raw_fast)
    window = MainWindow(
        defaults=defaults,
        snippets=snippets,
        storage=storage,
        secrets=secrets,
        client=AgentClient(lambda: sdk, sleep=lambda s: False),
        settings=settings_tmp,
        project_root=ROOT,
    )
    qtbot.addWidget(window)
    return window, sdk


def test_streaming_ligado_por_padrao(janela) -> None:
    window, _ = janela
    assert window.stream_enabled is True
    assert window.stream_action.isChecked() is True


def test_aba_temporaria_aparece_e_e_substituida(qtbot, janela) -> None:
    window, _ = janela
    vistas: list[str] = []
    window.search_panel.set_prompt(PERGUNTA)

    def anota() -> None:
        atual = window.tabs.currentWidget()
        if isinstance(atual, StreamingTab) and "temporária" not in vistas:
            vistas.append("temporária")

    window.tabs.currentChanged.connect(lambda _: anota())
    window.search_panel.action_button.click()
    qtbot.waitUntil(lambda: isinstance(window.tabs.currentWidget(), ResultTab), timeout=5000)

    assert vistas == ["temporária"]  # a aba temporária apareceu…
    assert window.tabs.count() == 2  # …e saiu, deixando só a definitiva
    assert not any(isinstance(window.tabs.widget(i), StreamingTab) for i in range(window.tabs.count()))


def test_desligar_o_streaming_nao_pede_stream_ao_sdk(qtbot, janela) -> None:
    window, sdk = janela
    window.stream_action.setChecked(False)
    assert window.stream_enabled is False

    window.search_panel.set_prompt(PERGUNTA)
    window.search_panel.action_button.click()
    qtbot.waitUntil(lambda: isinstance(window.tabs.currentWidget(), ResultTab), timeout=5000)
    assert "stream" not in sdk.chamadas[0]


def test_preferencia_de_streaming_sobrevive_ao_fechar(qtbot, janela, settings_tmp) -> None:
    window, _ = janela
    window.stream_action.setChecked(False)
    window.close()
    assert settings_tmp.load_flag("stream", True) is False


def test_falha_remove_a_aba_temporaria(qtbot, defaults, snippets, storage, secrets, raw_fast) -> None:
    """Se a busca falha no meio, o texto parcial não pode ficar numa aba órfã."""
    eventos = [FakeEvent("response.output_text.delta", delta="Lis")]  # sem evento final
    window = MainWindow(
        defaults=defaults,
        snippets=snippets,
        storage=storage,
        secrets=secrets,
        client=AgentClient(
            lambda: SdkFalso(raw_fast, eventos=eventos), sleep=lambda s: False, max_attempts=1
        ),
        project_root=ROOT,
    )
    qtbot.addWidget(window)

    window.search_panel.set_prompt(PERGUNTA)
    window.search_panel.action_button.click()
    qtbot.waitUntil(lambda: window.search_panel.running is False, timeout=5000)

    assert window.tabs.count() == 1
    assert window._streaming_tab is None
