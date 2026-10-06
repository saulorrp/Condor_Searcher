"""O que as escolhas do painel significam (TECHSPEC RF4). Os controles estão em `options_form.py`.

Três decisões sustentam este arquivo:
- quem decide se uma combinação fecha é o `core/prompt_builder`, chamado com um prompt de mentira
  (reimplementar as regras aqui seria garantir que um dia elas divergem do que é enviado);
- `options()` lê os controles na hora, sem `SearchOptions` guardado para ficar desatualizado;
- "Ver prompt final" mostra o payload que o `prompt_builder` produziu, não uma reconstrução.
"""

from __future__ import annotations

import json
from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from condor.core.config import Defaults, Snippets, SourcePack
from condor.core.models import MAX_DOMAINS, LocationOpt, SearchOptions
from condor.core.prompt_builder import build
from condor.ui.options_form import (
    OptionsForm,
    PromptPreviewDialog,
    data,
    qdate,
    select,
    summary_text,
    to_qdate,
)

#: Prompt de mentira para validar as opções sem exigir que o usuário já tenha digitado algo.
PROMPT_DE_PROVA = "pergunta de exemplo"


class OptionsWidget(QWidget):
    """Painel recolhível com as opções do RF4."""

    changed = Signal()
    validity_changed = Signal(bool, str)  # (pode buscar, dica)

    def __init__(
        self,
        defaults: Defaults,
        snippets: Snippets,
        packs: tuple[SourcePack, ...],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.defaults = defaults
        self.snippets = snippets
        self.packs = packs
        self.form = OptionsForm(snippets, packs, self)

        self._build_ui()
        self.set_options(defaults.options, source_packs=defaults.source_packs)
        self._connect_signals()
        self._revalidate()

    def _build_ui(self) -> None:
        self.toggle = QToolButton(self)
        self.toggle.setText("Opções")
        self.toggle.setCheckable(True)
        self.toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.toggled.connect(self._on_toggled)

        self.summary = QLabel(self)
        self.summary.setEnabled(False)

        self.body = QScrollArea(self)
        self.body.setWidgetResizable(True)
        self.body.setWidget(self.form)
        self.body.setVisible(False)
        self.body.setMinimumHeight(320)

        self.preview_button = QPushButton("Ver prompt final", self)
        self.preview_button.clicked.connect(lambda: self.show_preview())
        self.restore_button = QPushButton("Restaurar padrões", self)
        self.restore_button.clicked.connect(self.restore_defaults)

        cabecalho = QHBoxLayout()
        cabecalho.addWidget(self.toggle)
        cabecalho.addWidget(self.summary, stretch=1)
        cabecalho.addWidget(self.preview_button)
        cabecalho.addWidget(self.restore_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(cabecalho)
        layout.addWidget(self.body)

    def _connect_signals(self) -> None:
        f = self.form
        for widget in (
            f.preset_combo,
            f.context_combo,
            f.period_combo,
            f.mode_combo,
            f.language_combo,
            f.format_combo,
        ):
            widget.currentIndexChanged.connect(self._on_changed)
        f.max_results_spin.valueChanged.connect(self._on_changed)
        for edit in (f.after_edit, f.before_edit):
            edit.dateChanged.connect(self._on_changed)
        for linha in (f.country_edit, f.region_edit, f.city_edit):
            linha.textChanged.connect(self._on_changed)
        for check in (f.location_check, f.advanced_check, *f.priority_checks.values()):
            check.toggled.connect(self._on_changed)
        f.extra_domains.textChanged.connect(self._on_changed)
        f.instructions_edit.textChanged.connect(self._on_changed)
        f.packs_list.itemChanged.connect(self._on_changed)

        f.period_combo.currentIndexChanged.connect(lambda _: f.sync_visibility())
        f.location_check.toggled.connect(lambda _: f.sync_visibility())
        f.advanced_check.toggled.connect(f.sync_advanced)

    # ------------------------------------------------------------------ eventos

    def _on_changed(self, *_: object) -> None:
        self._revalidate()
        self.changed.emit()

    def _on_toggled(self, aberto: bool) -> None:
        self.body.setVisible(aberto)
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if aberto else Qt.ArrowType.RightArrow)

    # ------------------------------------------------------------------ leitura

    def options(self) -> SearchOptions:
        """Lê os controles e devolve as opções de agora."""
        f = self.form
        periodo = data(f.period_combo)
        intervalo = periodo == "range"
        location = None
        if f.location_check.isChecked():
            location = LocationOpt(
                country=f.country_edit.text().strip().upper(),
                region=f.region_edit.text().strip(),
                city=f.city_edit.text().strip(),
            )
        return SearchOptions(
            preset=data(f.preset_combo),  # type: ignore[arg-type]
            domains=self.domains(),
            domain_mode=data(f.mode_combo),  # type: ignore[arg-type]
            recency=(None if intervalo else (periodo or None)),  # type: ignore[arg-type]
            after=qdate(f.after_edit) if intervalo else None,
            before=qdate(f.before_edit) if intervalo else None,
            location=location,
            context_size=data(f.context_combo),  # type: ignore[arg-type]
            max_results=f.max_results_spin.value(),
            language=data(f.language_combo),
            output_format=data(f.format_combo),
            priorities=tuple(k for k, c in f.priority_checks.items() if c.isChecked()),
            custom_instructions=(
                f.instructions_edit.toPlainText().strip() if f.advanced_check.isChecked() else ""
            ),
        )

    def domains(self) -> tuple[str, ...]:
        """União dos pacotes marcados com os domínios extras, sem repetir."""
        escolhidos: list[str] = []
        marcados = self.selected_packs()
        for pack in self.packs:
            if pack.key in marcados:
                escolhidos += [d for d in pack.domains if d not in escolhidos]
        for linha in self.form.extra_domains.toPlainText().splitlines():
            dominio = linha.strip().lstrip("-").strip()
            if dominio and dominio not in escolhidos:
                escolhidos.append(dominio)
        return tuple(escolhidos)

    def selected_packs(self) -> tuple[str, ...]:
        lista = self.form.packs_list
        return tuple(
            lista.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(lista.count())
            if lista.item(i).checkState() == Qt.CheckState.Checked
        )

    # ------------------------------------------------------------------ escrita

    def set_options(self, options: SearchOptions, source_packs: tuple[str, ...] = ()) -> None:
        """Preenche os controles. Usado ao abrir o app e pelo "Repetir busca" da F9."""
        f = self.form
        bloqueados = self.blockSignals(True)
        try:
            f.advanced_check.setChecked(bool(options.custom_instructions) or options.preset == "xhigh")
            f.sync_advanced(f.advanced_check.isChecked())

            select(f.preset_combo, options.preset)
            select(f.context_combo, options.context_size)
            select(f.mode_combo, options.domain_mode)
            select(f.language_combo, options.language)
            select(f.format_combo, options.output_format)
            f.max_results_spin.setValue(options.max_results)
            f.instructions_edit.setPlainText(options.custom_instructions)

            if options.after or options.before:
                select(f.period_combo, "range")
                f.after_edit.setDate(to_qdate(options.after or date.today()))
                f.before_edit.setDate(to_qdate(options.before or date.today()))
            else:
                select(f.period_combo, options.recency or "")

            f.location_check.setChecked(options.location is not None)
            local = options.location or self.defaults.location_shortcut
            f.country_edit.setText(local.country)
            f.region_edit.setText(local.region)
            f.city_edit.setText(local.city)

            for chave, check in f.priority_checks.items():
                check.setChecked(chave in options.priorities)

            marcados = set(source_packs)
            for i in range(f.packs_list.count()):
                item = f.packs_list.item(i)
                ligado = item.data(Qt.ItemDataRole.UserRole) in marcados
                item.setCheckState(Qt.CheckState.Checked if ligado else Qt.CheckState.Unchecked)

            # Só vai para "Domínios extras" o que nenhum pacote marcado já traz.
            extras = [d for d in options.domains if not self._em_pacotes(d, marcados)]
            f.extra_domains.setPlainText("\n".join(extras))
        finally:
            self.blockSignals(bloqueados)

        f.sync_visibility()
        self._revalidate()
        self.changed.emit()

    def set_options_inferring_packs(self, options: SearchOptions) -> None:
        """Como `set_options`, mas remarcando os pacotes de fontes que a lista de domínios contém.

        O histórico guarda só a lista final de domínios (é o que `SearchOptions` conhece), então
        "Repetir busca" jogaria 14 domínios na caixa de extras com o pacote desmarcado. Aqui
        remarcamos os pacotes inteiramente contidos — e, se a remarcação mudar a ordem dos
        domínios, voltamos atrás: as opções repetidas têm de ser **idênticas** às de origem.
        """
        candidatos = tuple(p.key for p in self.packs if p.domains and set(p.domains) <= set(options.domains))
        self.set_options(options, source_packs=candidatos)
        if self.options().domains != options.domains:
            self.set_options(options)

    def restore_defaults(self) -> None:
        """Botão "Restaurar padrões" (RF4): volta ao `config/defaults.toml`."""
        self.set_options(self.defaults.options, source_packs=self.defaults.source_packs)

    def _em_pacotes(self, dominio: str, marcados: set[str]) -> bool:
        return any(p.key in marcados and dominio in p.domains for p in self.packs)

    # ------------------------------------------------------------------ validação

    def _revalidate(self) -> None:
        total = len(self.domains())
        self.form.domain_counter.setText(f"{total}/{MAX_DOMAINS} domínios")
        self.form.domain_counter.setStyleSheet("color: #b00020;" if total > MAX_DOMAINS else "")

        ok, dica = self.validate()
        self.summary.setText(summary_text(self.options()) if ok else f"⚠ {dica}")
        self.validity_changed.emit(ok, dica)

    def validate(self) -> tuple[bool, str]:
        """Pergunta ao `prompt_builder` se as opções fecham — sem duplicar as regras."""
        try:
            build(PROMPT_DE_PROVA, self.options(), self.snippets, self.defaults.timeouts)
        except ValueError as exc:
            return False, str(exc)
        return True, ""

    # ------------------------------------------------------------------ prévia

    def payload_preview(self, prompt: str = "") -> str:
        """JSON do payload + timeout, exatamente como seriam enviados (RF4)."""
        pergunta = prompt.strip() or PROMPT_DE_PROVA
        try:
            req = build(pergunta, self.options(), self.snippets, self.defaults.timeouts)
        except ValueError as exc:
            return f"As opções atuais não formam uma busca válida:\n\n{exc}"
        return f"timeout: {req.timeout_s}s\n\n{json.dumps(req.payload, ensure_ascii=False, indent=2)}"

    def show_preview(self, prompt: str = "") -> PromptPreviewDialog:
        dialogo = PromptPreviewDialog(self.payload_preview(prompt), self)
        dialogo.exec()
        return dialogo
