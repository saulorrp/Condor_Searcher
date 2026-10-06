"""Painel lateral com as buscas anteriores (TECHSPEC RF5).

O painel não decide nada: lê o histórico do `storage` e emite sinais. Quem reabre aba, repete
busca, abre arquivo ou confirma exclusão é a janela principal — inclusive porque excluir precisa
de confirmação, e caixa de diálogo é assunto dela.

"Excluir do histórico" tira a linha do banco e **não** apaga o `.md` (RF5). O painel repete isso
no texto do menu para o usuário não precisar lembrar.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDockWidget,
    QHeaderView,
    QMenu,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from condor.core.models import SearchRecord
from condor.services.storage import Storage

logger = logging.getLogger(__name__)

COLUNAS = ("Data", "Pergunta", "Profundidade", "Custo")

#: Quantas buscas o painel mostra. Passou disso, o usuário usa a pasta de resultados.
LIMITE = 200


class HistoryPanel(QDockWidget):
    """Lista das buscas salvas, com duplo clique e menu de contexto."""

    reopen_requested = Signal(object)  # SearchRecord
    repeat_requested = Signal(object)
    open_file_requested = Signal(object)
    delete_requested = Signal(object)

    def __init__(self, storage: Storage, parent: QWidget | None = None) -> None:
        super().__init__("Histórico", parent)
        self.storage = storage
        self.setObjectName("historico")
        self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)

        self.table = QTableWidget(0, len(COLUNAS), self)
        self.table.setHorizontalHeaderLabels(COLUNAS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_menu)
        self.table.itemDoubleClicked.connect(self._on_double_click)

        cabecalho = self.table.horizontalHeader()
        cabecalho.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        self.setWidget(self.table)
        self.refresh()

    # ------------------------------------------------------------------ dados

    def refresh(self, limit: int = LIMITE) -> None:
        """Relê o histórico do disco. Chamado ao abrir o app e depois de cada busca."""
        registros = self.storage.list_recent(limit)
        self.table.setRowCount(len(registros))
        for linha, record in enumerate(registros):
            self._fill_row(linha, record)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

    def _fill_row(self, linha: int, record: SearchRecord) -> None:
        valores = (
            record.created_at.strftime("%d/%m/%Y %H:%M"),
            " ".join(record.prompt.split()),
            record.options.preset,
            f"US$ {record.cost_usd:.5f}" if record.cost_usd is not None else "—",
        )
        for coluna, texto in enumerate(valores):
            item = QTableWidgetItem(texto)
            item.setToolTip(record.prompt if coluna == 1 else str(record.md_path))
            if coluna == 0:
                item.setData(Qt.ItemDataRole.UserRole, record)
            self.table.setItem(linha, coluna, item)

    def record_at(self, linha: int) -> SearchRecord | None:
        item = self.table.item(linha, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def current_record(self) -> SearchRecord | None:
        linha = self.table.currentRow()
        return self.record_at(linha) if linha >= 0 else None

    def count(self) -> int:
        return self.table.rowCount()

    # ------------------------------------------------------------------ interação

    def _on_double_click(self, item: QTableWidgetItem) -> None:
        record = self.record_at(item.row())
        if record is not None:
            self.reopen_requested.emit(record)

    def _show_menu(self, posicao: QPoint) -> None:
        linha = self.table.rowAt(posicao.y())
        if linha < 0:
            return
        record = self.record_at(linha)
        if record is None:
            return
        self.table.selectRow(linha)
        self.build_menu(record).exec(self.table.viewport().mapToGlobal(posicao))

    def build_menu(self, record: SearchRecord) -> QMenu:
        """Monta o menu de contexto do RF5. Separado para o teste poder inspecioná-lo."""
        menu = QMenu(self)
        menu.addAction("Abrir", lambda: self.reopen_requested.emit(record))
        menu.addAction("Repetir busca com as mesmas opções", lambda: self.repeat_requested.emit(record))
        menu.addAction("Abrir arquivo .md", lambda: self.open_file_requested.emit(record))
        menu.addSeparator()
        menu.addAction("Excluir do histórico (não apaga o .md)", lambda: self.delete_requested.emit(record))
        return menu
