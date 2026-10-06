"""Guarda a regra de camadas do AGENTS.md: `ui/ → services/ → core/`.

Isto é um teste e não um comentário porque a regra é fácil de quebrar sem perceber — um import
de conveniência em `core/` já derruba a testabilidade de toda a camada pura.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "condor"

#: O que `core/` não pode importar (camada pura: sem Qt, sem SDK, sem banco).
PROIBIDO_NO_CORE = ("PySide6", "perplexity", "sqlite3", "requests", "httpx")

_IMPORT = re.compile(r"^\s*(?:from|import)\s+([A-Za-z_][\w.]*)", re.MULTILINE)


def _imports(path: Path) -> set[str]:
    return {m.group(1).split(".")[0] for m in _IMPORT.finditer(path.read_text(encoding="utf-8"))}


@pytest.mark.parametrize("arquivo", sorted((SRC / "core").glob("*.py")), ids=lambda p: p.name)
def test_core_nao_importa_qt_sdk_nem_banco(arquivo: Path) -> None:
    proibidos = _imports(arquivo) & set(PROIBIDO_NO_CORE)
    assert not proibidos, f"{arquivo.name} importa {proibidos} — core/ tem de ser puro."


@pytest.mark.parametrize("arquivo", sorted((SRC / "core").glob("*.py")), ids=lambda p: p.name)
def test_core_nao_importa_services_nem_ui(arquivo: Path) -> None:
    texto = arquivo.read_text(encoding="utf-8")
    assert "condor.services" not in texto
    assert "condor.ui" not in texto


#: A fronteira com o SDK. Eram só `client.py` até a F10; `error_mapping.py` saiu dele quando o
#: arquivo passou das 300 linhas do AGENTS.md. Continuam sendo os dois únicos arquivos que
#: conhecem tipos do `perplexity`, e ambos vivem na mesma camada.
FRONTEIRA_DO_SDK = {"services/client.py", "services/error_mapping.py"}


def test_so_a_fronteira_importa_o_sdk() -> None:
    """AGENTS: o contato com o SDK fica confinado — trocar de SDK não deve respingar na UI."""
    com_sdk = {p.relative_to(SRC).as_posix() for p in SRC.rglob("*.py") if "perplexity" in _imports(p)}
    assert com_sdk == FRONTEIRA_DO_SDK


def test_a_ui_nao_conhece_o_sdk() -> None:
    for arquivo in (SRC / "ui").glob("*.py"):
        assert "perplexity" not in _imports(arquivo), f"{arquivo.name} importa o SDK."


def test_services_nao_importa_ui() -> None:
    for arquivo in (SRC / "services").glob("*.py"):
        assert "condor.ui" not in arquivo.read_text(encoding="utf-8")
