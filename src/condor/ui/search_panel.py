"""Painel da busca: a caixa de texto e o botão (TECHSPEC RF1).

O painel não sabe buscar: emite `search_requested` / `cancel_requested` e espera que a janela
lhe diga quando a busca começou e terminou (`set_running`).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

PLACEHOLDER = (
    "Escreva a sua pergunta.\n\n"
    "Exemplo: Como funciona o acesso à sala de leitura do Arquivo Histórico Ultramarino?\n\n"
    "Ctrl+Enter busca."
)


class PromptEdit(QPlainTextEdit):
    """Caixa de texto que entende Ctrl+Enter.

    A tecla é tratada aqui, e não num `QShortcut` da janela: atalho de janela só dispara quando
    a janela está ativa, o que deixa o comportamento dependente do gerenciador de janelas (e
    intestável fora de uma sessão gráfica).
    """

    submitted = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 — nome do Qt
        teclas = (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        modificadores = event.modifiers()
        if event.key() in teclas and modificadores & Qt.KeyboardModifier.ControlModifier:
            self.submitted.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class SearchPanel(QWidget):
    """Caixa de texto multilinha + botão que alterna entre Buscar e Cancelar."""

    search_requested = Signal(str)
    cancel_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._running = False
        self._search_enabled = True

        self.prompt_edit = PromptEdit(self)
        self.prompt_edit.setPlaceholderText(PLACEHOLDER)
        self.prompt_edit.setTabChangesFocus(True)
        self.prompt_edit.submitted.connect(self._on_shortcut)

        self.action_button = QPushButton("Buscar", self)
        self.action_button.setDefault(True)
        self.action_button.clicked.connect(self._on_clicked)

        self.hint = QLabel("Ctrl+Enter para buscar", self)
        self.hint.setEnabled(False)

        self._layout = QVBoxLayout(self)
        self._layout.addWidget(QLabel("Pergunta", self))
        self._layout.addWidget(self.prompt_edit, stretch=1)
        self._layout.addWidget(self.hint)
        self._layout.addWidget(self.action_button, alignment=Qt.AlignmentFlag.AlignRight)

    def set_options_widget(self, widget: QWidget) -> None:
        """Encaixa o painel de opções entre a pergunta e o botão (RF4)."""
        self.options_widget = widget
        self._layout.insertWidget(2, widget)

    def set_search_enabled(self, habilitado: bool, dica: str = "") -> None:
        """Opções inválidas desabilitam o Buscar e explicam por quê (aceite da F8)."""
        self._search_enabled = habilitado
        if not self._running:
            self.action_button.setEnabled(habilitado)
        self.action_button.setToolTip(dica)
        self.hint.setText(dica or "Ctrl+Enter para buscar")

    # ------------------------------------------------------------------ estado

    @property
    def running(self) -> bool:
        return self._running

    def set_running(self, running: bool) -> None:
        """Busca em andamento: o botão vira Cancelar e a caixa fica somente leitura (RF1)."""
        self._running = running
        self.action_button.setText("Cancelar" if running else "Buscar")
        self.action_button.setEnabled(True if running else self._search_enabled)
        self.prompt_edit.setReadOnly(running)

    def prompt(self) -> str:
        return self.prompt_edit.toPlainText().strip()

    def set_prompt(self, texto: str) -> None:
        """Usado pelo "Repetir busca" do histórico (F9)."""
        self.prompt_edit.setPlainText(texto)
        self.prompt_edit.setFocus()

    # ------------------------------------------------------------------ eventos

    def _on_clicked(self) -> None:
        if self._running:
            self.cancel_requested.emit()
        else:
            self._start()

    def _on_shortcut(self) -> None:
        if not self._running:
            self._start()

    def _start(self) -> None:
        if not self._search_enabled:
            return
        texto = self.prompt()
        if texto:
            self.search_requested.emit(texto)
        else:
            self.prompt_edit.setFocus()
