"""Janela principal: abas, barra de status e o ciclo de uma busca (TECHSPEC RF1, RF2, §7)."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, Qt, QThreadPool, QTimer, QUrl, Slot
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices
from PySide6.QtWidgets import (
    QMainWindow,
    QTabWidget,
    QWidget,
)

from condor.core.config import Defaults, Snippets, SourcePack
from condor.core.models import SearchOptions, SearchRecord
from condor.services.client import AgentClient
from condor.services.secrets import SecretStore
from condor.services.settings_store import SettingsStore
from condor.services.storage import Storage
from condor.ui.api_key_dialog import ApiKeyDialog
from condor.ui.assets import app_icon
from condor.ui.dialogs import DialogMixin
from condor.ui.history_actions import HistoryActionsMixin
from condor.ui.history_panel import HistoryPanel
from condor.ui.options_widget import OptionsWidget
from condor.ui.result_tab import StreamingTab, tab_title
from condor.ui.search_panel import SearchPanel
from condor.ui.worker import SearchContext, SearchWorker

logger = logging.getLogger(__name__)

TITULO = "Condor Searcher"


class MainWindow(HistoryActionsMixin, DialogMixin, QMainWindow):
    """Uma aba fixa de busca + uma aba por resultado."""

    def __init__(
        self,
        defaults: Defaults,
        snippets: Snippets,
        storage: Storage,
        secrets: SecretStore,
        client: AgentClient,
        settings: SettingsStore | None = None,
        packs: tuple[SourcePack, ...] = (),
        project_root: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.defaults = defaults
        self.storage = storage
        self.secrets = secrets
        self.client = client
        self.settings = settings
        self.packs = packs
        self.stream_enabled = settings.load_flag("stream", True) if settings is not None else True
        self._streaming_tab: StreamingTab | None = None
        project_root = project_root or Path.cwd()
        self._ctx = SearchContext(
            client=client, storage=storage, snippets=snippets, timeouts=defaults.timeouts
        )

        self._pool = QThreadPool.globalInstance()
        self._elapsed = QElapsedTimer()
        self._ticker = QTimer(self)
        self._ticker.setInterval(1000)
        self._ticker.timeout.connect(self._tick)
        self._status_base = ""

        self.setWindowTitle(TITULO)
        self.resize(1000, 760)
        icone = app_icon(project_root)
        if not icone.isNull():
            self.setWindowIcon(icone)

        self.search_panel = SearchPanel(self)
        self.search_panel.search_requested.connect(self.start_search)
        self.search_panel.cancel_requested.connect(self.cancel_search)

        self.options_widget = OptionsWidget(defaults, snippets, packs, self)
        self.options_widget.validity_changed.connect(self.search_panel.set_search_enabled)
        self.search_panel.set_options_widget(self.options_widget)
        if settings is not None:
            # A última configuração usada volta ao abrir (RF4).
            self.options_widget.set_options(
                settings.load(defaults.options),
                settings.load_source_packs(defaults.source_packs),
            )

        self.tabs = QTabWidget(self)
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self._close_tab)
        self.tabs.addTab(self.search_panel, "Nova busca")
        self.tabs.tabBar().setTabButton(0, self.tabs.tabBar().ButtonPosition.RightSide, None)
        self.setCentralWidget(self.tabs)

        self.history = HistoryPanel(storage, self)
        self.history.reopen_requested.connect(self.open_record)
        self.history.repeat_requested.connect(self.repeat_record)
        self.history.open_file_requested.connect(self.open_record_file)
        self.history.delete_requested.connect(self.delete_record)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.history)

        self._build_menu()
        self.statusBar().showMessage("Pronto.")

    @property
    def options(self) -> SearchOptions:
        """As opções de agora, lidas do painel — nunca uma cópia guardada."""
        return self.options_widget.options()

    # ------------------------------------------------------------------ menu

    def _build_menu(self) -> None:
        config = self.menuBar().addMenu("&Configurações")

        chave = QAction("Chave da API…", self)
        chave.triggered.connect(self.open_api_key_dialog)
        config.addAction(chave)

        prompt_final = QAction("Ver prompt final…", self)
        prompt_final.triggered.connect(lambda: self.options_widget.show_preview(self.search_panel.prompt()))
        config.addAction(prompt_final)

        pasta = QAction("Abrir pasta de resultados", self)
        pasta.triggered.connect(self._open_output_dir)
        config.addAction(pasta)

        exibir = self.menuBar().addMenu("&Exibir")
        exibir.addAction(self.history.toggleViewAction())

        self.stream_action = QAction("Mostrar a resposta enquanto chega", self)
        self.stream_action.setCheckable(True)
        self.stream_action.setChecked(self.stream_enabled)
        self.stream_action.setToolTip(
            "Desligue se a busca falhar com erro de fluxo; o resultado é o mesmo, só aparece de uma vez."
        )
        self.stream_action.toggled.connect(self._set_stream_enabled)
        exibir.addAction(self.stream_action)

    # ------------------------------------------------------------------ chave

    def ensure_key(self) -> bool:
        """Sem chave, abre o diálogo antes de a janela ficar utilizável (RF7)."""
        if self.secrets.get_key() is not None:
            return True
        self.statusBar().showMessage("Configure a chave da API para começar.")
        return self.open_api_key_dialog()

    @Slot()
    def open_api_key_dialog(self) -> bool:
        dialogo = ApiKeyDialog(self.secrets, self)
        dialogo.exec()
        if dialogo.saved:
            # A chave mudou: o próximo `run()` recria o cliente do SDK (RF7: sem reiniciar).
            self.client.forget_client()
            self.statusBar().showMessage("Chave atualizada.")
        return self.secrets.get_key() is not None

    # ------------------------------------------------------------------ busca

    @Slot(str)
    def start_search(self, prompt: str) -> None:
        if self.search_panel.running:
            return
        if not self.ensure_key():
            return

        self.client.reset()  # um cancelamento anterior não pode valer para esta busca (F5)
        self.search_panel.set_running(True)
        self._status_base = f"Buscando (preset {self.options.preset})"
        self._elapsed.start()
        self._ticker.start()
        self._tick()

        worker = SearchWorker(self._ctx, prompt, self.options, stream=self.stream_enabled)
        worker.signals.finished.connect(self._on_finished)
        worker.signals.failed.connect(self._on_failed)
        worker.signals.auth_failed.connect(self._on_auth_failed)
        worker.signals.cancelled.connect(self._on_cancelled)
        worker.signals.progress.connect(self._on_progress)
        worker.signals.delta.connect(self._on_delta)
        worker.signals.restarted.connect(self._on_restarted)
        self._pool.start(worker)

    @Slot()
    def cancel_search(self) -> None:
        self.client.cancel()
        self.statusBar().showMessage("Cancelando… a chamada em andamento ainda termina.")

    # ------------------------------------------------------------------ sinais do worker

    @Slot(str)
    def _on_progress(self, texto: str) -> None:
        self._status_base = texto.rstrip("…")
        self._tick()

    @Slot(str)
    def _on_delta(self, pedaco: str) -> None:
        """Primeiro pedaço abre a aba temporária; os seguintes só acrescentam."""
        if self._streaming_tab is None:
            self._streaming_tab = StreamingTab(self.search_panel.prompt(), parent=self)
            indice = self.tabs.addTab(self._streaming_tab, f"⏳ {tab_title(self._streaming_tab.prompt)}")
            self.tabs.setCurrentIndex(indice)
        self._streaming_tab.append(pedaco)

    @Slot()
    def _on_restarted(self) -> None:
        if self._streaming_tab is not None:
            self._streaming_tab.reset()

    def _close_streaming_tab(self) -> int | None:
        """Tira a aba temporária e devolve a posição em que ela estava."""
        if self._streaming_tab is None:
            return None
        indice = self.tabs.indexOf(self._streaming_tab)
        if indice != -1:
            self.tabs.removeTab(indice)
        self._streaming_tab.deleteLater()
        self._streaming_tab = None
        return indice if indice != -1 else None

    def _set_stream_enabled(self, ligado: bool) -> None:
        self.stream_enabled = ligado

    @Slot(object)
    def _on_finished(self, record: SearchRecord) -> None:
        self._stop_running()
        self._close_streaming_tab()
        if self.open_record(record) is None:
            return
        self.history.refresh()
        self.statusBar().showMessage(f"Salvo em {record.md_path.name}")

    @Slot(str)
    def _on_failed(self, mensagem: str) -> None:
        self._stop_running()
        self._close_streaming_tab()
        self.statusBar().showMessage("A busca falhou.")
        self.show_error("A busca falhou", mensagem)

    @Slot(str)
    def _on_auth_failed(self, mensagem: str) -> None:
        """401: além da mensagem, oferecemos trocar a chave na hora (RF7)."""
        self._stop_running()
        self._close_streaming_tab()
        self.statusBar().showMessage("Chave recusada.")
        if self.ask_change_key(mensagem):
            self.open_api_key_dialog()

    @Slot()
    def _on_cancelled(self) -> None:
        self._stop_running()
        self._close_streaming_tab()
        self.statusBar().showMessage("Busca cancelada.")

    # ------------------------------------------------------------------ apoio

    def _stop_running(self) -> None:
        self._ticker.stop()
        self.search_panel.set_running(False)

    def _tick(self) -> None:
        segundos = self._elapsed.elapsed() // 1000
        self.statusBar().showMessage(f"{self._status_base} — {segundos}s")

    def _close_tab(self, indice: int) -> None:
        if indice == 0:  # a aba de busca não fecha
            return
        widget = self.tabs.widget(indice)
        self.tabs.removeTab(indice)
        if widget is not None:
            widget.deleteLater()

    def _open_output_dir(self) -> None:
        self.storage.output_dir.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.storage.output_dir)))

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 — nome do Qt
        """Ao fechar, pede o cancelamento e guarda a configuração (RF4)."""
        self.client.cancel()
        if self.settings is not None:
            self.settings.save(
                self.options,
                self.options_widget.selected_packs(),
                ui={"stream": self.stream_enabled},
            )
        super().closeEvent(event)
