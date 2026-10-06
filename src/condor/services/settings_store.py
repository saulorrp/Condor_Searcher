"""Lembra a última configuração usada, em JSON (RF4: "Última configuração usada é lembrada").

Nada aqui é essencial: se o arquivo não existe, está corrompido ou foi escrito por uma versão
anterior, o app abre com os padrões e segue. Preferência do usuário perdida é um incômodo;
app que não abre por causa de um JSON torto é um defeito.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from condor.core.models import SearchOptions, options_from_dict, options_to_dict

logger = logging.getLogger(__name__)

FILE_NAME = "settings.json"

#: Sobe quando o formato mudar de um jeito que exija descartar o arquivo antigo.
SCHEMA_VERSION = 1


class SettingsStore:
    """Um arquivo JSON com a última configuração."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load(self, fallback: SearchOptions | None = None) -> SearchOptions:
        """Devolve a última configuração salva, ou `fallback` (ou os padrões) se não der."""
        padrao = fallback if fallback is not None else SearchOptions()
        dados = self._read()
        if dados is None:
            return padrao
        return options_from_dict(dados.get("options") or {})

    def _read(self) -> dict | None:
        """Lê o arquivo, ou `None` se não existir, estiver ilegível ou for de outra versão."""
        if not self.path.exists():
            return None
        try:
            dados = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Não consegui ler %s (%s); usando os padrões.", self.path.name, exc)
            return None
        if not isinstance(dados, dict) or dados.get("version") != SCHEMA_VERSION:
            logger.info("%s é de outra versão do formato; usando os padrões.", self.path.name)
            return None
        return dados

    def load_source_packs(self, fallback: tuple[str, ...] = ()) -> tuple[str, ...]:
        """Os pacotes de fontes marcados da última vez.

        Guardado separadamente porque `SearchOptions` só conhece a lista final de domínios: sem
        isto, reabrir o app mostraria os domínios do pacote soltos em "Domínios extras", com o
        pacote desmarcado.
        """
        dados = self._read()
        valor = dados.get("source_packs") if isinstance(dados, dict) else None
        if not isinstance(valor, list):
            return fallback
        return tuple(str(item) for item in valor if str(item).strip())

    def load_flag(self, nome: str, padrao: bool) -> bool:
        """Preferência de interface (ex.: mostrar a resposta enquanto chega).

        Fica fora de `SearchOptions` porque não muda o resultado da busca, só a forma de exibir —
        e `SearchOptions` é o que vai para a API e para o histórico.
        """
        dados = self._read() or {}
        valor = (dados.get("ui") or {}).get(nome)
        return bool(valor) if isinstance(valor, bool) else padrao

    def save(
        self,
        options: SearchOptions,
        source_packs: tuple[str, ...] = (),
        ui: dict[str, bool] | None = None,
    ) -> bool:
        """Grava a configuração. Devolve `False` se não deu (disco cheio, pasta somente leitura)."""
        dados = {
            "version": SCHEMA_VERSION,
            "options": options_to_dict(options),
            "source_packs": list(source_packs),
            "ui": dict(ui or {}),
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            logger.warning("Não consegui salvar %s (%s).", self.path.name, exc)
            return False
        return True

    def clear(self) -> None:
        """Esquece a configuração salva — usado pelo botão "Restaurar padrões" (RF4)."""
        self.path.unlink(missing_ok=True)
