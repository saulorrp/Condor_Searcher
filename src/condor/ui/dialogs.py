"""As caixas de diálogo da janela principal, num lugar só.

Por que existir em vez de chamar `QMessageBox` espalhado pelo código: método estático do PySide
não é remendável de forma confiável nos testes, e uma caixa modal que escapa **trava a suíte
inteira**. Com os diálogos concentrados em métodos, o teste substitui o método e segue.

Quem usa isto herda `DialogMixin` junto de `QMainWindow`.
"""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from condor.core.models import SearchRecord


class DialogMixin:
    """Caixas de diálogo da janela. Cada uma é um método para o teste poder trocá-la."""

    def show_error(self, titulo: str, mensagem: str) -> None:
        """Mostra um erro já em português (a mensagem vem pronta do `services/errors.py`)."""
        QMessageBox.warning(self, titulo, mensagem)

    def ask_change_key(self, mensagem: str) -> bool:
        """Chave recusada: devolve `True` se o usuário quer trocá-la agora (RF7)."""
        caixa = QMessageBox(QMessageBox.Icon.Warning, "Chave recusada", mensagem, parent=self)
        trocar = caixa.addButton("Trocar chave…", QMessageBox.ButtonRole.AcceptRole)
        caixa.addButton("Fechar", QMessageBox.ButtonRole.RejectRole)
        caixa.exec()
        return caixa.clickedButton() is trocar

    def ask_delete(self, record: SearchRecord) -> bool:
        """Confirma tirar a busca do histórico, lembrando que o arquivo fica (RF5)."""
        pergunta = " ".join(record.prompt.split())[:60]
        resposta = QMessageBox.question(
            self,
            "Excluir do histórico",
            f"Tirar esta busca do histórico?\n\n{pergunta}\n\n"
            f"O arquivo {record.md_path.name} continua na pasta de resultados.",
        )
        return resposta == QMessageBox.StandardButton.Yes

    def show_config_error(self, mensagem: str) -> None:
        QMessageBox.critical(self, "Configuração inválida", mensagem)
