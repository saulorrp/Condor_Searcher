"""Os controles do painel de opções: rótulos, layout e nada de regra (TECHSPEC RF4).

Separado de `options_widget.py` de propósito: aqui mora **o que aparece na tela**; lá, o que as
escolhas significam. Esta metade não sabe o que é um `SearchOptions`.

Os rótulos de idioma, formato, prioridade e pacote vêm dos TOML de `config/`, então acrescentar
um formato novo não exige tocar em código.
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from condor.core.config import Snippets, SourcePack
from condor.core.models import MAX_RESULTS, MIN_RESULTS, SearchOptions

#: Profundidade (RF4). `xhigh` só entra na lista no modo avançado.
PRESET_LABELS = (
    ("fast", "Rápida — fato único"),
    ("low", "Padrão — pesquisa do dia a dia"),
    ("medium", "Aprofundada — muitas fontes"),
    ("high", "Exaustiva — mais cara e lenta"),
)
PRESET_ADVANCED = ("xhigh", "Agente — tarefas abertas (muito cara)")

CONTEXT_LABELS = (("low", "Baixa"), ("medium", "Média"), ("high", "Alta"))

PERIOD_LABELS = (
    ("", "Qualquer período"),
    ("hour", "Última hora"),
    ("day", "Último dia"),
    ("week", "Última semana"),
    ("month", "Último mês"),
    ("year", "Último ano"),
    ("range", "Intervalo de datas…"),
)

MODE_LABELS = (("allow", "Somente estes domínios"), ("deny", "Excluir estes domínios"))


class OptionsForm(QTabWidget):
    """Todos os controles do RF4, em quatro abas. Expõe cada um como atributo."""

    def __init__(self, snippets: Snippets, packs: tuple[SourcePack, ...], parent: QWidget | None = None):
        super().__init__(parent)
        self.snippets = snippets
        self.packs = packs
        self.addTab(self._tab_busca(), "Busca")
        self.addTab(self._tab_fontes(), "Fontes")
        self.addTab(self._tab_resposta(), "Resposta")
        self.addTab(self._tab_avancado(), "Avançado")

    # ------------------------------------------------------------------ abas

    def _tab_busca(self) -> QWidget:
        self.preset_combo = combo(PRESET_LABELS)
        self.context_combo = combo(CONTEXT_LABELS)
        self.max_results_spin = QSpinBox()
        self.max_results_spin.setRange(MIN_RESULTS, MAX_RESULTS)

        self.period_combo = combo(PERIOD_LABELS)
        self.after_edit = date_edit()
        self.before_edit = date_edit()
        self.range_box = _row(("de", self.after_edit), ("até", self.before_edit))
        self.range_box.setVisible(False)

        self.location_check = QCheckBox("Informar a minha localização à busca")
        self.country_edit = line("PT", largura=60)
        self.region_edit = line("Lisboa")
        self.city_edit = line("Lisboa")
        self.location_box = _row(
            ("País", self.country_edit), ("Região", self.region_edit), ("Cidade", self.city_edit)
        )
        self.location_box.setVisible(False)

        form = QFormLayout()
        form.addRow("Profundidade", self.preset_combo)
        form.addRow("Profundidade de leitura", self.context_combo)
        form.addRow("Máx. resultados", self.max_results_spin)
        form.addRow("Período", self.period_combo)
        form.addRow("", self.range_box)
        form.addRow(self.location_check)
        form.addRow("", self.location_box)
        return wrap(form)

    def _tab_fontes(self) -> QWidget:
        self.mode_combo = combo(MODE_LABELS)

        self.packs_list = QListWidget()
        self.packs_list.setAlternatingRowColors(True)
        for pack in self.packs:
            item = QListWidgetItem(f"{pack.label} ({len(pack.domains)})")
            item.setData(Qt.ItemDataRole.UserRole, pack.key)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            dica = pack.description
            if pack.mode == "deny":
                dica = f"{dica}\n(pacote pensado para o modo “Excluir estes domínios”)"
            item.setToolTip(dica)
            self.packs_list.addItem(item)

        self.extra_domains = QPlainTextEdit()
        self.extra_domains.setPlaceholderText("Um domínio por linha. Ex.: dglab.gov.pt")
        self.extra_domains.setMaximumHeight(110)

        self.domain_counter = QLabel()

        form = QFormLayout()
        form.addRow("Modo do filtro", self.mode_combo)
        form.addRow("Pacotes de fontes", self.packs_list)
        form.addRow("Domínios extras", self.extra_domains)
        form.addRow("", self.domain_counter)
        return wrap(form)

    def _tab_resposta(self) -> QWidget:
        self.language_combo = combo(tuple((s.key, s.label) for s in self.snippets.languages))
        self.format_combo = combo(tuple((s.key, s.label) for s in self.snippets.formats))

        self.priority_checks: dict[str, QCheckBox] = {}
        caixa = QGroupBox("Prioridades")
        prioridades = QVBoxLayout(caixa)
        for snippet in self.snippets.priorities:
            check = QCheckBox(snippet.label)
            check.setToolTip(snippet.text)
            self.priority_checks[snippet.key] = check
            prioridades.addWidget(check)

        form = QFormLayout()
        form.addRow("Idioma da resposta", self.language_combo)
        form.addRow("Formato", self.format_combo)
        form.addRow(caixa)
        return wrap(form)

    def _tab_avancado(self) -> QWidget:
        self.advanced_check = QCheckBox("Liberar as opções avançadas")
        self.advanced_check.setToolTip(
            "Mostra o preset Agente (xhigh) e permite substituir as instruções de sistema do preset."
        )

        self.instructions_edit = QPlainTextEdit()
        self.instructions_edit.setPlaceholderText(
            "Instruções de sistema próprias. Substituem as do preset da Perplexity — o app reanexa "
            "automaticamente as regras de citação."
        )
        self.instructions_edit.setEnabled(False)
        self.instructions_edit.setMaximumHeight(140)

        form = QFormLayout()
        form.addRow(self.advanced_check)
        form.addRow("Instruções próprias", self.instructions_edit)
        return wrap(form)

    # ------------------------------------------------------------------ visibilidade

    def sync_visibility(self) -> None:
        """Campos que só fazem sentido com certa escolha aparecem só nela."""
        self.range_box.setVisible(data(self.period_combo) == "range")
        self.location_box.setVisible(self.location_check.isChecked())

    def sync_advanced(self, ligado: bool) -> None:
        """O preset Agente e as instruções próprias ficam atrás do "Avançado" (RF4)."""
        self.instructions_edit.setEnabled(ligado)
        indice = self.preset_combo.findData(PRESET_ADVANCED[0])
        if ligado and indice == -1:
            self.preset_combo.addItem(PRESET_ADVANCED[1], PRESET_ADVANCED[0])
        elif not ligado and indice != -1:
            if self.preset_combo.currentIndex() == indice:
                self.preset_combo.setCurrentIndex(self.preset_combo.findData("low"))
            self.preset_combo.removeItem(indice)


class PromptPreviewDialog(QDialog):
    """Mostra o que será enviado. Nunca inclui a chave: o payload não a contém (F2)."""

    def __init__(self, texto: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Prompt final")
        self.resize(760, 620)

        self.viewer = QPlainTextEdit(self)
        self.viewer.setReadOnly(True)
        self.viewer.setPlainText(texto)

        fechar = QPushButton("Fechar", self)
        fechar.clicked.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("É isto que vai para a API (sem a chave):", self))
        layout.addWidget(self.viewer)
        layout.addWidget(fechar)


# --------------------------------------------------------------------------- fábricas


def combo(pares: tuple[tuple[str, str], ...]) -> QComboBox:
    """Combo cujo texto é o rótulo e cujo `data` é o valor que o `core` entende."""
    widget = QComboBox()
    for valor, rotulo in pares:
        widget.addItem(rotulo, valor)
    return widget


def line(placeholder: str, largura: int = 0) -> QLineEdit:
    edit = QLineEdit()
    edit.setPlaceholderText(placeholder)
    if largura:
        edit.setMaximumWidth(largura)
    return edit


def date_edit() -> QDateEdit:
    edit = QDateEdit()
    edit.setCalendarPopup(True)
    edit.setDisplayFormat("dd/MM/yyyy")
    edit.setDate(QDate.currentDate())
    return edit


def wrap(form: QFormLayout) -> QWidget:
    widget = QWidget()
    widget.setLayout(form)
    return widget


def data(widget: QComboBox) -> str:
    valor = widget.currentData()
    return str(valor) if valor is not None else ""


def select(widget: QComboBox, valor: str) -> None:
    indice = widget.findData(valor)
    if indice != -1:
        widget.setCurrentIndex(indice)


def qdate(edit: QDateEdit) -> date:
    valor = edit.date()
    return date(valor.year(), valor.month(), valor.day())


def to_qdate(valor: date) -> QDate:
    return QDate(valor.year, valor.month, valor.day)


def _row(*pares: tuple[str, QWidget]) -> QWidget:
    """Linha horizontal de "rótulo + campo", usada nos campos que aparecem e somem."""
    caixa = QWidget()
    layout = QHBoxLayout(caixa)
    layout.setContentsMargins(0, 0, 0, 0)
    for rotulo, campo in pares:
        layout.addWidget(QLabel(rotulo))
        layout.addWidget(campo)
    return caixa


def summary_text(options: SearchOptions) -> str:
    """Resumo de uma linha, para o painel fechado não esconder o que está valendo."""
    rotulos = dict((*PRESET_LABELS, PRESET_ADVANCED))
    partes = [rotulos.get(options.preset, options.preset).split(" —")[0]]
    if options.domains:
        verbo = "excluindo" if options.domain_mode == "deny" else "restrito a"
        partes.append(f"{verbo} {len(options.domains)} domínio(s)")
    if options.recency:
        partes.append(dict(PERIOD_LABELS)[options.recency].lower())
    elif options.after or options.before:
        partes.append("intervalo de datas")
    if options.location is not None:
        partes.append(f"local {options.location.country}")
    if options.custom_instructions:
        partes.append("instruções próprias")
    return " · ".join(partes)
