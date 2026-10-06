"""Diálogo da chave da API (TECHSPEC RF7).

A chave nunca aparece inteira na tela depois de salva: o rótulo mostra só `pplx-…AB12`, e o campo
de digitação começa mascarado. Quem fala com o `.env` é sempre o `services/secrets.py`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from condor.services.secrets import KEY_PREFIX, MIN_KEY_LENGTH, SecretStore, is_valid_format, mask
from condor.services.secrets import SOURCE_SYSTEM as _SOURCE_SYSTEM

logger = logging.getLogger(__name__)

AVISO_SISTEMA = (
    "Atenção: existe uma variável de ambiente PERPLEXITY_API_KEY definida no sistema, "
    "e ela tem prioridade. Enquanto existir, a chave gravada aqui não terá efeito."
)

AVISO_TESTE = (
    "O teste faz uma busca mínima de verdade (preset rápido) e custa uma fração de centavo.\n\n"
    "Quer continuar?"
)


class ApiKeyDialog(QDialog):
    """Ver, trocar e remover a chave.

    `on_test` é opcional: recebe a chave e devolve `(ok, mensagem)`. A janela principal injeta
    uma função que faz a busca mínima do RF7 — assim o diálogo não conhece o cliente da API.
    """

    def __init__(
        self,
        secrets: SecretStore,
        parent: QWidget | None = None,
        on_test: Callable[[str], tuple[bool, str]] | None = None,
    ) -> None:
        super().__init__(parent)
        self.secrets = secrets
        self._on_test = on_test
        self.saved = False

        self.setWindowTitle("Chave da API")
        self.setMinimumWidth(520)

        self.current_label = QLabel(self)
        self.current_label.setWordWrap(True)

        self.key_edit = QLineEdit(self)
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText(f"{KEY_PREFIX}…")
        self.key_edit.textChanged.connect(self._refresh_buttons)

        self.show_check = QCheckBox("Mostrar a chave enquanto digito", self)
        self.show_check.toggled.connect(self._toggle_echo)

        self.message = QLabel(self)
        self.message.setWordWrap(True)

        self.buttons = QDialogButtonBox(self)
        self.save_button = self.buttons.addButton("Salvar", QDialogButtonBox.ButtonRole.AcceptRole)
        self.test_button = self.buttons.addButton("Testar chave", QDialogButtonBox.ButtonRole.ActionRole)
        self.remove_button = self.buttons.addButton(
            "Remover chave", QDialogButtonBox.ButtonRole.DestructiveRole
        )
        self.buttons.addButton("Fechar", QDialogButtonBox.ButtonRole.RejectRole)

        self.save_button.clicked.connect(self._save)
        self.test_button.clicked.connect(self._test)
        self.remove_button.clicked.connect(self._remove)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.current_label)
        layout.addWidget(QLabel("Chave nova", self))
        layout.addWidget(self.key_edit)
        layout.addWidget(self.show_check)
        layout.addWidget(self.message)
        layout.addWidget(self.buttons)

        self._refresh_current()
        self._refresh_buttons()

    # ------------------------------------------------------------------ estado da tela

    def _refresh_current(self) -> None:
        chave = self.secrets.get_key()
        origem = self.secrets.key_source()
        if chave is None:
            self.current_label.setText("Chave atual: nenhuma chave configurada.")
        else:
            self.current_label.setText(f"Chave atual: {mask(chave)} (origem: {origem}).")
        if self.secrets.system_overrides_file:
            self._warn(AVISO_SISTEMA)
        elif origem == _SOURCE_SYSTEM:
            self._info(
                "A chave vem de uma variável de ambiente do sistema. Salvar aqui grava no .env, "
                "que só passa a valer se a variável for removida."
            )

    def _refresh_buttons(self) -> None:
        digitada = self.key_edit.text().strip()
        valida = is_valid_format(digitada)
        self.save_button.setEnabled(valida)
        self.test_button.setEnabled(bool(self._on_test) and (valida or self.secrets.get_key() is not None))
        self.remove_button.setEnabled(self.secrets.key_source() is not None)

        if digitada and not valida:
            self._warn(
                f"A chave precisa começar com {KEY_PREFIX}, ter ao menos {MIN_KEY_LENGTH} "
                "caracteres e não conter espaços."
            )
        elif digitada:
            self.message.clear()

    def _toggle_echo(self, mostrar: bool) -> None:
        modo = QLineEdit.EchoMode.Normal if mostrar else QLineEdit.EchoMode.Password
        self.key_edit.setEchoMode(modo)

    def _warn(self, texto: str) -> None:
        self.message.setText(f"⚠ {texto}")

    def _info(self, texto: str) -> None:
        self.message.setText(texto)

    # ------------------------------------------------------------------ ações

    def _save(self) -> None:
        try:
            self.secrets.save_key(self.key_edit.text())
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Chave não salva", str(exc))
            return
        self.saved = True
        self.key_edit.clear()
        self._refresh_current()
        self._refresh_buttons()
        if not self.secrets.system_overrides_file:
            self._info("Chave salva. Já vale para a próxima busca, sem reiniciar.")
        self.accept()

    def _remove(self) -> None:
        confirmacao = QMessageBox.question(
            self,
            "Remover a chave",
            "Apagar a chave do arquivo .env? Você vai precisar digitá-la de novo para buscar.",
        )
        if confirmacao != QMessageBox.StandardButton.Yes:
            return
        if self.secrets.remove_key():
            self.saved = True
            self._info("Chave removida do .env.")
        else:
            self._warn("Não havia chave no .env para remover.")
        self._refresh_current()
        self._refresh_buttons()

    def _test(self) -> None:
        if self._on_test is None:
            return
        chave = self.key_edit.text().strip() or self.secrets.get_key() or ""
        if QMessageBox.question(self, "Testar a chave", AVISO_TESTE) != QMessageBox.StandardButton.Yes:
            return
        ok, mensagem = self._on_test(chave)
        if ok:
            self._info(f"✔ {mensagem}")
        else:
            self._warn(mensagem)
