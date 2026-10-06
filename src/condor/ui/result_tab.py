"""Aba de resultado: Markdown renderizado + rodapé + botões (TECHSPEC RF2)."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from condor.core.models import SearchRecord, Usage
from condor.core.response_parser import parse

logger = logging.getLogger(__name__)

#: Tamanho do título da aba (RF2).
TAB_TITLE_LENGTH = 40


def tab_title(prompt: str) -> str:
    """Primeiros 40 caracteres do prompt, numa linha só (RF2)."""
    texto = " ".join(prompt.split())
    return texto[:TAB_TITLE_LENGTH] + "…" if len(texto) > TAB_TITLE_LENGTH else texto or "Busca"


def strip_front_matter(md: str) -> str:
    """Tira o front matter YAML para a tela.

    O arquivo em disco mantém tudo (é o que dá reprodutibilidade); mas o `QTextBrowser` mostraria
    o bloco como texto solto no topo, o que só confunde quem lê.
    """
    if not md.startswith("---\n"):
        return md
    fim = md.find("\n---", 4)
    return md[fim + 4 :].lstrip("\n") if fim != -1 else md


def footer_text(usage: Usage) -> str:
    """Rodapé do RF2: custo, tokens e nº de buscas."""
    custo = f"US$ {usage.cost_usd:.5f}" if usage.cost_usd is not None else "custo não informado"
    return (
        f"{custo} · {usage.input_tokens:,} tokens de entrada · "
        f"{usage.output_tokens:,} de saída · {usage.search_calls} busca(s)"
    ).replace(",", ".")


class ResultTab(QWidget):
    """Uma busca concluída."""

    def __init__(
        self,
        record: SearchRecord,
        markdown: str,
        usage: Usage,
        json_path: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.record = record
        self.markdown = markdown
        self.json_path = json_path or record.md_path.with_suffix(".json")

        self.viewer = QTextBrowser(self)
        self.viewer.setOpenExternalLinks(True)  # links abrem no navegador do sistema (RF2)
        self.viewer.setMarkdown(strip_front_matter(markdown))

        self.footer = QLabel(footer_text(usage), self)
        self.footer.setEnabled(False)

        botoes = QHBoxLayout()
        botoes.addWidget(self._button("Abrir pasta", self.open_folder))
        botoes.addWidget(self._button("Copiar Markdown", self.copy_markdown))
        botoes.addWidget(self._button("Ver JSON bruto", self.show_raw_json))
        botoes.addStretch(1)
        botoes.addWidget(self.footer)

        layout = QVBoxLayout(self)
        layout.addWidget(self.viewer, stretch=1)
        layout.addLayout(botoes)

    def _button(self, texto: str, slot) -> QPushButton:
        botao = QPushButton(texto, self)
        botao.clicked.connect(slot)
        return botao

    # ------------------------------------------------------------------ ações

    def open_folder(self) -> None:
        """Abre a pasta do relatório, selecionando o arquivo quando o sistema permite."""
        caminho = self.record.md_path
        try:
            if sys.platform == "win32":
                subprocess.Popen(["explorer", f"/select,{caminho}"])  # noqa: S603, S607
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", str(caminho)])  # noqa: S603, S607
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(caminho.parent)))
        except OSError as exc:
            logger.warning("Não consegui abrir a pasta %s (%s).", caminho.parent, exc)

    def copy_markdown(self) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self.markdown)

    def show_raw_json(self) -> None:
        RawJsonDialog(self.json_path, self).exec()


class RawJsonDialog(QDialog):
    """Mostra o `.json` salvo ao lado do relatório (RF2)."""

    def __init__(self, json_path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"JSON bruto — {json_path.name}")
        self.resize(820, 620)

        visor = QPlainTextEdit(self)
        visor.setReadOnly(True)
        visor.setPlainText(_read_json(json_path))

        layout = QVBoxLayout(self)
        layout.addWidget(visor)

        fechar = QPushButton("Fechar", self)
        fechar.clicked.connect(self.accept)
        layout.addWidget(fechar)


def _read_json(path: Path) -> str:
    try:
        bruto = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return f"Não consegui ler {path.name}: {exc}"
    return json.dumps(bruto, ensure_ascii=False, indent=2)


def load_result_tab(record: SearchRecord, parent: QWidget | None = None) -> ResultTab:
    """Monta a aba de um registro lendo os arquivos salvos.

    Levanta `OSError` se o `.md` sumiu (o relatório é o produto; sem ele não há aba). Já o `.json`
    é só para o rodapé: se faltar, mostramos o que o histórico souber em vez de recusar a abrir.
    """
    markdown = record.md_path.read_text(encoding="utf-8")
    return ResultTab(record, markdown, _usage_of(record), parent=parent)


def _usage_of(record: SearchRecord) -> Usage:
    try:
        bruto = json.loads(record.md_path.with_suffix(".json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return Usage(input_tokens=0, output_tokens=0, search_calls=0, cost_usd=record.cost_usd)
    return parse(bruto).usage


class StreamingTab(QWidget):
    """Aba temporária que mostra o texto enquanto ele chega (F10: streaming).

    Mostra **texto puro**, de propósito: renderizar Markdown a cada pedaço recebido custa caro e
    faz a tela piscar, e o texto parcial muitas vezes está no meio de uma marcação. Quando a busca
    termina, esta aba é trocada pela `ResultTab` com o Markdown de verdade, citações viradas em
    links e a lista de fontes.
    """

    def __init__(self, prompt: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.prompt = prompt
        self._texto: list[str] = []

        self.viewer = QPlainTextEdit(self)
        self.viewer.setReadOnly(True)
        self.viewer.setPlaceholderText("A resposta aparece aqui conforme chega…")

        self.footer = QLabel("Recebendo a resposta…", self)
        self.footer.setEnabled(False)

        layout = QVBoxLayout(self)
        layout.addWidget(self.viewer, stretch=1)
        layout.addWidget(self.footer)

    def append(self, pedaco: str) -> None:
        """Acrescenta um pedaço e mantém a rolagem no fim, como um terminal."""
        self._texto.append(pedaco)
        self.viewer.setPlainText("".join(self._texto))
        barra = self.viewer.verticalScrollBar()
        barra.setValue(barra.maximum())

    def reset(self) -> None:
        """Uma tentativa falhou: o que veio até agora não vale mais."""
        self._texto.clear()
        self.viewer.clear()
        self.footer.setText("A conexão falhou no meio; recomeçando…")

    def text(self) -> str:
        return "".join(self._texto)
