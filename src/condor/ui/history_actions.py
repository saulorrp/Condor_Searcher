"""O que a janela faz quando o histórico pede alguma coisa (TECHSPEC RF5).

Mixin, e não funções soltas, porque todas estas ações mexem na mesma janela: abas, barra de
status e painel de busca. Quem herda precisa ter `tabs`, `storage`, `history`, `search_panel`,
`options_widget`, `ask_delete()` e `_on_failed()`.
"""

from __future__ import annotations

from PySide6.QtCore import QUrl, Slot
from PySide6.QtGui import QDesktopServices

from condor.core.models import SearchRecord
from condor.ui.result_tab import ResultTab, load_result_tab, tab_title


class HistoryActionsMixin:
    """Abrir, repetir, abrir o arquivo e excluir — as quatro ações do menu do RF5."""

    @Slot(object)
    def open_record(self, record: SearchRecord) -> ResultTab | None:
        """Abre a aba de uma busca lendo o `.md` salvo, ou reativa a que já estiver aberta."""
        existente = self._tab_for(record)
        if existente is not None:
            self.tabs.setCurrentWidget(existente)
            return existente

        try:
            aba = load_result_tab(record, parent=self)
        except OSError as exc:
            self._on_failed(f"Não consegui abrir o relatório {record.md_path.name}: {exc}")
            return None

        indice = self.tabs.addTab(aba, tab_title(record.prompt))
        self.tabs.setTabToolTip(indice, record.prompt)
        self.tabs.setCurrentIndex(indice)
        return aba

    @Slot(object)
    def repeat_record(self, record: SearchRecord) -> None:
        """ "Repetir busca com as mesmas opções" (RF5): preenche a tela e **para**.

        Não dispara a busca sozinho: repetir por engano custa dinheiro.
        """
        self.search_panel.set_prompt(record.prompt)
        self.options_widget.set_options_inferring_packs(record.options)
        self.tabs.setCurrentIndex(0)
        self.statusBar().showMessage("Pergunta e opções carregadas. Revise e clique em Buscar.")

    @Slot(object)
    def open_record_file(self, record: SearchRecord) -> None:
        """Abre o `.md` no programa padrão do sistema."""
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(record.md_path)))

    @Slot(object)
    def delete_record(self, record: SearchRecord) -> None:
        """Tira do histórico. O `.md` e o `.json` ficam no disco (RF5)."""
        if not self.ask_delete(record):
            return
        self.storage.delete(record.id)
        self.history.refresh()
        self.statusBar().showMessage("Removido do histórico. O arquivo .md continua na pasta.")

    def _tab_for(self, record: SearchRecord) -> ResultTab | None:
        """Evita duas abas do mesmo relatório quando se clica duas vezes no histórico."""
        for indice in range(1, self.tabs.count()):
            aba = self.tabs.widget(indice)
            if isinstance(aba, ResultTab) and aba.record.md_path == record.md_path:
                return aba
        return None
