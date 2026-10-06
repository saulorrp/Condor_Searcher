"""Apoio para os testes de interface.

Roda em `offscreen`: os testes não abrem janela na tela e funcionam igual numa máquina sem
sessão gráfica. Nenhum teste de UI toca na rede — o cliente é sempre falso.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from condor.core.config import load_defaults, load_snippets  # noqa: E402
from condor.services.secrets import ENV_VAR, SecretStore  # noqa: E402
from condor.services.settings_store import SettingsStore  # noqa: E402
from condor.services.storage import Storage  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"
CHAVE = "pplx-chavefalsa1234567890"


@pytest.fixture(scope="session")
def defaults():
    return load_defaults(ROOT / "config" / "defaults.toml")


@pytest.fixture(scope="session")
def snippets():
    return load_snippets(ROOT / "config" / "prompt_snippets.toml")


@pytest.fixture(scope="session")
def raw_fast() -> dict:
    return json.loads((FIXTURES / "agent_fast.json").read_text(encoding="utf-8"))


@pytest.fixture
def storage(tmp_path: Path) -> Storage:
    return Storage(tmp_path / "saida")


@pytest.fixture
def secrets(tmp_path: Path) -> SecretStore:
    """Chave presente, em `.env` próprio — nunca o `.env` do usuário."""
    env = tmp_path / ".env"
    env.write_text(f"{ENV_VAR}={CHAVE}\n", encoding="utf-8")
    return SecretStore(env, environ={})


@pytest.fixture
def settings_tmp(tmp_path: Path) -> SettingsStore:
    """Configuração salva num arquivo temporário — nunca a do usuário."""
    return SettingsStore(tmp_path / "settings.json")


@pytest.fixture
def secrets_sem_chave(tmp_path: Path) -> SecretStore:
    return SecretStore(tmp_path / "vazio" / ".env", environ={})


@pytest.fixture(autouse=True)
def sem_caixas_modais(monkeypatch):
    """Rede de segurança: uma caixa de diálogo que escape trava a suíte inteira.

    Os testes que querem verificar o diálogo substituem o método de novo, por cima deste.
    """
    from condor.ui.main_window import MainWindow

    escapadas: list[tuple[str, str]] = []
    monkeypatch.setattr(MainWindow, "show_error", lambda self, t, m: escapadas.append((t, m)))
    monkeypatch.setattr(MainWindow, "ask_change_key", lambda self, m: False)
    monkeypatch.setattr(MainWindow, "ask_delete", lambda self, r: False)
    return escapadas
